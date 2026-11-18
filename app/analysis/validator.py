"""댓글 규칙 검사 V1~V6·V8~V11 (docs/COMMENT_REFACTOR.md 5절, 2026-11-18 리팩토링).

네트워크·DB·LLM 없이 도는 순수 함수다. AI가 쓴 초안과 사람이 고친 글이 **같은 함수**를 거친다.
게시를 막는 검사는 이것뿐이다. 말투·짜임·문장 조각은 보지 않는다(예전 V7·V12·V13·V14 삭제,
V14의 지어낸 평판 검사는 V10에 합쳤다). 검사 번호는 저장된 예전 결과와 맞추려고 바꾸지 않았다.

- `validate(text, ...)` → `Validation(passed, checks, char_count, evidence_quote)`
- `find_evidence(text, context_text)` → 글과 영상 자료에 함께 나오는 가장 긴 구절(원문 그대로)
- `quote_in_context(quote, context_text)` → 구절이 영상 자료에 있는가(V6과 같은 기준, 분석이 씀)
- `normalize(s)` → 대조용 글: NFC, 소문자, 글자·숫자만 남김
- `usable_key_phrases`·`derive_key_phrases`·`strip_hashtags` → 영상 분석이 쓴다

실패 문구는 "무엇이 걸렸고 → 어떻게 고치면 되는지"를 한 줄로 쓴다. 화면과 다시 쓰기 프롬프트가
같은 문구를 쓴다. 글자 수는 NFC로 맞춘 뒤의 코드 포인트 수이고 광고 표기는 빼고 센다.
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
MIN_KEY_PHRASE_CHARS = 2  # 핵심 말(분석): 정리 후 2자 이상
MAX_KEY_PHRASE_CHARS = 10  # 핵심 말(분석): 정리 후 10자 이하
QUOTE_SIMILARITY = 0.85  # V6: 근거 구절이 그대로 없으면 이만큼 비슷한 구간이 있어야 한다
# V11: 이전 글과 글 전체가 이만큼 같으면 「사실상 같은 글」(2026-11-18 리팩토링: 0.6 → 0.8.
# 운명원 대목이 닮은 것만으로는 걸리지 않게)
PREVIOUS_SIMILARITY = 0.8
BRAND_GAP = 8  # 따옴표로 옮긴 영상 속 말: 앞뒤 이만큼 안에 브랜드가 있으면 V8~V10 면제 없음
FACT_EXTRA_CHARS = 3  # V10: 걸린 말 앞뒤로 이만큼 더 brand.facts와 똑같으면 사실 문장으로 본다
_FIND_MIN = 2  # find_evidence: 정리 후 이보다 짧은 겹침은 구절로 치지 않는다

CHECK_NAMES: dict[str, str] = {
    "V1": "길이 40~120자 · 한 줄",
    "V2": "링크 없음",
    "V3": "해시태그 없음",
    "V4": "홍보 표기 맨 앞",
    "V5": "운명원 1~2번 · 연애 사주",
    "V6": "짚은 구절이 영상 자료에 있음",
    "V8": "가 본 척하는 후기 없음",
    "V9": "지어낸 구체적 연애 사연 없음",
    "V10": "효능 단정·지어낸 평판 없음",
    "V11": "이전 글과 다름",
}
PATTERN_CODES = ("V8", "V9", "V10")

# ---------------------------------------------------------------- 표현 목록(정규식)
# 과하게 잡는 쪽이 안전하다(걸리면 다시 만들면 된다). 다만 정상 표현("공감돼요", "상담받아
# 보세요")과 시청자 말투의 의향·들은 평판("저도 한번 보고 싶네요", "잘 본다던데", "잘 맞는다고
# 하던데", "친구가 … 봤는데 잘 맞는다고 하던데")은 걸리지 않게 한다 — 테스트로 확인한다.
# 막는 것은 써 본 척(V8), 지어낸 애인 이야기(V9), 효능 단정(V10)이다(2026-11-17 시청자 말투
# 전환, 과제 PDF 기준).

LINK_PATTERNS: tuple[str, ...] = (
    r"https?",
    r"www\s?[.．。]",
    r"[0-9a-z가-힣_-]+\s?[.．。]\s?(?:com|kr|net|co|io|me|app|shop)(?![a-z])",
    r"닷\s?컴",
)

# 「상담받아 보고 싶어요」「상담받아보려구요」「상담받아 볼까」「상담받고 싶어요」「상담받으러」
# 같은 권유·의향은 뺀다(2026-11-17 대표 본보기: 「저도 기회 되면 상담받아보고 싶어요」)
_CONSULTED = (
    r"상담\s?받(?!\s?아\s?(?:보(?:세요|시|셔|실|고\s?싶|려|면)|볼|봐야|봐\s?보)|고\s?싶|"
    r"을\s?(?:수|까)|으실|으러|으려|기)"
)
# 「직접 알아보고 싶어요」「직접 가 보려고요」처럼 뒤에 의향이 오면 써 본 척이 아니다
_NOT_INTENT = r"(?![^.!?…,]{0,12}?(?:려[고구]|고\s?싶|볼까|생각|야겠|야지))"

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
    r"봤더니",
    # 권하는 말·의향은 뺀다: 상담받아 보세요·상담받아보시는·상담받아 보고 싶다·상담받을 수·
    # 상담받으실·상담받으러 오세요·상담받기·상담받아보려구요
    _CONSULTED,
    r"예약\s?(?:했|해\s?놨|해\s?뒀|함|완료)",
    # 「후기가 많던데」는 들은 평판(2026-11-18 대표 의견)이라 뺀다 — 내 후기·「후기 남겨요」는
    # 그대로 막는다
    r"후기(?!\s?(?:가|도|들이)\s?(?:많|자자))",
    r"소름",
    r"맞더라",
    r"맞췄",
    r"맞추더",
    r"맞히",
    r"효과\s?(?:봤|를\s?봤|있었)",
    r"덕분에",
    r"직접\s?(?:가|받|봤|해\s?봤|상담)" + _NOT_INTENT,
    r"실제로\s?(?:가|받|봤|해\s?봤|상담)" + _NOT_INTENT,
)

# V9 지어낸 연애 사연(내 애인·전 애인 이야기). 시청자 말투의 공감·의향("저도 한번 보고 싶네요",
# "완전 제 얘기네요")은 과제 PDF가 원하는 페르소나라 막지 않는다(2026-11-17).
CONSUMER_PATTERNS: tuple[str, ...] = (
    r"(?<![가-힣])(?:제|내)\s?(?:남친|여친|남자\s?친구|여자\s?친구|애인|전\s?남친|전\s?여친)",
    r"우리\s?(?:남친|여친|오빠|자기)",
    # ⑤의 까닭으로 내 애인을 지어냄(2026-11-18): 「저도 남친이랑 싸워서」「나도 3년 만난 남친
    # 때문에」. 애인이 없다는 말·바람(「저도 남친 없어서」「나도 애인 생길지」)은 걸지 않는다.
    r"(?<![가-힣])(?:저도|나도)\s(?:[^.!?…,\s]+\s){0,2}(?:전\s?)?"
    r"(?:남친|여친|남자\s?친구|여자\s?친구|애인)"
    r"(?!\s*(?:이|가|은|는|도)?\s*(?:생기|생길|생겼|생긴|없|있었으면|만나|만날|사귀))",
)

# V10 확인할 수 없는 효능·최상급 표현
CLAIM_PATTERNS: tuple[str, ...] = (
    r"\d+\s?[%％]",
    r"퍼센트",
    r"무조건",
    r"반드시",
    r"보장",
    r"(?<!언)제일",  # "언제일지"는 최상급이 아니다(C1에서 찾음)
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
    r"잘\s?(?:맞혀|맞춰|맞히|맞추|맞췄|맞더)",  # 들은 얘기 꼴이면 통과(아래 REPUTATION_PATTERNS)
    r"신통",
    r"효과",
    r"효험",
    # 「용하다」는 남의 말로 옮겨도 막는다("용하대요").
    r"(?<![가-힣])용하",
    # 평판(운명원 페르소나 = 「연애 사주 잘 봐주는 곳으로 유명한 곳」, 과제 원문, 2026-11-17 대표):
    # 아래 셋은 **들은 얘기 꼴이면 통과**(「잘 맞는다고 하던데」「잘 맞는대요」「잘 본다던데」),
    # 내가 단정하면 실패(「잘 맞아요」「운명원은 잘 맞혀요」「잘 봐요」「잘 보는 곳이에요」).
    # 들은 얘기인지는 `REPUTATION_PATTERNS` + `_relayed_claim`이 본다.
    r"잘\s?맞(?:는다|는대|아요|아서|더|대)",
    r"(?:맞는|맞힌|맞춘)\s?(?:대요|대서|대더라|다네요|다니까|다던데|다더라)",
    r"잘\s?(?:봐요|봐서|봅니다|보더라|보시더라|보네요|봐\s?주(?:어요|더라|십니다|네요))",
    r"잘\s?(?:보는|봐\s?주는)\s?(?:곳|데)(?:이에요|예요|입니다|이야|야|이죠)",
)

# 들은 얘기 꼴이면 넘어가는 평판 표현(V10). 「무조건」「100%」「최고」「용하」는 들은 얘기도
# 막는다(과제 금지: 확인할 수 없는 효능 단정). 「정확」은 2026-11-17 대표 본보기(「연애사주가 꽤
# 정확하다는 얘기가 있더라구요」)로 들은 얘기 꼴이면 넘어간다 — 「정확해요」는 그대로 막는다.
REPUTATION_PATTERNS: frozenset[str] = frozenset({
    r"정확(?:하|히|한|도|해)",
    r"잘\s?(?:맞혀|맞춰|맞히|맞추|맞췄|맞더)",
    r"잘\s?맞(?:는다|는대|아요|아서|더|대)",
    r"(?:맞는|맞힌|맞춘)\s?(?:대요|대서|대더라|다네요|다니까|다던데|다더라)",
    r"잘\s?(?:봐요|봐서|봅니다|보더라|보시더라|보네요|봐\s?주(?:어요|더라|십니다|네요))",
    r"잘\s?(?:보는|봐\s?주는)\s?(?:곳|데)(?:이에요|예요|입니다|이야|야|이죠)",
})
# 남이 써 본 얘기를 전하면 넘어가는 이용 표현(V8): 「친구가 운명원에서 연애 사주 봤는데 잘 맞는다고
# 하던데」. 「후기」「소름」「덕분에」「예약했」「직접」「실제로」「맞더라」는 그대로 막는다.
RELAY_PATTERNS: frozenset[str] = frozenset({
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
    r"봤더니",
    _CONSULTED,
    r"맞췄",
    r"맞추더",
    r"맞히",
})
# 전하는 말: 「~다고 하던데」「~대요」「~라더라」「~다던데」「~다는 얘기」「~다는 이야기가
# 있던데」「~기로 유명」
HEARSAY_TAIL = re.compile(
    r"[다라]\s?고\s?(?:하|들|해|그러)|[다라]고들|[대래](?:요|서|더라|니까)|"
    r"[다라](?:던데|더라|네요|니까|길래|며|는데)|[다라]는\s?(?:얘기|이야기|말|소문|평|글)|"
    r"[단란]\s?(?:얘기|이야기|말|소문|평)|(?:기로|으로|로)\s?유명"
)
# 남(써 본 사람): 「친구가」「아는 언니가」「주변에서」「동생이」. 「우리 오빠」는 V9가 본다.
THIRD_PERSON = re.compile(
    r"(?<![가-힣])(?:친구|지인|주변|동생|언니|누나|형|동료|선배|후배|엄마|이모|고모|사촌|"
    r"아는\s?(?:사람|분|언니|동생|형|누나|오빠)|회사\s?사람|친한\s?(?:언니|동생|친구|형|누나))"
    r"(?:들)?(?:이|가|도|는|분|네|한테서|한테|에서|께서)?(?![가-힣])"
)
FIRST_PERSON = re.compile(r"(?<![가-힣])(?:제가|내가|저도|나도|저는|나는|전|난)(?![가-힣])")
_CLAUSE_END = re.compile(r"[.!?…\n]|(?<=[ㄱ-ㅎㅏ-ㅣ])\s")

BUILTIN_PATTERNS: dict[str, tuple[str, ...]] = {
    "V8": REVIEW_PATTERNS,
    "V9": CONSUMER_PATTERNS,
    "V10": CLAIM_PATTERNS,
}


# ---------------------------------------------------------------- 결과 모양


@dataclass(frozen=True)
class CheckResult:
    code: str  # V1~V6, V8~V11
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


# ---------------------------------------------------------------- 핵심 말(C1)

# 어느 연애 영상에나 나오는 흔한 낱말. 이것 하나만으로는 「그 영상의 핵심 말」이 아니다(분석).
# 낱말 그대로만 본다 — '남자심리'처럼 붙여 쓴 말은 그 영상의 주제일 수 있어 막지 않는다(과제 예시).
COMMON_WORDS = frozenset(
    """
    연애 사랑 남자 여자 영상 마음 사람 고민 관계 연락 이별 썸 결혼 인연
    사주 운세 궁합 애인 남친 여친 남자친구 여자친구 커플 연인 친구 오늘
    진짜 정말 이야기 얘기 생각 심리 상대 상대방 우리 저 나 너 그 이
    저도 나도 매일 그냥 너무 완전 근데 그런데 그래서 사연 상담 구독 댓글
    채널 시청 시청자 유튜브 방송 라이브 감정 행복 이유 시간 때문 정도
    하루 지금 요즘 사이 데이트 만남 남녀 연애심리 연애상담 연애고민 연애운 문제 자주
    여러분 우리들 모두 하나 일상 인생 오늘의 이번 다음 처음 마지막 방법
    특징 분석 정리 내용 것 것들 거 수 때 곳 분 누구 무엇 뭐 어디 언제
    어떻게 왜 이런 그런 저런 아주 많이 조금 여러 가지 여러가지 이것 그것
    저것 우리가 제가 내가 사실 계속 항상 자꾸 다시 먼저 혼자 같이 함께
    서로
    """.split()
)
# 낱말 끝의 조사(긴 것부터). 떼고 남은 말이 2자 이상일 때만 뗀다.
_PARTICLES = (
    "에서는", "에게는", "이라고", "으로", "에서", "에게", "한테", "까지", "부터", "처럼", "보다",
    "라고",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "와", "과", "랑", "로", "만",
)
# 말끝이 이렇게 끝나면 낱말이 아니라 풀이말(서술어)로 본다(뽑을 때만 쓴다)
_VERBISH = (
    "다", "요", "죠", "까", "데", "고", "면", "서", "지", "게", "네", "니", "며", "던", "는", "은",
    "을",
)
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_HASHTAG = re.compile(r"[#＃]([0-9A-Za-z가-힣_]{2,20})")
_HASHTAG_TOKEN = re.compile(r"[#＃][^\s#＃]+")


def strip_hashtags(text: str) -> str:
    """글에서 해시태그(#낱말)를 뺀다(2026-11-18). 해시태그 낱말은 핵심 말·댓글 재료가 아니다 —
    설명란 「#인팁특징」이 핵심 말로 뽑혀 댓글에 「인팁특징」이 들어갔다."""
    out = _HASHTAG_TOKEN.sub(" ", unicodedata.normalize("NFC", text or ""))
    return "\n".join(" ".join(line.split()) for line in out.split("\n")).strip()


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if word.endswith(p) and len(word) - len(p) >= 2:
            return word[: -len(p)]
    return word


def is_common_word(phrase: str) -> bool:
    """흔한 낱말 하나인가(조사를 떼고 본다). 정리한 글로 비교한다."""
    n = normalize(phrase)
    return not n or n in COMMON_WORDS or _strip_particle(n) in COMMON_WORDS


# 2026-11-18(대표 시연 초안 「을이 되지 말고라니」): 자동 자막에서 말하다 만 토막을 핵심 말로 뽑으면
# 초안이 그 끝에 어미를 바로 붙였다. 두 낱말 이상이고 마지막 낱말이 이어 주는 끝으로 끝나면 뺀다.
CUT_ENDINGS = ("고", "서", "면", "는데", "은데", "지만", "니까", "려고", "도록", "거나")


def is_cut_fragment(phrase: str) -> bool:
    """말하다 만 토막인가(「을이 되지 말고」「기갑부터 잡고」).

    한 낱말(「최고」「사고」)은 보지 않는다.
    """
    words = unicodedata.normalize("NFC", phrase or "").split()
    return len(words) >= 2 and len(words[-1]) >= 2 and words[-1].endswith(CUT_ENDINGS)


def key_phrase_ok(phrase: str, context_n: str, rules: ValidatorRules | None = None) -> bool:
    """핵심 말로 쓸 수 있는가: 정리 후 2~10자, 흔한 낱말 하나가 아님, 말하다 만 토막이 아님,
    표기·브랜드가 아님, 영상 자료(정리한 글)에 그대로 있음."""
    n = normalize(phrase)
    if not (MIN_KEY_PHRASE_CHARS <= len(n) <= MAX_KEY_PHRASE_CHARS):
        return False
    if is_common_word(phrase) or is_cut_fragment(phrase):
        return False
    if rules is not None:
        for marker in (rules.brand, rules.disclosure):
            if marker and normalize(marker) and normalize(marker) in n:
                return False
    return n in context_n


def usable_key_phrases(
    phrases: Iterable[str], context_text: str, rules: ValidatorRules | None = None
) -> list[str]:
    """핵심 말 중 쓸 수 있는 것(원래 모양 그대로, 같은 말은 하나). 분석이 쓴다."""
    context_n = normalize(context_text)
    out: list[str] = []
    seen: set[str] = set()
    for raw in phrases:
        phrase = " ".join(str(raw or "").split()).strip("'\"‘’“”「」#")
        key = normalize(phrase)
        if key in seen or not key_phrase_ok(phrase, context_n, rules):
            continue
        seen.add(key)
        out.append(phrase)
    return out


def hashtags(text: str, limit: int = 12) -> list[str]:
    """글 속 해시태그 낱말(# 뺀 것, 앞에서부터)."""
    return list(dict.fromkeys(_HASHTAG.findall(unicodedata.normalize("NFC", text or ""))))[:limit]


def derive_key_phrases(
    texts: Iterable[str], context_text: str, rules: ValidatorRules | None = None, limit: int = 6
) -> list[str]:
    """핵심 말 목록이 없을 때(예전 분석, 모델이 고른 핵심 말이 모두 버려졌을 때) 코드로 뽑는다.

    `texts`(제목·해시태그 순)를 낱말로 나눠 조사를 떼고, 흔한 낱말·풀이말·영상 자료에 없는 말을
    뺀다. 말하다 만 자막 문장은 넣지 않는다(풀이말 조각이 핵심 말로 뽑힌다).
    """
    words: list[str] = []
    for text in texts:
        for token in _TOKEN.findall(unicodedata.normalize("NFC", text or "")):
            word = _strip_particle(token)
            if word.endswith(_VERBISH) and not token.isascii():
                continue
            words.append(word)
    return usable_key_phrases(words, context_text, rules)[:limit]


# ---------------------------------------------------------------- 규칙별 검사


def _check(code: str, passed: bool, message: str) -> CheckResult:
    return CheckResult(code=code, name=CHECK_NAMES[code], passed=passed, message=message)


def _length_without_mark(text: str, mark: str) -> int:
    """글자 수(홍보 표기와 그 뒤 한 칸은 빼고 센다 — 2026-11-18 대표: 「[광고]는 빼고 120자」)."""
    if mark and text.startswith(mark):
        text = text[len(mark):].lstrip()
    return len(text)


def _v1_length(text: str, rules: ValidatorRules) -> CheckResult:
    n = _length_without_mark(text, rules.disclosure)
    lo, hi = rules.min_chars, rules.max_chars
    problems: list[str] = []
    if "\n" in text or "\r" in text:
        problems.append("줄바꿈이 있습니다 — 한 줄로 이어 쓰세요")
    if n < lo:
        problems.append(f"{n}자로 짧습니다({lo}~{hi}자, 표기 빼고) — {lo - n}자 이상 늘리세요")
    elif n > hi:
        problems.append(f"{n}자로 깁니다({lo}~{hi}자, 표기 빼고) — {n - hi}자 이상 줄이세요")
    if problems:
        return _check("V1", False, " / ".join(problems))
    return _check("V1", True, f"{n}자(표기 빼고, {lo}~{hi}자) · 한 줄")


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
    """V5 브랜드 이름 1~2번, 그리고 글 안에 '연애'와 '사주'가 둘 다 있다(「연애 사주」·「연애사주」·
    「연애 쪽 사주」·「사주로 연애운」 모두 된다)."""
    brand = rules.brand
    count = text.count(brand) if brand else 0
    if count == 0:
        return _check("V5", False, f"브랜드 이름 '{brand}'이(가) 없습니다 — 한 번 넣으세요")
    if count > 2:
        return _check("V5", False, f"'{brand}'이(가) {count}번 나옵니다 — 1~2번으로 줄이세요")
    if not ("연애" in text and "사주" in text):
        return _check("V5", False, f"'{brand}' 연애 사주 얘기가 없습니다 — 함께 말하세요")
    return _check("V5", True, f"'{brand}' {count}번 · 연애 사주")


def _v6_evidence(
    text: str, context_text: str, rules: ValidatorRules, evidence_quote: str | None
) -> tuple[CheckResult, str | None]:
    body = _strip_markers(text, rules)
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

    return v6, quote or None



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


def _sentence_at(text: str, start: int, end: int) -> tuple[int, int]:
    """[start, end)를 품은 문장의 범위(마침표류·ㅠㅠ 뒤 띄어쓰기로 자른다)."""
    left = 0
    for m in _CLAUSE_END.finditer(text, 0, start):
        left = m.end()
    stop = _CLAUSE_END.search(text, end)
    return left, (stop.start() if stop else len(text))


def _relayed_claim(text: str, start: int, end: int) -> bool:
    """V10 평판 표현이 들은 얘기 꼴인가: 그 말부터 같은 문장 안 몇 자 뒤까지 전하는 말이 있다.

    「잘 맞는다고 하던데」「잘 맞는대요」「잘 맞힌다는 얘기」는 들은 얘기, 「잘 맞아요」「잘 봐요」
    는 내 단정이다.
    """
    _, stop = _sentence_at(text, start, end)
    window = text[start : min(stop, end + 8)]
    return bool(HEARSAY_TAIL.search(window))


def _relayed_use(text: str, start: int, end: int) -> bool:
    """V8 이용 표현이 남이 써 본 얘기를 전하는 꼴인가.

    같은 문장에서 그 말 앞에 남(친구·지인·주변·동생·언니 …)이 있고, 그 사이에 나(제가·저도 …)가
    없고, 그 말 뒤에 전하는 말(~다고 하던데·~대요·~라더라·~다던데)이 있어야 한다.
    「친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데」는 통과, 「제가 운명원에서 봤는데
    잘 맞더라고요」「친구랑 같이 봤는데 좋았어요」는 실패.
    """
    left, stop = _sentence_at(text, start, end)
    before = text[left:start]
    who = list(THIRD_PERSON.finditer(before))
    if not who:
        return False
    if FIRST_PERSON.search(before[who[-1].end():]):
        return False
    return bool(HEARSAY_TAIL.search(text[end:stop]))


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
            if code == "V10" and pattern.pattern in REPUTATION_PATTERNS and _relayed_claim(
                text, m.start(), m.end()
            ):
                continue  # 들은 평판(「잘 맞는다고 하던데」)
            if code == "V8" and pattern.pattern in RELAY_PATTERNS and (
                _relayed_use(text, m.start(), m.end())
                or (pattern.pattern in (r"맞췄", r"맞추더", r"맞히")
                    and _relayed_claim(text, m.start(), m.end()))
            ):
                continue  # 남이 써 본 얘기를 전함(「친구가 … 봤는데 잘 맞는다고 하던데」)
            hits.append(m.group(0))
    if hits:
        return _check(code, False, f"걸린 말 {_found(hits)} — {hint}")
    return _check(code, True, "걸린 표현 없음")


def _v11_previous(
    text: str, previous_texts: Sequence[str], rules: ValidatorRules
) -> CheckResult:
    """V11 이전 글과 사실상 같은 글이 아닌가(2026-11-18 리팩토링: 글 전체만 본다).

    비교 대상은 다른 영상에서 승인·게시한 글. 표기와 브랜드 이름은 빼고 정리한 글끼리
    `PREVIOUS_SIMILARITY` 이상이면 실패. 운명원 대목이 닮은 것만으로는 걸리지 않게 높게
    둔다."""
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
            f"이전 글 '{shown}'와 {best:.0%} 같습니다 — 이 영상의 장면과 내 고민으로 새로 쓰세요",
        )
    if not previous_texts:
        return _check("V11", True, "비교할 이전 글 없음")
    return _check(
        "V11", True, f"이전 글 {len(previous_texts)}개와 비교 · 가장 비슷한 것 {best:.0%}"
    )


# 2026-11-18(기획 담당 · 대표 의견): 운명원 대목(이름이 든 문장과 그다음 문장)에 과제 설정에 없는 새
# 평판·사례를 지어내지 않는다(V10). brand.facts에 그대로 있는 말은 된다.
# 문장 끝: 마침표류, 또는 ㅠㅠ·ㅋㅋ 뒤의 띄어쓰기(댓글은 마침표 없이 이어 쓴다)
_SENTENCE_SPLIT = re.compile(r"[.!?…\n]+|(?<=[ㄱ-ㅎㅏ-ㅣ])\s+")
INVENTED_REPUTE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("예약·대기", re.compile(
        r"예약|대기\s?(?:가|도|해|하|시간|줄)|웨이팅|줄\s?(?:서|을\s?서|이\s?길)|밀렸|밀려\s?있")),
    ("방송·출연", re.compile(
        r"방송|티\s?비|(?<![A-Za-z])[Tt][Vv](?![A-Za-z])|유튜브|출연|매스컴|기사\s?(?:났|가\s?났|에\s?나)")),
    ("연예인", re.compile(r"연예인|아이돌|배우(?!자)|셀럽|유명인|인플루언서")),
    ("가격", re.compile(
        r"가격|비용|저렴|비싸|(?<![가-힣])싸(?:다|고|던|요|더|서)|\d+\s?만?\s?원|할인|무료|공짜")),
    ("위치", re.compile(r"위치|(?:역|동네)\s?(?:근처|앞)|강남|홍대|신촌|압구정|성수")),
    ("경력", re.compile(r"경력|전통|\d+\s?대째|\d+\s?년\s?(?:경력|전통|넘게|이상)")),
    ("적중률", re.compile(r"적중|확률|\d+\s?[%％]|퍼센트|\d+\s?(?:번|개|명)\s?중")),
    ("구체 사례", re.compile(
        r"재회(?:했|시켜|하게\s?해|됐|성공)|결혼\s?(?:날짜|시기|날)|"
        r"(?:날짜|시기|이름|나이|생일|띠)(?:을|를|도|까지)?\s?(?:다\s?)?"
        r"(?:맞혔|맞췄|맞혀|맞춰|맞히|맞추|맞았)|"
        r"(?<![가-힣])다\s?(?:맞혔|맞췄|맞혀|맞춰|맞히|맞추|맞는|맞아|맞았)")),
)
# 나나 아는 사람이 직접 받아 본 결과(「친구가 봤는데 다 맞혔다던데」). 친구·주변은
# 「추천하던데」까지만
_OTHERS_USED = re.compile(
    r"봤는데|봤더니|봐\s?봤|받아\s?봤|받았|받고\s?왔|다녀\s?왔|다녀\s?온|다녀\s?갔|갔다\s?왔|"
    r"가\s?봤|보고\s?왔|봤대|봤다"
)


def invented_repute(sentence: str, facts_n: Sequence[str] = ()) -> tuple[str, str] | None:
    """문장 하나에서 설정에 없는 새 평판·사례 (종류, 걸린 말). 없으면 None. brand.facts에 그대로
    있는 말(`facts_n`: normalize한 사실 문장)은 넘어간다."""
    for label, pattern in INVENTED_REPUTE:
        for m in pattern.finditer(sentence):
            word = m.group(0)
            if facts_n and any(normalize(word) in f for f in facts_n):
                continue
            return label, word
    for who in THIRD_PERSON.finditer(sentence):
        rest = sentence[who.end():]
        me = FIRST_PERSON.search(rest)
        m = _OTHERS_USED.search(rest[: me.start()] if me else rest)
        if m:
            return "받아 본 결과", who.group(0) + " … " + m.group(0)
    return None



def brand_invented(
    text: str, brand: str, disclosure: str = "", facts_n: Sequence[str] = ()
) -> tuple[str, str] | None:
    """운명원 대목(이름이 든 문장과 그다음 문장)의 새 평판·사례(`invented_repute`)."""
    body = text.replace(disclosure, " ") if disclosure else text
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(body) if p and p.strip()]
    for i, p in enumerate(parts):
        if brand and brand in p:
            for s in parts[i : i + 2]:
                found = invented_repute(s, facts_n)
                if found:
                    return found
    return None



def _v10_claims(
    text: str, rules: ValidatorRules, facts_n: list[str], quoted: Sequence[tuple[int, int]]
) -> CheckResult:
    """V10 효능 단정·최상급(표현 목록) + 운명원 대목의 지어낸 평판·사례(예전 V14를 합침)."""
    v10 = _pattern_check(
        "V10", text, rules,
        "확인할 수 없는 효능·최상급입니다. 빼거나 brand.facts의 사실로 바꾸세요",
        facts_n,
        quoted=quoted,
    )
    if not v10.passed:
        return v10
    invented = brand_invented(text, rules.brand, rules.disclosure, facts_n)
    if invented:
        label, word = invented
        return _check(
            "V10", False,
            f"'{rules.brand}'에 대해 설정에 없는 평판·사례({label}: '{word}')가 있습니다 — "
            "연애 사주를 잘 보기로 유명하다는 것만 말하세요",
        )
    return v10


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
    """V1~V6·V8~V11을 모두 돌린다. 하나라도 실패하면 `passed=False`(게시를 막는 검사는 이것뿐).

    - `context_text`: 대조할 영상 자료 전체(3단계 `search_text`: 제목·설명·자막·댓글, 자르지 않음)
    - `previous_texts`: 이전에 승인·게시한 글들(V11)
    - `evidence_quote`: 초안이 짚은 영상 구절(AI가 돌려준 `used_quote`). 없으면 글에서 찾는다(V6)
    - `disclosure_required`: 거짓이면 V4가 표기 없는 글도 「표기 끔」으로 통과시킨다(R3)
    """
    clean = unicodedata.normalize("NFC", text or "").strip()
    facts_n = [normalize(f) for f in brand_facts if f and f.strip()]

    v6, quote = _v6_evidence(clean, context_text or "", rules, evidence_quote)
    quoted = _quoted_spans(clean, context_text or "", rules)
    checks = (
        _v1_length(clean, rules),
        _v2_links(clean),
        _v3_hashtags(clean),
        _v4_disclosure(clean, rules, required=disclosure_required),
        _v5_brand(clean, rules),
        v6,
        _pattern_check(
            "V8", clean, rules,
            "가 본 적 있는 후기처럼 읽힙니다. 아직 안 가 본 사람의 말로 바꾸세요",
            quoted=quoted,
        ),
        _pattern_check(
            "V9", clean, rules,
            "지어낸 구체적 연애 사연(내 애인 이야기)입니다. 내 처지는 한마디로만 말하세요",
            quoted=quoted,
        ),
        _v10_claims(clean, rules, facts_n, quoted),
        _v11_previous(clean, previous_texts, rules),
    )
    return Validation(
        passed=all(c.passed for c in checks),
        checks=checks,
        char_count=len(clean),
        evidence_quote=quote,
    )
