"""댓글 규칙 검사 V1~V12 (DESIGN 5.4, PLAYBOOK 6단계).

네트워크·DB·LLM 없이 도는 순수 함수다. AI가 쓴 초안과 사람이 고친 글이 **같은 함수**를 거친다.

- `validate(text, ...)` → `Validation(passed, checks, char_count, evidence_quote)`
- `find_evidence(text, context_text)` → 글과 영상 자료에 함께 나오는 가장 긴 구절
  (영상 자료 원문 그대로)
- `normalize(s)` → 대조용 글: NFC, 소문자, 글자·숫자만 남김(공백·문장부호·이모지·기호 제거)

실패 문구는 "무엇이 걸렸고 → 어떻게 고치면 되는지"를 한 줄로 쓴다. 화면과 5단계 재생성 프롬프트가
같은 문구를 쓴다.

글자 수는 NFC로 맞춘 뒤의 **코드 포인트 수**다(표기 `[광고]`와 공백 포함). 피부색이 붙은 이모지처럼
여러 코드 포인트로 된 그림 글자는 2자 이상으로 센다(엄격한 쪽).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

# ---------------------------------------------------------------- 기준값

MIN_EVIDENCE_CHARS = 6  # V6: 근거 구절은 정리 후 6자 이상
MIN_OVERLAP_CHARS = 4  # V7: 글과 근거 구절이 정리 후 4자 이상 연속으로 겹친다
QUOTE_SIMILARITY = 0.85  # V6: 근거 구절이 그대로 없으면 이만큼 비슷한 구간이 있어야 한다
PREVIOUS_SIMILARITY = 0.6  # V11: 이전 글과 이만큼 비슷하면 실패
BRAND_GAP = 8  # 따옴표로 옮긴 영상 속 말: 앞뒤 이만큼 안에 브랜드가 있으면 V8~V10 면제 없음
FACT_EXTRA_CHARS = 3  # V10: 걸린 말 앞뒤로 이만큼 더 brand.facts와 똑같으면 사실 문장으로 본다
_FIND_MIN = 2  # find_evidence: 정리 후 이보다 짧은 겹침은 구절로 치지 않는다

CHECK_NAMES: dict[str, str] = {
    "V1": "길이 40~120자 · 한 줄",
    "V2": "링크 없음",
    "V3": "해시태그 없음",
    "V4": "홍보 표기 맨 앞",
    "V5": "브랜드 이름 1~2번",
    "V6": "근거가 영상 자료에 있음",
    "V7": "글이 근거를 담음",
    "V8": "이용 후기 표현 없음",
    "V9": "지어낸 연애 사연 없음",
    "V10": "효능·최상급 표현 없음",
    "V11": "이전 글과 다름",
    "V12": "한글·영문·숫자·기본 문장부호만",
}
PATTERN_CODES = ("V8", "V9", "V10")

# ---------------------------------------------------------------- 표현 목록(정규식)
# 과하게 잡는 쪽이 안전하다(걸리면 다시 만들면 된다). 다만 정상 표현("공감돼요", "상담받아
# 보세요")과 시청자 말투의 의향·가벼운 평판("저도 한번 보고 싶네요", "요즘 많이 보이던데",
# "잘 본다던데")은 걸리지 않게 한다 — 테스트로 확인한다. 막는 것은 써 본 척(V8), 지어낸 애인
# 이야기(V9), 효능 단정(V10)이다(2026-11-17 시청자 말투 전환, 과제 PDF 기준).

LINK_PATTERNS: tuple[str, ...] = (
    r"https?",
    r"www\s?[.．。]",
    r"[0-9a-z가-힣_-]+\s?[.．。]\s?(?:com|kr|net|co|io|me|app|shop)(?![a-z])",
    r"닷\s?컴",
)

# V8 직접 이용한 후기 표현
REVIEW_PATTERNS: tuple[str, ...] = (
    r"봤는데",
    r"봐\s?봤",
    r"받아\s?봤",
    r"받았는데",
    r"받았어",
    r"받고\s?왔",
    r"다녀\s?왔",
    r"다녀\s?온",
    r"갔다\s?왔",
    r"가\s?봤",
    r"써\s?봤",
    r"이용해\s?봤",
    r"이용했",
    # 권하는 말·의향은 뺀다: 상담받아 보세요·상담받아보시는·상담받아 보고 싶다·상담받을 수·
    # 상담받으실·상담받으러 오세요·상담받기
    r"상담\s?받(?!\s?아\s?보(?:세요|시|셔|실|고\s?싶)|을\s?수|으실|으러\s?오|기)",
    r"예약\s?(?:했|해\s?놨|해\s?뒀|함|완료)",
    r"후기",
    r"소름",
    r"맞더라",
    r"맞췄",
    r"맞추더",
    r"맞히",
    r"효과\s?(?:봤|를\s?봤|있었)",
    r"덕분에",
    r"직접\s?(?:가|받|봤|해\s?봤|상담)",
    r"실제로\s?(?:가|받|봤|해\s?봤|상담)",
)

# V9 지어낸 연애 사연(내 애인·전 애인 이야기). 시청자 말투의 공감·의향("저도 한번 보고 싶네요",
# "완전 제 얘기네요")은 과제 PDF가 원하는 페르소나라 막지 않는다(2026-11-17).
CONSUMER_PATTERNS: tuple[str, ...] = (
    r"(?<![가-힣])(?:제|내)\s?(?:남친|여친|남자\s?친구|여자\s?친구|애인|전\s?남친|전\s?여친)",
    r"우리\s?(?:남친|여친|오빠|자기)",
)

# V10 확인할 수 없는 효능·최상급 표현
CLAIM_PATTERNS: tuple[str, ...] = (
    r"\d+\s?[%％]",
    r"퍼센트",
    r"무조건",
    r"반드시",
    r"보장",
    r"제일",
    r"최고",
    r"최상",
    r"유일",
    r"족집게",
    r"(?<![가-힣])용한",
    r"확실",
    r"완벽",
    r"백발백중",
    r"(?<![0-9])1\s?(?:등|위)",
    r"넘버\s?원",
    r"정확(?:하|히|한|도|해)",
    r"잘\s?(?:맞혀|맞춰|맞히|맞추|맞췄|맞더)",
    r"신통",
    r"효과",
    r"효험",
    # 맞힌다는 효능은 남의 말로 옮겨도 막는다("잘 맞는대요", "용하대요"). 가벼운 평판("잘
    # 본다던데", "유명하던데", "요즘 많이 보이던데")은 과제 PDF의 예와 brand.facts("잘 봐주는
    # 곳으로 알려져 있다")에 맞춰 허용한다(2026-11-17 시청자 말투 전환).
    r"(?<![가-힣])용하",
    r"잘\s?맞(?:는다|는대|아요|아서|더|대)",
    r"(?:맞는|맞힌|맞춘)\s?(?:대요|대서|대더라|다네요|다니까|다던데|다더라)",
)

BUILTIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "V8": REVIEW_PATTERNS,
    "V9": CONSUMER_PATTERNS,
    "V10": CLAIM_PATTERNS,
}


# ---------------------------------------------------------------- 결과 모양


@dataclass(frozen=True)
class CheckResult:
    code: str  # V1 ~ V11
    name: str
    passed: bool
    message: str  # 한 줄: 통과면 확인한 내용, 실패면 걸린 것 — 고치는 법

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "name": self.name, "passed": self.passed,
                "message": self.message}


@dataclass(frozen=True)
class Validation:
    passed: bool
    checks: tuple[CheckResult, ...]
    char_count: int
    evidence_quote: str | None  # 대조에 쓴 근거 구절(주어진 것, 없으면 찾은 것)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def failure_lines(self) -> list[str]:
        """재생성 프롬프트·화면에 그대로 쓰는 실패 문구."""
        return [f"{c.code} {c.name}: {c.message}" for c in self.failures]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "char_count": self.char_count,
            "evidence_quote": self.evidence_quote,
        }


@dataclass(frozen=True)
class ValidatorRules:
    """검사 기준. `config.yaml`의 `comment`와 `validator.extra_patterns`에서 만든다."""

    min_chars: int = 40
    max_chars: int = 120
    brand: str = "운명원"
    disclosure: str = "[광고]"
    extra_patterns: tuple[tuple[str, str], ...] = ()  # (V8|V9|V10, 정규식)
    _compiled: dict[str, tuple[re.Pattern[str], ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        compiled: dict[str, tuple[re.Pattern[str], ...]] = {}
        for code in PATTERN_CODES:
            sources = list(BUILTIN_PATTERNS[code])
            sources += [p for c, p in self.extra_patterns if c == code]
            compiled[code] = tuple(re.compile(p, re.IGNORECASE) for p in sources)
        object.__setattr__(self, "_compiled", compiled)

    @classmethod
    def from_config(
        cls, rules: Mapping[str, Any], extra_patterns: Iterable[tuple[str, str]] = ()
    ) -> ValidatorRules:
        comment = rules.get("comment") or {}
        return cls(
            min_chars=int(comment.get("min_chars", 40)),
            max_chars=int(comment.get("max_chars", 120)),
            brand=str(comment.get("brand") or "운명원"),
            disclosure=str(comment.get("disclosure") or "[광고]"),
            extra_patterns=tuple(extra_patterns),
        )

    def patterns(self, code: str) -> tuple[re.Pattern[str], ...]:
        return self._compiled[code]


def parse_extra_patterns(raw: Any) -> tuple[tuple[str, str], ...]:
    """`validator.extra_patterns`를 읽는다. 항목 모양: `{code: V8|V9|V10, pattern: 정규식}`.

    잘못된 항목은 앱을 켤 때 바로 알 수 있게 `ValueError`(무엇이 틀렸는지 한국어)를 낸다.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("validator.extra_patterns는 목록이어야 합니다.")
    out: list[tuple[str, str]] = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"validator.extra_patterns {i}번째 항목은 {{code: V8, pattern: ...}} 모양이어야 "
                "합니다."
            )
        code = str(item.get("code") or "").strip().upper()
        pattern = str(item.get("pattern") or "")
        if code not in PATTERN_CODES:
            raise ValueError(
                f"validator.extra_patterns {i}번째 항목의 code는 V8·V9·V10 중 하나여야 합니다."
            )
        if not pattern.strip():
            raise ValueError(f"validator.extra_patterns {i}번째 항목의 pattern이 비어 있습니다.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"validator.extra_patterns {i}번째 항목의 정규식이 잘못됐습니다: {exc}"
            ) from exc
        out.append((code, pattern))
    return tuple(out)


# ---------------------------------------------------------------- 대조용 도우미


def _keep(ch: str) -> bool:
    return unicodedata.category(ch)[0] in "LN"  # 글자(L)·숫자(N)만


def normalize(s: str) -> str:
    """대조용: NFC, 소문자, 글자·숫자만 남긴다(공백·문장부호·이모지·기호 제거)."""
    return "".join(ch for ch in unicodedata.normalize("NFC", s or "").lower() if _keep(ch))


def _normalize_map(s: str) -> tuple[str, list[int]]:
    """정리한 글과, 정리한 글의 각 글자가 원문(NFC) 몇 번째 글자였는지."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(s):
        low = ch.lower()
        if len(low) == 1 and _keep(low):
            chars.append(low)
            index.append(i)
    return "".join(chars), index


def _longest_common(a: str, b: str) -> tuple[int, int, int]:
    """(a 시작, b 시작, 길이). 긴 글(b)에서 자주 나오는 글자를 버리지 않게 autojunk를 끈다."""
    if not a or not b:
        return 0, 0, 0
    m = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.a, m.b, m.size


def _strip_markers(text: str, rules: ValidatorRules) -> str:
    """대조할 때는 홍보 표기와 브랜드 이름을 뺀다(영상 자료에 우연히 있어도 근거가 아니다)."""
    for marker in (rules.disclosure, rules.brand):
        if marker:
            text = text.replace(marker, " ")
    return text


def find_evidence(text: str, context_text: str) -> str | None:
    """글과 영상 자료에 함께 나오는 가장 긴 구절을 영상 자료 원문 그대로 돌려준다.

    공백·문장부호·이모지는 무시하고 맞춘다. 정리 후 2자보다 짧으면 None.
    """
    ctx = unicodedata.normalize("NFC", context_text or "")
    text_n = normalize(text)
    ctx_n, ctx_index = _normalize_map(ctx)
    _, start, size = _longest_common(text_n, ctx_n)
    if size < _FIND_MIN:
        return None
    first, last = ctx_index[start], ctx_index[start + size - 1]
    return ctx[first : last + 1].strip()


def quote_in_context(quote: str, context_text: str) -> bool:
    """근거 구절이 영상 자료에 있는가 — V6과 같은 기준(정리 후 6자 이상, 그대로 있거나 85% 이상
    비슷한 구간). 5단계 분석이 모델이 고른 근거를 거를 때 쓴다."""
    quote_n = normalize(quote)
    if len(quote_n) < MIN_EVIDENCE_CHARS:
        return False
    ctx_n = normalize(context_text)
    if quote_n in ctx_n:
        return True
    return _best_window_ratio(quote_n, ctx_n) >= QUOTE_SIMILARITY


def _best_window_ratio(quote_n: str, ctx_n: str) -> float:
    """영상 자료에서 근거 구절과 가장 비슷한 같은 길이 구간의 유사도(0~1).

    3글자 조각이 겹치는 자리만 후보로 본다(긴 자료를 다 훑지 않게).
    """
    n = len(quote_n)
    if not n or not ctx_n:
        return 0.0
    gram = 3 if n >= 3 else 1
    positions: dict[str, list[int]] = {}
    for j in range(len(ctx_n) - gram + 1):
        positions.setdefault(ctx_n[j : j + gram], []).append(j)
    starts: set[int] = set()
    for i in range(n - gram + 1):
        for j in positions.get(quote_n[i : i + gram], ()):
            starts.add(max(0, j - i))
    best = 0.0
    for s in starts:
        window = ctx_n[s : s + n]
        matcher = SequenceMatcher(None, quote_n, window, autojunk=False)
        if matcher.real_quick_ratio() <= best or matcher.quick_ratio() <= best:
            continue
        best = max(best, matcher.ratio())
        if best >= 1.0:
            break
    return best


def _clip(s: str, limit: int = 24) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _found(matches: list[str]) -> str:
    uniq = list(dict.fromkeys(m.strip() for m in matches if m.strip()))
    return ", ".join(f"'{_clip(m, 16)}'" for m in uniq[:3])


# ---------------------------------------------------------------- 규칙별 검사


def _check(code: str, passed: bool, message: str) -> CheckResult:
    return CheckResult(code=code, name=CHECK_NAMES[code], passed=passed, message=message)


def _v1_length(text: str, rules: ValidatorRules) -> CheckResult:
    n = len(text)
    lo, hi = rules.min_chars, rules.max_chars
    problems: list[str] = []
    if "\n" in text or "\r" in text:
        problems.append("줄바꿈이 있습니다 — 한 줄로 이어 쓰세요")
    if n < lo:
        problems.append(f"{n}자로 짧습니다({lo}~{hi}자, 표기 포함) — {lo - n}자 이상 늘리세요")
    elif n > hi:
        problems.append(f"{n}자로 깁니다({lo}~{hi}자, 표기 포함) — {n - hi}자 이상 줄이세요")
    if problems:
        return _check("V1", False, " / ".join(problems))
    return _check("V1", True, f"{n}자(표기 포함, {lo}~{hi}자) · 한 줄")


def _v2_links(text: str) -> CheckResult:
    probe = unicodedata.normalize("NFKC", text)  # 전각 글자(ｗｗｗ．)도 잡는다
    hits = [m.group(0) for p in LINK_PATTERNS for m in re.finditer(p, probe, re.IGNORECASE)]
    if hits:
        return _check(
            "V2", False, f"주소로 보이는 글자가 있습니다: {_found(hits)} — 링크를 지우세요"
        )
    return _check("V2", True, "주소로 보이는 글자 없음")


def _v3_hashtags(text: str) -> CheckResult:
    hits = re.findall(r"[#＃]\S*", text)
    if hits:
        return _check(
            "V3", False, f"해시태그가 있습니다: {_found(hits)} — # 기호와 태그를 지우세요"
        )
    return _check("V3", True, "# 기호 없음")


def _v4_disclosure(text: str, rules: ValidatorRules, *, required: bool = True) -> CheckResult:
    """`required=False`는 광고 표기를 끈 초안(R3: 모든 영상에서 켜고 끌 수 있다). 표기가 있으면
    맨 앞이어야 하는 것은 같다."""
    mark = rules.disclosure
    if text.startswith(mark + " "):
        return _check("V4", True, f"맨 앞이 {mark}")
    if text.startswith(mark):
        return _check("V4", False, f"{mark} 바로 뒤에 한 칸을 띄우세요 — '{mark} 본문' 모양으로")
    if mark in text:
        return _check("V4", False, f"{mark}가 맨 앞에 있지 않습니다 — 글 맨 앞으로 옮기세요")
    if not required:
        return _check("V4", True, "표기 끔")
    return _check("V4", False, f"홍보 표기 {mark}가 없습니다 — 글을 '{mark} '로 시작하세요")


def _v5_brand(text: str, rules: ValidatorRules) -> CheckResult:
    brand = rules.brand
    count = text.count(brand) if brand else 0
    if count == 0:
        return _check("V5", False, f"브랜드 이름 '{brand}'이(가) 없습니다 — 한 번 넣으세요")
    if count > 2:
        return _check("V5", False, f"'{brand}'이(가) {count}번 나옵니다 — 1~2번으로 줄이세요")
    return _check("V5", True, f"'{brand}' {count}번")


def _v6_v7_evidence(
    text: str, context_text: str, rules: ValidatorRules, evidence_quote: str | None
) -> tuple[CheckResult, CheckResult, str | None]:
    body = _strip_markers(text, rules)
    body_n = normalize(body)
    ctx_n = normalize(context_text)

    if evidence_quote is not None and evidence_quote.strip():
        quote = unicodedata.normalize("NFC", evidence_quote).strip()
        quote_n = normalize(quote)
        if len(quote_n) < MIN_EVIDENCE_CHARS:
            v6 = _check(
                "V6", False,
                f"근거 '{_clip(quote)}'가 너무 짧습니다 — 영상 속 말을 "
                f"{MIN_EVIDENCE_CHARS}자 이상 그대로 쓰세요",
            )
        elif quote_n in ctx_n:
            v6 = _check("V6", True, f"근거 '{_clip(quote)}'가 영상 자료에 있음")
        else:
            ratio = _best_window_ratio(quote_n, ctx_n)
            if ratio >= QUOTE_SIMILARITY:
                v6 = _check(
                    "V6", True,
                    f"근거 '{_clip(quote)}'와 {ratio:.0%} 비슷한 구간이 영상 자료에 있음",
                )
            else:
                v6 = _check(
                    "V6", False,
                    f"근거 '{_clip(quote)}'가 영상 자료에 없습니다 — 자막·설명·댓글에 "
                    "실제로 있는 말을 쓰세요",
                )
    else:
        quote = find_evidence(body, context_text)
        quote_n = normalize(quote or "")
        if quote and len(quote_n) >= MIN_EVIDENCE_CHARS:
            v6 = _check("V6", True, f"영상 자료와 겹치는 구절: '{_clip(quote)}'")
        elif quote:
            v6 = _check(
                "V6", False,
                f"영상과 겹치는 말이 '{_clip(quote)}'뿐입니다 — 영상 속 말을 "
                f"{MIN_EVIDENCE_CHARS}자 이상 그대로 넣으세요",
            )
        else:
            v6 = _check(
                "V6", False,
                f"영상과 겹치는 말이 없습니다 — 영상 속 말을 {MIN_EVIDENCE_CHARS}자 이상 "
                "그대로 넣으세요",
            )

    if not quote or (evidence_quote is None and not v6.passed):
        # 근거를 글에서 찾는 경우 V6이 실패하면 V7도 확인할 근거가 없다. 원인은 V6 하나다.
        v7 = _check("V7", False, "확인할 근거 구절이 없습니다 — V6을 고치면 함께 풀립니다")
    else:
        _, _, overlap = _longest_common(body_n, quote_n)
        if overlap >= MIN_OVERLAP_CHARS:
            v7 = _check("V7", True, f"근거와 {overlap}자 연속으로 겹침")
        else:
            v7 = _check(
                "V7", False,
                f"글에 근거 '{_clip(quote)}'의 말이 없습니다 — 근거의 낱말을 "
                f"{MIN_OVERLAP_CHARS}자 이상 이어서 넣으세요",
            )
    return v6, v7, quote or None


def _fact_allows(text: str, start: int, end: int, facts_n: list[str]) -> bool:
    """걸린 말이 brand.facts의 문장 안에서 앞뒤 말까지 똑같이 쓰였으면 허용한다.

    걸린 말을 품은 구간이 어떤 사실 문장과 (걸린 말 + 3자) 이상 똑같아야 한다.
    """
    text_n, index = _normalize_map(text)
    span = [k for k, i in enumerate(index) if start <= i < end]
    if not span:
        return False
    ms, me = span[0], span[-1] + 1
    need = (me - ms) + FACT_EXTRA_CHARS
    for fact in facts_n:
        i = ms
        while i >= 0 and text_n[i:me] in fact:
            j = me
            while j < len(text_n) and text_n[i : j + 1] in fact:
                j += 1
            if j - i >= need:
                return True
            i -= 1
    return False


_QUOTED = re.compile('\'([^\'\n]{2,})\'|"([^"\n]{2,})"|‘([^’\n]{2,})’|“([^”\n]{2,})”')


def _quoted_spans(text: str, context_text: str, rules: ValidatorRules) -> list[tuple[int, int]]:
    """글 안에서 영상 자료의 말을 따옴표로 그대로 옮긴 구간들(원문 위치, 따옴표 포함).

    5단계: 영상 속 말을 따옴표로 옮기면 그 안의 "제일 걱정", "소름 돋았다" 같은 말이 V8~V10에
    걸렸다. 그 말은 홍보 담당자의 주장이 아니라 영상의 말이므로 넘어간다. 다만 좁게만 허용한다.
    - 따옴표 안의 말이 V6과 같은 기준으로 영상 자료에 있어야 한다(따옴표 없이 옮기면 걸린다)
    - 따옴표 안이나 따옴표 앞뒤 8자 안에 브랜드 이름이 있으면 넘어가지 않는다. 영상·댓글 속
      "여기가 제일 정확해요"를 브랜드에 붙여 옮기는 것도 전해 들은 효능이기 때문이다
    """
    spans: list[tuple[int, int]] = []
    for m in _QUOTED.finditer(text):
        inner = next(g for g in m.groups() if g is not None)
        around = text[max(0, m.start() - BRAND_GAP) : m.end() + BRAND_GAP]
        if rules.brand and rules.brand in around:
            continue
        if quote_in_context(inner, context_text):
            spans.append((m.start(), m.end()))
    return spans


def _pattern_check(
    code: str,
    text: str,
    rules: ValidatorRules,
    hint: str,
    facts_n: list[str] | None = None,
    quoted: Sequence[tuple[int, int]] = (),
) -> CheckResult:
    hits: list[str] = []
    for pattern in rules.patterns(code):
        for m in pattern.finditer(text):
            if facts_n and _fact_allows(text, m.start(), m.end(), facts_n):
                continue
            if any(a <= m.start() and m.end() <= b for a, b in quoted):
                continue  # 영상 속 말을 따옴표로 그대로 옮긴 구간 안
            hits.append(m.group(0))
    if hits:
        return _check(code, False, f"걸린 말 {_found(hits)} — {hint}")
    return _check(code, True, "걸린 표현 없음")


# V12: 허용 글자(PLAYBOOK 6단계 표). 공백 문자는 여기서 받고 줄바꿈은 V1이 잡는다.
ALLOWED_PUNCT = frozenset(".,!?~'\"‘’“”…·-()[]%:/")


def _allowed_char(ch: str) -> bool:
    o = ord(ch)
    return (
        0xAC00 <= o <= 0xD7A3  # 한글 완성형
        or 0x1100 <= o <= 0x11FF  # 한글 낱자
        or 0x3130 <= o <= 0x318F  # 한글 호환 낱자(ㄱ, ㅏ, ㆍ …)
        or ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9")
        or ch.isspace()
        or ch in ALLOWED_PUNCT
    )


def _char_kind(ch: str) -> str:
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF or o >= 0x20000:
        return "한자"
    if 0x3040 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9F:
        return "일본어 글자"
    if o in (0x200D, 0xFE0E, 0xFE0F) or unicodedata.category(ch) in ("Cf", "Mn", "Cc"):
        return "보이지 않는 글자"
    if 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or unicodedata.category(ch) == "So":
        return "이모지·기호"
    return "허용하지 않는 문자"


def _v12_charset(text: str, rules: ValidatorRules) -> CheckResult:
    body = _strip_markers(text, rules)  # 설정한 표기·브랜드 이름은 그대로 둔다
    bad = list(dict.fromkeys(ch for ch in body if not _allowed_char(ch)))
    if not bad:
        return _check("V12", True, "한글·영문·숫자·기본 문장부호만 씀")
    shown = []
    for ch in bad[:5]:
        kind = _char_kind(ch)
        label = f"U+{ord(ch):04X}" if kind == "보이지 않는 글자" else ch
        shown.append(f"'{label}'({kind})")
    more = f" 외 {len(bad) - 5}개" if len(bad) > 5 else ""
    return _check(
        "V12", False,
        f"쓸 수 없는 글자가 있습니다: {', '.join(shown)}{more} — 지우거나 한글로 바꾸세요",
    )


def _v11_previous(text: str, previous_texts: Sequence[str], rules: ValidatorRules) -> CheckResult:
    body_n = normalize(_strip_markers(text, rules))
    best, best_text = 0.0, ""
    for prev in previous_texts:
        prev_n = normalize(_strip_markers(unicodedata.normalize("NFC", prev or ""), rules))
        if not prev_n or not body_n:
            continue
        ratio = SequenceMatcher(None, body_n, prev_n, autojunk=False).ratio()
        if ratio > best:
            best, best_text = ratio, prev
    if best >= PREVIOUS_SIMILARITY:
        shown = _clip(_strip_markers(best_text, rules).strip(), 20)
        return _check(
            "V11", False,
            f"이전 글 '{shown}'와 {best:.0%} 비슷합니다 — 이 영상의 장면·말로 새로 쓰세요",
        )
    if not previous_texts:
        return _check("V11", True, "비교할 이전 글 없음")
    return _check(
        "V11", True, f"이전 글 {len(previous_texts)}개와 비교 · 가장 비슷한 것 {best:.0%}"
    )


# ---------------------------------------------------------------- 전체 검사


def validate(
    text: str,
    *,
    context_text: str,
    rules: ValidatorRules,
    brand_facts: Sequence[str],
    previous_texts: Sequence[str],
    evidence_quote: str | None = None,
    disclosure_required: bool = True,
) -> Validation:
    """V1~V12를 모두 돌린다. 하나라도 실패하면 `passed=False`.

    - `disclosure_required`: 거짓이면 V4가 표기 없는 글도 「표기 끔」으로 통과시킨다(R3: 초안의
      「광고 표기 붙이기」를 끈 경우. 어떤 영상이든)

    - `context_text`: 대조할 영상 자료 전체(3단계 `search_text`: 제목·설명·자막·댓글, 자르지 않음)
    - `previous_texts`: 이전에 승인·게시한 글들(V11). 5단계 전까지는 빈 목록
    - `evidence_quote`: AI가 고른 근거 구절(5단계). 없으면 `find_evidence`로 찾는다
    """
    clean = unicodedata.normalize("NFC", text or "").strip()
    facts_n = [normalize(f) for f in brand_facts if f and f.strip()]

    v6, v7, quote = _v6_v7_evidence(clean, context_text or "", rules, evidence_quote)
    quoted = _quoted_spans(clean, context_text or "", rules)
    checks = (
        _v1_length(clean, rules),
        _v2_links(clean),
        _v3_hashtags(clean),
        _v4_disclosure(clean, rules, required=disclosure_required),
        _v5_brand(clean, rules),
        v6,
        v7,
        _pattern_check(
            "V8", clean, rules,
            "직접 이용한 후기처럼 읽힙니다. 영상 내용에 공감하는 말로 바꾸세요",
            quoted=quoted,
        ),
        _pattern_check(
            "V9", clean, rules,
            "지어낸 연애 사연(내 애인 이야기)입니다. 영상에 대한 반응과 공감으로 바꾸세요",
            quoted=quoted,
        ),
        _pattern_check(
            "V10", clean, rules,
            "확인할 수 없는 효능·최상급입니다. 빼거나 brand.facts의 사실로 바꾸세요",
            facts_n,
            quoted=quoted,
        ),
        _v11_previous(clean, previous_texts, rules),
        _v12_charset(clean, rules),
    )
    return Validation(
        passed=all(c.passed for c in checks),
        checks=checks,
        char_count=len(clean),
        evidence_quote=quote,
    )
