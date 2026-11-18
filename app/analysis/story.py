"""이야기처럼 쓰기(2026-11-18 대표 결정).

설정 `comment.writer`가 `story`(기본)이면 코드는 조각·말투·잇는 문장·까닭·글쓴이 처지를 정해 주지
않는다. AI가 자막(없으면 제목·설명)과 인기 댓글을 직접 읽고 영상의 연애 고민을 먼저 정리한 뒤,
시청자 입장에서 기승전결로 통째로 쓴다(`story_prompts`). `pieces`는 그 전 방식(조각 맞추기)이고
코드와 시험을 그대로 둔다.

`story`에 남는 것(대표 표, 2026-11-18 — 코드가 확인할 것 / AI가 판단할 것):
1. 코드, 규칙 검사(막는 것, `validator.validate(story=True)`) — 설정된 글자 수(V1, 표기 빼고) · 영상
   근거(V6·V7) · 운명원 언급(V5) · 허위 이용 후기(V8·V9·V10, V14 지어낸 평판·사례) + 과제 원문 금지
   (V2 링크·V3 해시태그·V11 영상마다 다르게)와 표기(V4). V12·V13은 보지 않는다.
2. 코드, 다시 쓰게만 하는 검사(`story_issues`) — S4 앞 글과 거의 똑같은 글.
3. AI, 맥락 일치 검증(`review.story_review_system`) — 영상 맥락과 일치(same_topic·drift) ·
   기승전결이 자연스러운가(flow) · 같은 사람이 쓴 글처럼(one_voice) ·
   운명원 언급이 뜬금없는가(natural_ad).
   걸리면 한 번 다시 쓰고, 그래도 걸려도 게시를 막지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from app.analysis import style
from app.analysis.validator import normalize

WRITER_STORY = "story"
WRITER_PIECES = "pieces"
WRITERS = (WRITER_STORY, WRITER_PIECES)
WRITER_LABELS = {WRITER_STORY: "이야기처럼(권장)", WRITER_PIECES: "조각 맞추기(예전)"}

# S4(이야기 방식, 2026-11-18 대표 기준): 비슷한 것은 괜찮고 **너무 똑같은 것만** 막는다. 글 전체
# (운명원 이름을 뺀 것)가 앞 글과 이만큼 같으면 사실상 같은 글이다. 운명원 문장이 닮은 것만으로는
# 걸리지 않는다(대표: 「브랜드 문장이 조금 비슷하다는 이유로 다시 쓰게 하지 않는다」)
SAME_TEXT = 0.8


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
    """이야기 방식의 나쁜 꼴 검사(S4 똑같은 글만 — 2026-11-18 대표: 불필요한 제한은 뺀다.
    S5·S9·S13과 「똑같은 끝 문장」을 뺐고, S1 길이는 V1과 같은 셈이 되어 뺐다). 없으면 빈 목록.

    `earlier`: 같은 영상 앞 초안. `shown`: 앞서 보인 초안(다른 영상 포함).
    """
    del max_total  # 길이는 규칙 검사 V1이 본다(표기 빼고)
    issues: list[str] = []
    body = style._body(text, disclosure)
    pool = [*earlier, *shown]
    ratio, _ = same_text(body, pool, brand=brand, disclosure=disclosure)
    if ratio >= SAME_TEXT:
        issues.append(
            f"S4 똑같은 글: 앞서 쓴 글과 {round(ratio * 100)}% 같습니다 — 이 영상의 "
            "말로 다시 쓰세요(낱말이 겹치는 것은 괜찮습니다)"
        )
    return issues
