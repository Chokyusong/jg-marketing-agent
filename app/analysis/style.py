"""초안 다듬기 검사(C1 다듬기, 2026-11-17 대표 지시 「초안 더 다듬고」).

규칙 검사(V1~V14)를 통과한 초안 가운데 **읽기에 어색한 꼴**을 코드로 찾는다. 이 검사는 승인을
막지 않는다 — 모델이 쓴 초안을 한 번 더 쓰게 하는 까닭(다시 쓸 차례가 남았을 때)과 다듬기
단계(`prompts.polish_user`)에 넘길 「남은 문제」로만 쓴다. 사람이 고친 글에는 쓰지 않는다.

- S1 길이: 전체 110자를 넘음(목표 70~105자, 한도 40~120자는 V1 그대로)
- S2 바람에 핵심 말: 운명원 문장(바람)에 영상의 핵심 말을 끼움
  (「내짝 찾기 언제 되는지 궁금해지네요」)
- S3 띄어쓰기·말꼴: 「이유여쭤보고」처럼 붙여 씀, 「없었네라는 말에」처럼 말끝에 바로 「라는」
- S4 같은 영상 앞 초안과 비슷함: [다른 댓글 만들기]가 거의 같은 글을 내지 않게
- S5 남의 일을 내 일로: 영상의 핵심 말이 든 장면을 「완전 내 얘기」라고 하거나(그 문장이나 바로
  앞 문장), 없는 애인과의 「우리 관계·사이·인연」. 6회차 사연 영상 초안 5개가 사연 속 일을 내 일처럼
  썼다. 막연한 「완전 제 얘기네요」 자체는 시청자 말투로 둔다(2026-11-17 결정, V9).

S3는 6회차에서 「~인지 한번 가 봐야겠어요」(「언제인지 한번 가 봐야겠네요」)도 잡는다 —
「가 봐야겠다」는 물음을 받지 못한다(「~인지 한번 보고 싶다」, 「궁금해서 다음에 한번 가
봐야겠네요」로).

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
# 남의 일을 내 일로: 영상 속 사연·말을 내 얘기라고 하거나, 없는 애인과의 관계를 「우리」로
_MY_STORY = re.compile(r"(?:완전|딱|진짜)?\s?(?:내|제)\s?얘기|(?:나|저)잖아")
_OUR = re.compile(r"우리\s?(?:관계|사이|인연|둘|커플|연애)|우리도")
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
    max_total: int = SOFT_MAX_TOTAL,
) -> list[str]:
    """다시 쓰게 할 까닭들(없으면 빈 목록). `earlier`: 같은 영상에 앞서 쓴 초안 글."""
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
    mine = _OUR.search(body) or _claimed_scene(body, key_phrases)
    if mine:
        issues.append(
            f"S5 남의 일을 내 일로: '{mine.group(0).strip()}' — 나는 영상을 본 사람입니다. 영상 속 "
            "사람의 일을 내 일로 만들지 말고 '보는 제가 다 답답하네', '남 일 같지 않네'처럼 보는 "
            "사람 자리에서 반응하세요(없는 애인과의 '우리 관계'도 쓰지 않습니다)"
        )
    issues += _same_video(body, brand=brand, disclosure=disclosure, key_phrases=key_phrases,
                          earlier=earlier)
    return issues


def _claimed_scene(body: str, key_phrases: Sequence[str]) -> re.Match[str] | None:
    """핵심 말이 든 장면(그 문장이나 바로 앞 문장)을 「내 얘기」라고 한 곳."""
    sentences = _sentences(body)
    for i, s in enumerate(sentences):
        m = _MY_STORY.search(s)
        if not m:
            continue
        near = " ".join(sentences[max(0, i - 1) : i + 1])
        if any(k and contains_key_phrase(near, k) for k in key_phrases):
            return m
    return None


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
