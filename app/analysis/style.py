"""초안 다듬기 검사(C1 다듬기, 2026-11-17 대표 지시 「초안 더 다듬고」).

규칙 검사(V1~V14)를 통과한 초안 가운데 **읽기에 어색한 꼴**을 코드로 찾는다. 이 검사는 승인을
막지 않는다 — 모델이 쓴 초안을 한 번 더 쓰게 하는 까닭(다시 쓸 차례가 남았을 때)과 다듬기
단계(`prompts.polish_user`)에 넘길 「남은 문제」로만 쓴다. 사람이 고친 글에는 쓰지 않는다.

- S1 길이: 전체 110자를 넘음(목표 70~105자, 한도 40~120자는 V1 그대로)
- S2 바람에 핵심 말: 운명원 문장(바람)에 영상의 핵심 말을 끼움
  (「내짝 찾기 언제 되는지 궁금해지네요」)
- S3 띄어쓰기·말꼴: 「이유여쭤보고」처럼 붙여 씀, 「없었네라는 말에」처럼 말끝에 바로 「라는」
- S4 같은 영상 앞 초안과 비슷함: [다른 댓글 만들기]가 거의 같은 글을 내지 않게
- S5 영상 사연을 내 것으로: 영상 속 **숫자**(「3년 사귄」「2년째」「석 달」)를 영상 얘기라는
  표지(「~대요」「~라니」「~다는 말에」) 없이 내 일처럼 옮긴 문장. 비슷한 처지라고 말하는 것
  (「완전 제 얘기네요」「저도 비슷해서」「우리 사이」)은 시청자 말투로 둔다(기획 담당 2026-11-17:
  막을 것은 사연 복사와 내 일이 될 수 없는 것 둘뿐 — 뒤의 것은 프롬프트로만 막는다).

S3는 「~인지 한번 가 봐야겠어요」(「언제인지 한번 가 봐야겠네요」)와 「제 연애 운세 한번 가
봐야겠네요」도 잡는다 — 「가 봐야겠다」는 물음도, 운세·시기 같은 목적어도 받지 못한다
(「~인지 한번 보고 싶다」, 「궁금해서 다음에 한번 가 봐야겠네요」로). 1~7회차 초안 112개에
대 보니 목적어 꼴은 「연애 운세 한번 가 봐야겠네요」 2개만 걸렸다.

문구는 규칙 검사처럼 「무엇이 걸렸고 — 어떻게 고치면 되는지」 한 줄이다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.analysis.validator import contains_key_phrase, normalize

SOFT_MAX_TOTAL = 110
# 1~5회차 실제 초안: 다른 영상 초안끼리 가장 닮은 것이 0.55, 같은 영상 두 초안은 0.18~0.67,
# 대표가 본 영상의 두 초안은 0.94였다. 다른 영상 글만큼도 다르지 않으면 다시 쓰게 한다.
SAME_VIDEO_SIMILARITY = 0.55

_SPLIT = re.compile(r"[.!?…\n]+|(?<=[ㄱ-ㅎㅏ-ㅣ])\s+")
_WISH = re.compile(
    r"싶|봐야|볼까|가\s?볼|궁금|물어보|여쭤|알아보|보려고|볼래|해\s?볼|받아\s?보|할까|보자|좋겠"
)
# 붙여 쓴 꼴: 앞말에 바로 붙은 「여쭤보·물어보·알아보」(되물어보·캐물어보는 한 낱말)
_GLUED = re.compile(r"(?<=[가-힣])(?<![되캐])(여쭤보|물어보|알아보)")
# 말끝(~네)에 바로 붙은 「라는 말」: 「없었네라는 말에」 → 「없었다는 말에」
_NE_RANEUN = re.compile(r"[가-힣]*네라는\s?말")
# 「~인지/~는지/~ㄹ지 (한번) 가 봐야겠다」: 물음 뒤에 「가 봐야」(사이에 「궁금해서」 등이 있으면
# 괜찮다)
_ASK_GO = re.compile(r"[가-힣]+지\s+((?:[가-힣]+\s+){0,3}?)가\s?봐야")
_ASK_GO_OK = re.compile(r"궁금|싶어서|알고\s?싶|물어보러|보러|여쭈러")
# 「운세·시기 (한번) 가 봐야겠다」: 가는 곳이 아닌 것을 「가 봐야」의 목적어로
_THING_GO = re.compile(
    r"(?<![가-힣])(?:연애\s?)?(?:운세|연애운|시기|타이밍|궁합|사주|앞날|미래|결말)(?:을|를|도)?\s+"
    r"(?:(?:한번|한\s번|다음에|꼭|언제)\s+)*가\s?봐야"
)
# 영상 속 숫자: 「3년」「2년째」「6개월」「석 달」「두 달」
_NUMBER = re.compile(
    r"\d+\s?(?:년|개월|달|주|살|번|일|시간|명|월|차)|"
    r"(?<![가-힣])(?:한|두|세|석|넉|네|다섯|여섯|일곱|여덟|아홉|열)\s?달(?![라려리콤])"
)
# 영상 얘기로 받는 표지(이게 있으면 숫자를 옮겨도 내 일이 아니다)
_ABOUT_VIDEO = re.compile(
    r"말에|말이|대요|래요|댔|랬|대\b|래\b|라니|다니|다는|라는|던데|다고|라고|사연|영상|댓글|"
    r"그분|이분|(?:거|걸|글|영상|댓글|사연|얘기|말)\s?보니|듣고|봤는데|셨|시죠|시네|으시"
)
# 운명원 꺼내는 말의 표지(앞 초안과 같은 틀인지 볼 때)
HEARSAY_MARKS = (
    "잘 본다던데", "잘 본다고", "보이던데", "많이들 본다", "하던데", "눈에 띄던데", "들었", "소문",
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip()]


def _body(text: str, disclosure: str) -> str:
    rest = text.strip()
    if disclosure and rest.startswith(disclosure):
        rest = rest[len(disclosure):].strip()
    return rest


def wish_part(text: str, brand: str) -> str:
    """운명원을 꺼낸 뒤의 바람 대목: 브랜드 문장의 브랜드 뒤쪽(+ 바람이 없으면 다음 문장)."""
    sentences = _sentences(text)
    for i, s in enumerate(sentences):
        if brand and brand in s:
            part = s.split(brand, 1)[1]
            if not _WISH.search(part) and i + 1 < len(sentences):
                part += " " + sentences[i + 1]
            return part
    return ""


def hearsay_mark(text: str, brand: str) -> str:
    """운명원 문장에 쓴 꺼내는 말 표지(없으면 빈 글)."""
    for s in _sentences(text):
        if brand and brand in s:
            return next((m for m in HEARSAY_MARKS if m in s), "")
    return ""


def used_phrases(text: str, key_phrases: Sequence[str]) -> list[str]:
    return [k for k in key_phrases if k and contains_key_phrase(text, k)]


def style_issues(
    text: str,
    *,
    brand: str,
    disclosure: str,
    key_phrases: Sequence[str] = (),
    earlier: Sequence[str] = (),
    context: str = "",
    max_total: int = SOFT_MAX_TOTAL,
) -> list[str]:
    """다시 쓰게 할 까닭들(없으면 빈 목록).

    `earlier`: 같은 영상에 앞서 쓴 초안 글. `context`: 영상 자료 글(S5 숫자 대조, 없으면 S5를
    보지 않는다).
    """
    issues: list[str] = []
    body = _body(text, disclosure)
    if len(text) > max_total:
        issues.append(
            f"S1 길이: {len(text)}자로 깁니다 — {max_total}자 안으로 줄이세요(② 내 처지 한마디나 "
            "④ 마무리는 빼도 됩니다)"
        )
    wish = wish_part(body, brand)
    stuffed = [
        k for k in key_phrases
        if k and len(normalize(k)) >= 2 and contains_key_phrase(wish, k)
    ]
    if stuffed:
        shown = ", ".join(f"'{k}'" for k in stuffed[:2])
        issues.append(
            f"S2 바람에 핵심 말: {brand} 뒤의 바람에 핵심 말 {shown}을(를) 끼웠습니다 — 핵심 말은 "
            "영상 반응에만 쓰고, 바람은 '나도 언제 짝 만나는지', '이 사람이랑 이어질지'처럼 쉬운 "
            "내 말로 쓰세요"
        )
    glued = [m.group(0) for m in _GLUED.finditer(body)]
    spans = [body[max(0, m.start() - 2) : m.end() + 1] for m in _GLUED.finditer(body)]
    if glued:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{spans[0]}'처럼 붙여 썼습니다 — '이유 물어보고'처럼 띄어 쓰세요"
        )
    ne = _NE_RANEUN.search(body)
    if ne:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{ne.group(0)}'은 어색합니다 — '~했다는 말에'처럼 고치세요"
        )
    ask = next((m for m in _ASK_GO.finditer(body) if not _ASK_GO_OK.search(m.group(1))), None)
    if ask:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{ask.group(0)}'은 앞뒤가 안 맞습니다 — '~인지 한번 보고 싶다'로 "
            "쓰거나, 물음 없이 '다음에 한번 가 봐야겠네요'로 쓰세요"
        )
    thing = _THING_GO.search(body)
    if thing:
        issues.append(
            f"S3 띄어쓰기·말꼴: '{thing.group(0)}'은 어색합니다 — 운세·시기는 가는 곳이 아니니 "
            "'연애 운세 한번 보고 싶다'나 '다음에 한번 가 봐야겠네요'로 쓰세요"
        )
    copied = _copied_number(body, context, brand)
    if copied:
        issues.append(
            f"S5 영상 사연을 내 것으로: '{copied}'는 영상 속 사연의 숫자입니다 — 내 일처럼 "
            "옮기지 말고 '저도 오래 만나다 보니'처럼 숫자 없이 내 말로 쓰거나, '~했대요'처럼 "
            "영상 얘기로 받으세요(비슷한 처지라고 말하는 것은 괜찮습니다)"
        )
    issues += _same_video(body, brand=brand, disclosure=disclosure, key_phrases=key_phrases,
                          earlier=earlier)
    return issues


def _copied_number(body: str, context: str, brand: str) -> str:
    """영상 자료에 있는 숫자를 영상 얘기라는 표지 없이 쓴 문장의 그 숫자(없으면 빈 글)."""
    if not context:
        return ""
    ctx = normalize(context)
    for s in _sentences(body):
        if brand and brand in s:
            # 운명원을 꺼내는 들은 얘기(「~던데」)는 영상 얘기 표지가 아니다
            s = s.split(brand, 1)[0]
        if _ABOUT_VIDEO.search(s):
            continue
        for m in _NUMBER.finditer(s):
            if s[m.end():].lstrip().startswith(("이면", "면")):
                continue  # 「3년이면 진짜 식은 건지」: 영상 속 숫자를 두고 하는 말
            if normalize(m.group(0)) in ctx:
                return m.group(0)
    return ""


def _same_video(
    body: str, *, brand: str, disclosure: str, key_phrases: Sequence[str], earlier: Sequence[str]
) -> list[str]:
    def flat(t: str) -> str:
        rest = _body(t, disclosure)
        return normalize(rest.replace(brand, " ") if brand else rest)

    mine = flat(body)
    mark = hearsay_mark(body, brand)
    phrases = set(used_phrases(body, key_phrases))
    many = len([k for k in key_phrases if k]) >= 2
    for old in earlier:
        old_body = _body(old, disclosure)
        ratio = SequenceMatcher(None, mine, flat(old), autojunk=False).ratio()
        if ratio >= SAME_VIDEO_SIMILARITY:
            return [
                f"S4 앞 초안과 비슷함: 같은 영상의 앞 초안과 {round(ratio * 100)}% 같습니다 — 짚는 "
                "장면·핵심 말·말투·운명원 꺼내는 말·끝말을 바꿔 다른 글로 쓰세요"
            ]
        if mark and mark == hearsay_mark(old_body, brand):
            return [
                f"S4 앞 초안과 비슷함: 운명원을 앞 초안과 같은 말('{mark}')로 꺼냈습니다 — 다른 "
                "들은 얘기로 꺼내세요"
            ]
        if many and phrases and phrases == set(used_phrases(old_body, key_phrases)):
            shown = ", ".join(f"'{k}'" for k in sorted(phrases))
            return [
                f"S4 앞 초안과 비슷함: 앞 초안과 같은 핵심 말({shown})만 썼습니다 — 다른 핵심 말로 "
                "다른 장면을 짚으세요"
            ]
    return []
