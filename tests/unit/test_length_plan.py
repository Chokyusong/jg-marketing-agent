"""길이를 코드가 먼저 센다(2026-11-18 기획 담당).

루나 12개 중 한 번에 끝난 초안이 하나뿐이었다(다시 쓴 까닭 S1 길이 9번). 배정된 조각이 긴 꼴이면
운명원 대목만 65~75자였다. 이제:
- 운명원 대목의 예상 길이(`brand_estimate`)에 상한(`BRAND_CAP`, 잇는 문장이 없으면 `BRAND_CAP_LONG`)
  — 넘으면 덜 쓴 차례를 지키며 짧은 꼴로.
- 남는 글자 수를 ①·②에 숫자로(`length_plan`), 모자라면 잇는 문장을 뺀다.
- 요청 글 맨 끝 한 줄에 ⑤의 끝 꼴.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from app.llm import prompts as P

BRAND = "운명원"
ANALYSIS = {"topic": "재회", "concern": "헤어진 사람을 못 잊겠다", "tone": "t", "viewer_needs": "n"}
BASE = dict(analysis=ANALYSIS, quote="q", source="comment", min_body=35, max_body=115)


def _shown(pieces: P.Pieces, kind: str) -> str:
    fill = {P.REASON_WISH: "저도 이 사람이랑 맞는지 ", P.REASON_STATE: "저도 연락 문제로 "}
    return "[광고] 반응입니다. " + pieces.joined(BRAND).replace("저도 ", fill.get(kind, "저도 "))


@pytest.mark.parametrize("kind", [P.REASON_WISH, P.REASON_STATE, P.REASON_NONE])
@pytest.mark.parametrize("cap", [P.BRAND_CAP, P.BRAND_CAP_LONG])
def test_brand_part_stays_under_the_cap_and_keeps_variety(kind, cap):
    rng = random.Random(11)
    shown: list[str] = []
    hows, leads = Counter(), Counter()
    for _ in range(20):
        pieces = P.assign_pieces(BRAND, shown, rng=rng, wish=kind == P.REASON_WISH, cap=cap,
                                 reason_kind=kind)
        assert P.brand_estimate(pieces, BRAND, kind) <= cap, pieces
        hows[pieces.how] += 1
        leads[P.fold(pieces.lead(BRAND))] += 1
        shown.insert(0, _shown(pieces, kind))
    assert max(leads.values()) == 1  # 꺼내는 말 통째 같은 것 없음
    assert len(hows) >= 6 and hows[""] <= 7  # 세기 말을 늘 빼지 않는다


def test_without_a_cap_or_when_it_fits_nothing_changes():
    a = P.assign_pieces(BRAND, [], rng=random.Random(3))
    b = P.assign_pieces(BRAND, [], rng=random.Random(3), cap=999, reason_kind=P.REASON_WISH)
    assert a == b


def test_long_forms_shrink_to_short_ones():
    # 「요새 들어 · 연애 쪽 사주 · 정말 잘 봐주기로 유명하다던데 · 언제 시간 내서 찾아가
    # 보려고요」 꼴
    rng = random.Random(0)
    longest = max((P.assign_pieces(BRAND, [], rng=rng) for _ in range(200)),
                  key=lambda p: P.brand_estimate(p, BRAND, P.REASON_WISH))
    assert P.brand_estimate(longest, BRAND, P.REASON_WISH) > P.BRAND_CAP
    short = P.assign_pieces(BRAND, [], rng=random.Random(0), cap=P.BRAND_CAP,
                            reason_kind=P.REASON_WISH, wish=True)
    assert P.brand_estimate(short, BRAND, P.REASON_WISH) <= P.BRAND_CAP


def _pieces(kind: str, cap: int) -> P.Pieces:
    return P.assign_pieces(BRAND, [], rng=random.Random(1), wish=kind == P.REASON_WISH, cap=cap,
                           reason_kind=kind)


def test_length_plan_splits_the_room_into_numbers():
    pieces = _pieces(P.REASON_WISH, P.BRAND_CAP)
    plan = P.length_plan(pieces, BRAND, mark_len=5, reason_kind=P.REASON_WISH, bridge=True)
    assert plan.brand == P.brand_estimate(pieces, BRAND, P.REASON_WISH)
    assert P.BRIDGE_CHARS[0] <= plan.bridge <= P.BRIDGE_CHARS[1]
    assert 25 <= plan.first <= P.FIRST_MAX
    assert plan.total <= P.PLAN_TOTAL
    # 표기를 끄면 ①에 5자를 더 준다
    off = P.length_plan(pieces, BRAND, mark_len=0, reason_kind=P.REASON_WISH, bridge=True)
    assert off.first + off.bridge > plan.first + plan.bridge
    # 잇는 문장을 정하지 않았으면 ②는 0
    alone = P.length_plan(pieces, BRAND, mark_len=5, reason_kind=P.REASON_WISH, bridge=False)
    assert alone.bridge == 0 and alone.first <= P.FIRST_MAX


def test_no_bridge_when_the_brand_part_leaves_too_little_room():
    rng = random.Random(0)
    longest = max((P.assign_pieces(BRAND, [], rng=rng, wish=True) for _ in range(200)),
                  key=lambda p: P.brand_estimate(p, BRAND, P.REASON_WISH))
    plan = P.length_plan(longest, BRAND, mark_len=5, reason_kind=P.REASON_WISH, bridge=True)
    room = P.PLAN_TOTAL - 5 - plan.brand - 1
    assert room < P.BRIDGE_ROOM and plan.bridge == 0


def test_draft_user_gives_numbers_and_ends_with_the_ending_form():
    pieces = _pieces(P.REASON_WISH, P.BRAND_CAP)
    plan = P.length_plan(pieces, BRAND, mark_len=5, reason_kind=P.REASON_WISH, bridge=True)
    user = P.draft_user(**BASE, pieces=pieces, reason_kind=P.REASON_WISH, bridge=True, plan=plan,
                        failure_lines=["S1 길이: 너무 깁니다"], previous_body="앞 글")
    assert f"① 영상 반응은 {plan.first}자 안의 **온전한 한 문장**" in user
    assert "'끌림이라니...'처럼 말을 던지고 끊거나 짧은 토막 여럿으로 쪼개지 않는다" in user
    assert f"② 잇는 문장은 {plan.bridge}자 안의 한 문장" in user
    assert f"운명원 대목은 정해 준 조각 그대로 {plan.brand}자쯤" in user
    assert "영상 반응은 25~35자로" not in user  # 숫자로 바꿨다
    # 맨 끝 한 줄(다시 쓰기 줄보다도 뒤)
    last = user.splitlines()[-1]
    assert last.startswith(f"[끝 꼴] 저도 [알고 싶은 것] {pieces.ending()}.")
    assert "꼴 보기 문구를 그대로 쓰지 않는다" in last
    none = P.draft_user(**BASE, pieces=pieces, reason_kind=P.REASON_NONE, bridge=True,
                        plan=P.length_plan(pieces, BRAND, mark_len=5,
                                           reason_kind=P.REASON_NONE, bridge=False))
    assert none.splitlines()[-1] == f"[끝 꼴] 저도 {pieces.ending()}."
    assert "② 잇는 문장은 이번에 쓰지 않는다" in none
    state = P.draft_user(**BASE, pieces=pieces, reason_kind=P.REASON_STATE, plan=plan)
    assert state.splitlines()[-1].startswith("[끝 꼴] 저도 [이 영상 고민에서 온 짧은 까닭] ")
    # 몫을 주지 않으면(예전 호출) 예전 글 그대로
    old = P.draft_user(**BASE, pieces=pieces, reason_kind=P.REASON_WISH, bridge=True)
    assert "영상 반응은 25~35자로" in old and "[끝 꼴]" not in old


def test_system_asks_for_a_whole_first_sentence():
    system = P.draft_system(brand=BRAND, disclosure="[광고]", facts=[])
    assert "짧게 쓰려고 토막 내지 않는다" in system
    assert "**온전한 한 문장**('끌림이라니... 속얘기까지 듣고 싶네요.' ✗)" in system
