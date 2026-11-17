"""운명원 대목 조각 배정(2026-11-18 기획 담당 A).

기획 담당이 같은 영상 고치기 전·후 28개를 견줬더니, 조각을 권하기만 하니 모델이
「요새 · 꽤 · 잘 본다고 하던데 · 한번 가 보려고요」로 쏠렸다. 이제 코드가 초안마다 때·연애 사주·
세기 말·평판·들은 꼴·끝말을 정해 주고(`prompts.assign_pieces`), 정해 준 것과 다르거나 ④가 앞서
보인 초안과 통째로 같으면 다듬기 검사 S15가 다시 쓰게 한다.

목표(28개): 때 한 낱말 ≤12, 세기 말 하나 ≤8, 「잘 본다」 꼴 ≤12, 같은 끝말 ≤6, ④ 통째 같음 0.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from app.analysis import style as S
from app.analysis.validator import ValidatorRules, validate
from app.config import DEFAULT_BRAND_FACTS
from app.llm import prompts as P

BRAND = "운명원"
RULES = ValidatorRules(min_chars=40, max_chars=120, brand=BRAND, disclosure="[광고]")
FACTS = list(DEFAULT_BRAND_FACTS)
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
OPEN = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "


def _run(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락", key_phrases=["하루에 한 번 연락"],
    )


def _text(pieces: P.Pieces) -> str:
    return OPEN + pieces.joined(BRAND)


def _rotate(n: int, seed: int) -> list[str]:
    """n개 초안을 차례로(영상마다 두 개, 둘째는 같은 영상 앞 초안을 피한다) 만든 셈."""
    rng = random.Random(seed)
    shown: list[str] = []
    for k in range(n):
        avoid = shown[:1] if k % 2 else []
        pieces = P.assign_pieces(BRAND, shown, avoid=avoid, rng=rng)
        shown.insert(0, _text(pieces))
    return shown


@pytest.mark.parametrize("seed", [1, 7, 11, 23])
def test_twenty_eight_drafts_meet_the_spread_targets(seed):
    shown = _rotate(28, seed)
    leads = [P.lead_part(t, BRAND) for t in shown]
    ends = [P.ending_part(t, BRAND) for t in shown]
    # 때 한 낱말(「요즘 들어」는 「요즘」으로 센다)
    words = ("요즘", "요새", "최근")
    times = Counter(next(w for w in words if lead.startswith(w)) for lead in leads)
    assert max(times.values()) <= 12, times
    hows = Counter(h for lead in leads for h in P.LEAD_HOWS if h in lead.split())
    assert max(hows.values()) <= 8, hows
    jal_bonda = sum(P._verb_of(lead) == 0 for lead in leads)
    assert jal_bonda <= 12, jal_bonda
    # 「잘 본다」 없는 평판(잘 맞춘다·잘 봐준다·잘 맞는다·정확하다·통째 꼴)도 몫이 있다
    others = Counter(P._verb_of(lead) for lead in leads if P._verb_of(lead) != 0)
    assert len(others) == 5 and min(others.values()) >= 3, others
    actions = Counter(a for e in ends for a in P.END_ACTIONS if e.endswith(a))
    assert max(actions.values()) <= 6, actions
    folded = [P.fold(lead) for lead in leads]
    assert len(set(folded)) == len(folded)  # ④ 통째 같은 짝 0


def test_every_assignable_piece_combination_passes_every_rule():
    # 배정할 수 있는 잘한다는 말 × 들은 꼴 × 세기 말(없음 포함)이 모두 V1~V14를 통과한다.
    # 「잘 맞는다」「정확하다」 + 소문·입소문·후기·추천은 V10에 걸려 배정하지 않는다(PIECE_SKIP)
    loves, times = P.LEAD_LOVES, P.LEAD_TIMES
    k = 0
    for verb in range(len(P.PIECE_VERBS) + 1):
        hears = P.PIECE_WHOLES if verb == len(P.PIECE_VERBS) else P.PIECE_HEARS
        for hear in range(len(hears)):
            if (verb, hear) in P.PIECE_SKIP:
                continue
            for how in P.PIECE_HOWS:
                k += 1
                pieces = P.Pieces(times[k % len(times)], loves[k % len(loves)], how, verb, hear,
                                  P.END_WHENS[k % len(P.END_WHENS)],
                                  P.END_ACTIONS[k % len(P.END_ACTIONS)])
                result = _run(_text(pieces))
                assert result.passed, (pieces.lead(BRAND), result.failure_lines())
    for verb in (3, 4):  # 뺀 짝은 정말 V10에 걸린다(빼지 않아도 되면 다시 넣는다)
        for hear in (7, 8, 10, 12):
            pieces = P.Pieces("요즘", "연애사주", "", verb, hear, "한번", "가보려구요")
            assert not _run(_text(pieces)).passed, pieces.lead(BRAND)


def test_every_ending_passes_with_and_without_a_reason():
    for when in P.END_WHENS:
        for action in P.END_ACTIONS:
            pieces = P.Pieces("요즘", "연애사주", "", 0, 0, when, action)
            assert _run(_text(pieces)).passed, pieces.ending()


def test_pieces_are_read_back_from_the_text():
    rng = random.Random(3)
    shown: list[str] = []
    for _ in range(20):
        pieces = P.assign_pieces(BRAND, shown, rng=rng)
        text = _text(pieces)
        back = P.pieces_of(text, BRAND)
        # 맞춤법까지 그대로 읽어 낸다(「연애사주」·「연애 사주」, AI 검수 뒤 같은 배정)
        assert back == pieces, (pieces, back)
        assert P.assign_pieces(BRAND, shown, keep=back) is back  # 다시 쓸 때 같은 배정
        shown.insert(0, text)
    assert P.pieces_of("[광고] 운명원 얘기 없음", BRAND) is None


def test_pieces_are_counted_only_in_their_own_place():
    # 영상 반응의 「요즘」「꽤」는 운명원 대목의 때·세기 말로 세지 않는다
    used = ["[광고] 요즘 꽤 힘드네요. 최근에 운명원이 연애사주를 잘 맞춘다고 하던데, 저도 한번 "
            "가보려구요"] * 6
    rng = random.Random(5)
    picks = [P.assign_pieces(BRAND, used, rng=rng) for _ in range(10)]
    assert all(p.time != "최근에" for p in picks)
    assert any(p.time == "요즘" for p in picks)
    assert all(p.action != "가보려구요" for p in picks)


def test_whole_reputation_without_a_how_slot_gets_no_how():
    used: list[str] = []
    rng = random.Random(2)
    seen = 0
    for _ in range(40):
        pieces = P.assign_pieces(BRAND, used, rng=rng)
        if pieces.verb == len(P.PIECE_VERBS) and "{how}" not in P.PIECE_WHOLES[pieces.hear]:
            assert pieces.how == ""
            seen += 1
        used.insert(0, _text(pieces))
    assert seen


def test_prompt_names_the_pieces_instead_of_suggestions():
    pieces = P.Pieces("요새 들어", "연애 쪽 사주", "꽤", 2, 3, "기회 되면",
                      "상담받아 볼 생각이에요")
    user = P.draft_user(analysis={"concern": "연락 문제"}, quote="q", source="comment",
                        min_body=35, max_body=115, hearsay=["요즘 운명원 잘 본다던데"],
                        endings=["저도 한번 가보려구요"], pieces=pieces, reason=True)
    assert ("이번 초안의 운명원 대목: 때='요새 들어' / 연애 사주='연애 쪽 사주' / 세기 말='꽤' / "
            "평판='잘 맞춘다' / 들은 꼴='~는 얘기를 들었는데' / "
            "끝말='기회 되면 상담받아 볼 생각이에요'") in user
    assert ("이어 쓰면: '요새 들어 운명원이 연애 쪽 사주를 꽤 잘 맞춘다는 얘기를 들었는데, "
            "저도 기회 되면 상담받아 볼 생각이에요'") in user
    assert "'저도 [까닭] + 기회 되면 상담받아 볼 생각이에요'" in user
    assert "꺼내는 말은 이번에 이런 식으로" not in user
    assert "바람의 끝말은 이번에 이런 식으로" not in user
    # 같은 배정이면 같은 줄(다시 쓸 때)
    again = P.draft_user(analysis={"concern": "연락 문제"}, quote="q", source="comment",
                         min_body=35, max_body=115, pieces=pieces, failure_lines=["x"],
                         previous_body="앞 글")
    line = next(x for x in user.splitlines() if x.startswith("이번 초안의 운명원 대목:"))
    assert line in again


def test_s15_flags_pieces_other_than_assigned_and_a_repeated_lead():
    pieces = P.Pieces("요새", "연애사주", "", 2, 0, "조만간 한번", "찾아가 보려고요")
    good = _text(pieces)
    assert S.style_issues(good, brand=BRAND, disclosure="[광고]", pieces=pieces) == []
    # 다른 때·세기 말을 넣고 다른 끝말로
    drift = OPEN + "요즘 운명원이 연애사주를 꽤 잘 맞춘다고 하던데, 저도 한번 가보려구요"
    issues = [i for i in S.style_issues(drift, brand=BRAND, disclosure="[광고]", pieces=pieces)
              if i.startswith("S15")]
    assert len(issues) == 1
    assert "때='요새'" in issues[0] and "세기 말='(없음)'" in issues[0]
    assert "끝말='조만간 한번 찾아가 보려고요'" in issues[0]
    assert ("'요새 운명원이 연애사주를 잘 맞춘다고 하던데, 저도 조만간 한번 찾아가 "
            "보려고요'") in issues[0]
    # 까닭을 「저도」 뒤에 넣어도 조각은 그대로다
    reasoned = OPEN + ("요새 운명원이 연애사주를 잘 맞춘다고 하던데, 저도 연락 문제로 조만간 한번 "
                       "찾아가 보려고요")
    assert S.style_issues(reasoned, brand=BRAND, disclosure="[광고]", pieces=pieces) == []
    # ④가 앞서 보인 초안과 통째로 같다
    repeat = S.style_issues(good, brand=BRAND, disclosure="[광고]", pieces=pieces,
                            used_leads=[P.lead_part("[광고] 아. " + good[5:], BRAND)])
    assert [i for i in repeat if i.startswith("S15 꺼내는 말 되풀이")]
    # 조각을 주지 않으면(사람이 고친 글) 보지 않는다
    assert not [i for i in S.style_issues(drift, brand=BRAND, disclosure="[광고]")
                if i.startswith("S15")]


def test_representative_samples_still_pass_and_s15_leaves_them_alone():
    # 대표 본보기 10개는 그대로 통과한다. 조각을 정해 주지 않은 글(사람이 쓴 글)은 S15가 보지 않고,
    # 목록에 없는 끝말(「상담받아보고 싶네요」)이면 읽어 내지 못해 새로 정한다(None)
    for model in P.BRAND_MODELS:
        text = OPEN + model
        assert _run(text).passed, (model, _run(text).failure_lines())
        assert not [i for i in S.style_issues(text, brand=BRAND, disclosure="[광고]")
                    if i.startswith("S15")]
    read = [P.pieces_of(OPEN + m, BRAND) for m in P.BRAND_MODELS]
    assert sum(r is not None for r in read) >= 5
