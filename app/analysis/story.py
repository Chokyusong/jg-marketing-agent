"""이야기처럼 쓰기(2026-11-18 대표 결정, 기획 담당 설계).

설정 `comment.writer`가 `story`(기본)이면 코드는 조각·말투·잇는 문장·까닭·글쓴이 처지를 정해 주지
않는다. AI가 영상을 보고 글쓴이 처지까지 스스로 정해 기·승·전·결로 통째로 쓰고, 코드는 내용만
확인한다. `pieces`는 그 전 방식(조각 맞추기)이고 코드와 시험을 그대로 둔다.

`story`에 남는 것은 셋뿐이다.
1. 규칙 검사(막는 것, `validator.validate(story=True)`) — V1~V13 그대로 + V14 넷(이름·연애 사주·
   들은 평판·보러 갈 뜻)과 「운명원은 첫 문장에 나오지 않는다」.
2. 나쁜 꼴 검사(`story_issues`, 다시 쓰게만 한다) — S1 길이 · S4 거의 똑같음(글 전체가 앞 글·
   본보기와 사실상 같거나, 운명원 문장이 글자까지 같음 — 비슷한 것은 괜찮다) · S5 영상 숫자를 내
   것으로 · S9 끝난 말에 조사 · S13 해시태그 낱말. 「ㅋㅋ.」는 `drafter.clean_body`가 지운다.
3. 맥락 일치 검증(`review.story_review_system`) — 같은 주제 · 한 목소리 · 벗어난 문장 · 자연스러운
   결론.
코드가 정해 준 것과 다르면 거르는 검사(조각 S15·잇는 문장 S11·S12·S16·S17·까닭 S18~S22·말투
배정)는 `story`에 하나도 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from app.analysis import style
from app.analysis.validator import normalize
from app.llm.prompts import fold

WRITER_STORY = "story"
WRITER_PIECES = "pieces"
WRITERS = (WRITER_STORY, WRITER_PIECES)
WRITER_LABELS = {WRITER_STORY: "이야기처럼(권장)", WRITER_PIECES: "조각 맞추기(예전)"}

# 프롬프트에 보여 줄 처지의 예(예일 뿐 — AI가 영상에 맞게 스스로 정하고, 안 맞으면 빼도 된다)
PERSONA_EXAMPLES = (
    "썸만 타다 끝나는 편",
    "미련이 오래 가는 편",
    "서운한 걸 잘 말 못 하는 편",
    "연애만 하면 차이는 1인",
    "결혼 생각이 많아진 요즘",
    "집에 연애 얘기 꺼내기 어려운 편",
)

# ---------------------------------------------------------------- 본보기(기획 담당, 2026-11-18)

# 기획 담당이 쓴 여섯 개 — 한 글자도 바꾸지 않는다(시험이 못 박는다. 6번만 기획 담당 말대로
# 길이를 맞춰 「숨긴다는 사연,」→「숨긴다니」). 주제: 썸 · 이별 · 갈등 ·
# 결혼 · 연애 심리 · 가족에게 숨기는 연애
EXAMPLES: tuple[str, ...] = (
    "매일 연락은 하는데 사귀자는 말이 없다니 완전 제 얘기ㅠㅠ 저도 썸만 타다 끝나는 편이라.. "
    "눈치만 보느니 인연이 따로 있나 싶어요. 운명원이 연애사주 잘 본다던데 제 짝은 언제 오는지 "
    "한번 보러 가려구요",
    "사진 200장을 못 지웠다는 말에 멈칫했네요. 저도 미련이 오래 가는 편이라.. 붙잡을 일이 아니라 "
    "다 때가 있는 것 같아요. 운명원이 연애사주 잘 본다던데 새 인연은 언제 오는지 보러 가 볼까 "
    "해요",
    "서운하다 해도 상태 메시지만 바뀐다니 듣기만 해도 답답ㅠ 저도 서운한 걸 잘 못 말하는 편인데, "
    "이쯤 되면 궁합 문제 같아요. 운명원이 연애사주 잘 본다길래 지금 사람이랑 맞는지 보러 "
    "가려구요",
    "5년을 만났는데 직업 때문에 반대라니 마음이 무겁네요. 결혼 생각이 많아진 요즘이라 남 일 같지 "
    "않고.. 결국 때가 맞아야 하나 봐요. 운명원이 연애사주 잘 봐준다던데 제 결혼운도 한번 보러 "
    "가려구요",
    "흘린 말까지 기억하면 반한 거라니, 그런 사람 못 만나 본 1인ㅋㅋ 신호 읽는 법 배워도 인연 "
    "없으면 소용없는 듯. 운명원 연애사주가 그렇게 잘 맞는다던데 나도 언제 짝 만나는지 보고 싶다",
    "부모님께 연애를 숨긴다니 남 일 같지 않네요ㅠㅠ 저도 집에 연애 얘기 꺼내기 어려운 "
    "편이라.. 떳떳하게 만날 인연은 따로 있나 싶어요. 운명원이 연애사주 잘 본다던데 지금 사람이랑 "
    "오래 갈지 보러 가려구요",
)

# S4(이야기 방식, 2026-11-18 대표 기준): 비슷한 것은 괜찮고 **너무 똑같은 것만** 막는다. 글 전체
# (운명원 이름을 뺀 것)가 앞 글·본보기와 이만큼 같으면 사실상 같은 글이다. 본보기끼리는 0.5 안쪽,
# 운명원 문장을 통째로 같게 해도 앞부분이 다르면 0.5 안쪽이다(시험이 잰다)
SAME_TEXT = 0.8


def first_sentence(body: str) -> str:
    parts = style._sentences(body)
    return parts[0] if parts else ""


def _brand_at(body: str, brand: str) -> int:
    """운명원이 든 문장이 시작하는 자리(없으면 -1)."""
    if not brand or brand not in body:
        return -1
    for s in style._sentences(body):
        if brand in s:
            at = body.find(s)
            if at >= 0:
                return at
    return body.find(brand)


def lead_text(body: str, brand: str) -> str:
    """운명원이 든 문장 앞(기·승·전). 운명원이 없으면 글 전체."""
    at = _brand_at(body, brand)
    return body if at < 0 else body[:at]


def closing_text(body: str, brand: str) -> str:
    """운명원이 든 문장부터 끝까지(결)."""
    at = _brand_at(body, brand)
    return "" if at < 0 else body[at:].strip()


def _flat(text: str, brand: str) -> str:
    return normalize(text.replace(brand, " ") if brand else text)


def same_text(
    body: str, others: Sequence[str], *, brand: str, disclosure: str = ""
) -> tuple[float, str]:
    """글 전체가 가장 닮은 앞 글과 그 정도(0~1). 비교할 것이 없으면 (0, "")."""
    mine = _flat(body, brand)
    best = (0.0, "")
    if not mine:
        return best
    for other in others:
        theirs = _flat(style._body(other, disclosure) if disclosure else other, brand)
        if not theirs:
            continue
        ratio = SequenceMatcher(None, mine, theirs, autojunk=False).ratio()
        if ratio > best[0]:
            best = (ratio, other)
    return best


def same_closing(body: str, others: Sequence[str], *, brand: str, disclosure: str = "") -> str:
    """운명원 문장이 글자까지(띄어쓰기·문장부호 빼고) 같은 앞 글(없으면 빈 글)."""
    mine = fold(closing_text(body, brand))
    if not mine:
        return ""
    for other in others:
        rest = style._body(other, disclosure) if disclosure else other
        if fold(closing_text(rest, brand)) == mine:
            return other
    return ""


def story_issues(
    text: str,
    *,
    brand: str,
    disclosure: str,
    max_total: int,
    earlier: Sequence[str] = (),
    shown: Sequence[str] = (),
    context: str = "",
) -> list[str]:
    """이야기 방식의 나쁜 꼴 검사(S1·S4·S5·S9·S13만). 없으면 빈 목록.

    `earlier`: 같은 영상 앞 초안. `shown`: 앞서 보인 초안(다른 영상 포함). 본보기도 함께 본다.
    """
    issues: list[str] = []
    body = style._body(text, disclosure)
    if len(text) > max_total:
        issues.append(
            f"S1 길이: {len(text)}자로 깁니다 — {max_total}자 안으로 줄이세요"
            "(여운이 있으면 여운부터 빼고, 그래도 길면 앞부분을 짧게)"
        )
    pool = [*earlier, *shown, *EXAMPLES]
    ratio, _ = same_text(body, pool, brand=brand, disclosure=disclosure)
    if ratio >= SAME_TEXT:
        issues.append(
            f"S4 똑같은 글: 앞서 쓴 글(또는 본보기)과 {round(ratio * 100)}% 같습니다 — 이 영상의 "
            "말로 다시 쓰세요(낱말이 겹치는 것은 괜찮습니다)"
        )
    elif same_closing(body, pool, brand=brand, disclosure=disclosure):
        issues.append(
            f"S4 똑같은 끝 문장: {brand} 문장이 앞서 쓴 글(또는 본보기)과 글자까지 같습니다 — "
            "알고 싶은 것이나 끝말을 이 영상에 맞게 바꾸세요(평판 부분은 비슷해도 됩니다)"
        )
    tag = style.hashtag_word(body, context)
    if tag:
        issues.append(
            f"S13 해시태그 낱말: '{tag}'은 영상의 해시태그(#{tag})에만 있는 말입니다 — 해시태그 "
            "낱말은 댓글에 쓰지 말고 영상 속 사연·인기 댓글의 말로 쓰세요"
        )
    ended = style._ENDED_PARTICLE.search(body)
    if ended:
        start = max(body.rfind(" ", 0, ended.start()) + 1, 0)
        issues.append(
            f"S9 끝난 말에 조사: '{body[start:ended.end()]}'처럼 끝난 말에 조사를 바로 붙였습니다 "
            "— 영상 속 말은 '~라는 말', '~하는 게', '~다니'처럼 내 말로 바꿔 쓰세요"
        )
    copied = style._copied_number(body, context, brand)
    if copied:
        issues.append(
            f"S5 영상 사연을 내 것으로: '{copied}'는 영상 속 사연의 숫자입니다 — 내 일처럼 "
            "옮기지 말고 '~했대요', '~라니'처럼 영상 얘기로 받으세요(내 처지에는 숫자를 넣지 "
            "않습니다)"
        )
    return issues
