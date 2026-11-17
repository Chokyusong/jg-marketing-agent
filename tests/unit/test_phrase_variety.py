"""영상마다 다르게(2026-11-17, PDF 대조) — 같은 표현 되풀이 줄이기.

Codex(`gpt-5.6-luna`) 영상 8개 × 초안 2개에서 「자꾸 눈에 띄던데」 4번, 「나도 한번 볼까
싶다」 4번이 나왔다. 코드가 권하는 꺼내는 말·끝말 목록이 짧았고, 오래전 글까지 센 횟수만 보아
드물게 쓴 말 하나가 영상마다 「가장 덜 쓴 것」으로 남았다.

- 목록을 넉넉히(모두 V14·V8·V10·S3에 안 걸리는지 여기서 본다), 최근 글에 쓴 것을 먼저 피한다.
- 목록은 권유일 뿐(프롬프트에 「목록에 없는 말도 된다」).
- 2026-11-17(대표 다섯 조각): 꺼내는 말·끝말을 조각(때·연애 사주·틀·세기 말·들은 얘기 꼴 / 언제·
  가 보겠다는 말)별 목록으로 바꿨다. 조각마다 덜 쓴 것을 골라 이어 붙인다. 예전 통문장 목록
  (`HEARSAY_LINES`·`WISH_ENDINGS`)의 시험은 조각 시험으로 옮겼다.
- S6: 「~는데/인데」 뒤에 운명원의 「~던데」를 또 이은 문장은 다시 쓰게 한다(승인은 막지 않음).
- 분석: 설명란에만 있는 채널 홍보·방송 일정 안내는 근거·핵심 말에서 뺀다.
"""

from __future__ import annotations

import random

import pytest
from test_context_fit import make_context

from app.analysis import style as S
from app.analysis.analyzer import check_evidence, check_key_phrases, is_channel_promo
from app.analysis.context import search_text
from app.analysis.validator import ValidatorRules, validate
from app.llm import prompts as P

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = ["연애 사주 상담을 하는 곳"]
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
OPEN = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요."


def _check(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락", key_phrases=["하루에 한 번 연락"],
    )


def test_piece_lists_cover_the_ceo_models():
    """2026-11-17 대표 본보기 10개에서 뽑은 조각이 목록에 다 있다(같은 결의 변형 몇 개를 더함)."""
    assert {"요즘", "요새", "최근", "최근에"} <= set(P.LEAD_TIMES)
    assert {"연애사주", "연애 사주", "연애 쪽 사주"} <= set(P.LEAD_LOVES)
    assert {"그렇게", "진짜", "엄청", "특히", "되게", "꽤"} <= set(P.LEAD_HOWS)
    assert {"잘 본다", "잘 맞춘다", "잘 봐준다", "잘 맞는다", "정확하다"} <= set(P.CLAIM_MARKS)
    assert {"고 하더라구요", "고 하더라구여", "고 하던데", "는 얘기를 들었는데",
            "는 이야기가 있던데", "는 얘기가 있더라구요"} <= set(P.LEAD_TAILS)
    assert {"언제 한번", "조만간 한번", "기회 되면", "한번", "언제 시간 내서",
            "궁금해서 한번"} <= set(P.END_WHENS)
    assert {"방문해서 사주 봐보려구요", "가보고 싶네요", "상담받아보고 싶어요",
            "방문해 볼까 싶네요",
            "가보려구요", "가볼 생각이에요", "직접 알아보고 싶어요", "방문해 볼까 해요",
            "사주 봐보고 싶네요"} <= set(P.END_ACTIONS)
    for pieces in (P.LEAD_TIMES, P.LEAD_LOVES, P.LEAD_HOWS, P.LEAD_TAILS, P.END_WHENS,
                   P.END_ACTIONS, P.CLAIM_MARKS):
        assert len(set(pieces)) == len(pieces)
    assert "여쭤보고 싶네요" not in P.END_ACTIONS


def _lead(time: str, claim: str, love: str, how: str, tail: str, brand: str = "운명원") -> str:
    filled = claim.format(brand=brand, brand_i=P.with_i(brand), love=love, how=how)
    return f"{time} {filled}{tail}"


@pytest.mark.parametrize("claim", P.LEAD_CLAIMS)
@pytest.mark.parametrize("tail", P.LEAD_TAILS)
def test_every_lead_piece_combination_passes_rules_and_style(claim, tail):
    """틀 × 들은 얘기 꼴마다, 때·연애 사주·세기 말을 돌려 가며 규칙 검사 14개와 다듬기 검사."""
    for i, time in enumerate(P.LEAD_TIMES):
        lead = _lead(time, claim, P.LEAD_LOVES[i % 3], P.LEAD_HOWS[i % len(P.LEAD_HOWS)], tail)
        joint = ". " if lead.endswith(("요", "여")) else ", "
        text = f"{OPEN} {lead}{joint}저도 언제 한번 가 보려고요."
        result = _check(text)
        assert [c.code for c in result.checks if not c.passed] == [], (
            lead, result.failure_lines())
        assert S.style_issues(text, brand="운명원", disclosure="[광고]") == [], lead
        assert S.hearsay_mark(text, "운명원"), lead  # S4가 같은 꺼내는 말을 알아본다


@pytest.mark.parametrize("when", P.END_WHENS)
def test_every_ending_piece_combination_passes_rules_and_style(when):
    for action in P.END_ACTIONS:
        text = f"{OPEN} 요즘 운명원 연애 사주 잘 본다고 하던데, 저도 {when} {action}."
        result = _check(text)
        assert [c.code for c in result.checks if not c.passed] == [], (
            when, action, result.failure_lines())
        assert S.style_issues(text, brand="운명원", disclosure="[광고]") == [], (when, action)


def test_suggestions_are_whole_five_piece_passages():
    leads = P.hearsay_choices("운명원", [], n=3, rng=random.Random(3))
    ends = P.ending_choices([], n=3, rng=random.Random(3))
    assert len(set(leads)) == 3 and len(set(ends)) == 3
    for lead, end in zip(leads, ends, strict=True):
        assert end.startswith("저도 ")
        text = f"{OPEN} {lead}, {end}."
        assert _check(text).passed, (text, _check(text).failure_lines())


def test_counting_ignores_spelling_and_takes_the_longest_piece():
    """편한 맞춤법(하더라구요·가보려구요)과 붙여 쓴 「연애사주」는 같은 것으로 센다. 「언제 한번」
    안의 「한번」, 「요즘 들어」 안의 「요즘」은 따로 세지 않는다."""
    assert P.fold("하더라구요") == P.fold("하더라고요") == P.fold("하더라구여")
    assert P.fold("가보려구요") == P.fold("가 보려고요")
    assert P.fold("연애사주") == P.fold("연애 사주")
    used = ["[광고] … 요즘 들어 운명원 연애 사주가 잘 맞는다고 하더라고요. 저도 언제 한번 가 "
            "보려고요."]
    whens = P._least_used(P.END_WHENS, used, rng=random.Random(0))
    assert whens[-1] == "언제 한번" and "한번" in whens[:-1]
    times = P._least_used(P.LEAD_TIMES, used, rng=random.Random(0))
    assert times[-1] == "요즘 들어" and "요즘" in times[:-1]
    tails = P._least_used(P.LEAD_TAILS, used, rng=random.Random(0))
    assert set(tails[-2:]) == {"고 하더라구요", "고 하더라구여"}  # 맞춤법만 다른 둘
    loves = P._least_used(P.LEAD_LOVES, used, rng=random.Random(0))
    assert set(loves[-2:]) == {"연애사주", "연애 사주"}
    actions = P._least_used(P.END_ACTIONS, used, rng=random.Random(0))
    assert actions[-1] == "가보려구요"  # 「가 보려고요」로 쓴 것을 「가보려구요」로 센다


def test_recent_use_is_avoided_before_old_counts():
    """오래전 글에 많이 쓴 말보다, 최근 글에 쓴 말을 먼저 피한다(조각마다)."""
    old = ["[광고] 요새 운명원 연애 사주가 진짜 잘 맞는다던데, 저도 한번 가보고 싶네요."] * 5
    recent = ["[광고] 최근에 운명원이 연애 쪽 사주를 꽤 잘 본다고들 하던데, 저도 기회 되면 "
              "상담받아보고 싶어요."]
    filler = ["…"] * (P.RECENT_TEXTS - 1)
    times = P._least_used(P.LEAD_TIMES, recent + filler + old, rng=random.Random(1))
    assert times[-2:] == ["요새", "최근에"]
    # 최근 6개 글 밖으로 밀려나면 전체 횟수로만 본다(다섯 번 쓴 말이 맨 뒤)
    used = ["…"] * P.RECENT_TEXTS + recent + old  # 최신이 앞
    times = P._least_used(P.LEAD_TIMES, used, rng=random.Random(1))
    assert times[-2:] == ["최근에", "요새"]
    actions = P._least_used(P.END_ACTIONS, recent, rng=random.Random(1))
    assert actions[-1] == "상담받아보고 싶어요"


def test_system_prompt_does_not_seed_one_ending():
    """임무 문장이 「한번 볼까 싶어지게」였더니 모델이 그 말을 끝말로 되풀이했다(Codex 6/16)."""
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=FACTS)
    assert "볼까' 싶어지게" not in system
    assert "운명원 연애 사주에 관심이 가게 한다" in system


def test_eight_videos_in_a_row_do_not_repeat_the_same_lead():
    """모델이 첫 권유를 고른다고 치면 8개 영상에서 같은 말이 되풀이되지 않는다."""
    used: list[str] = []
    leads, endings = [], []
    for _ in range(8):
        lead = P.hearsay_choices("운명원", used, n=3)[0]
        end = P.ending_choices(used, n=3)[0]
        leads.append(lead)
        endings.append(end)
        used.insert(0, f"[광고] 영상 얘기. {lead}, {end}.")
    assert len(set(leads)) == 8 and len(set(endings)) == 8
    # 조각마다도 돈다: 때 말 6가지가 앞 6개 영상에 한 번씩
    assert len({lead.split(" 운명원")[0] for lead in leads[:6]}) == 6


def test_empty_history_picks_differ_by_seed():
    """2026-11-17(대표 「잘 보기로 유명하다던데 이것만 나와?」): 기록이 하나도 없는 새 PC에서도
    영상마다 다른 말을 권한다 — 횟수가 같으면 목록 순서가 아니라 무작위. 씨앗이 같으면 같은 답."""
    firsts = {P.hearsay_choices("운명원", [], n=3, rng=random.Random(s))[0] for s in range(12)}
    ends = {P.ending_choices([], n=3, rng=random.Random(seed))[0] for seed in range(12)}
    assert len(firsts) >= 5 and len(ends) >= 5
    a = P.hearsay_choices("운명원", [], n=3, rng=random.Random(7))
    assert a == P.hearsay_choices("운명원", [], n=3, rng=random.Random(7))
    assert a != P.hearsay_choices("운명원", [], n=3, rng=random.Random(8))
    # 기본(씨앗 없음)도 무작위: 여러 번 부르면 처음 권하는 말이 한 가지로 굳지 않는다
    assert len({P.hearsay_choices("운명원", [])[0] for _ in range(40)}) > 1


def test_draft_user_says_lists_are_only_suggestions():
    text = P.draft_user(
        analysis={"topic": "t", "concern": "c"}, quote="q", source="comment", min_body=35,
        max_body=115, brand="운명원", hearsay=["요즘 운명원 연애 사주 잘 본다고 하던데"],
        endings=["저도 언제 한번 가 보려고요"],
    )
    assert "권유일 뿐이다 — 조각을 바꿔도 되지만" in text
    assert "목록에 없는 말도 되지만 가 보겠다는 뜻은 넣는다" in text
    assert "'저도 고민인데 운명원 잘 본다던데 …' ✗" in text
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=FACTS)
    assert "그대로 베끼지 말고 이 결로" in system
    assert "'나도 한번 볼까 싶다'" not in system  # 고정 예가 굳은 끝말이 되지 않게


# ---------------------------------------------------------------- S6


@pytest.mark.parametrize("text", [
    "[광고] 저도 요즘 이 고민인데 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요.",
    "[광고] 거절당하면 동아리 못 간다는 말에 진짜 공감되네요...ㅠ 동아리 선배라서 더 조심스러운데 "
    "요즘 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요",
    "[광고] 연락 문제는 늘 어려운데 요새 주변에서 운명원 연애 사주 잘 본다고들 하던데 저도 한번 "
    "방문해 볼까 해요.",
    # Codex 1회차: 쉼표를 찍어도 같은 꼴
    "[광고] 저도 맞는 사람을 만날 수 있을지 늘 고민인데, 요즘 운명원이 연애 사주를 잘 봐준다고 "
    "하던데 저도 조만간 상담받아보고 싶어요.",
])
def test_s6_neunde_then_deonde_in_one_sentence(text):
    found = S.style_issues(text, brand="운명원", disclosure="[광고]")
    assert [i[:2] for i in found] == ["S6"], found
    assert "새 문장으로 꺼내세요" in found[0]


@pytest.mark.parametrize("text", [
    # 끊어 쓰면 괜찮다
    "[광고] 저도 요즘 이 고민이에요. 요즘 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요.",
    # 「~던데」만, 「~는데」가 운명원 문장 밖에
    "[광고] 연락이 뜸해지는데 괜히 불안하네요. 요새 운명원이 연애 사주로 유명하다던데 저도 한번 "
    "가볼 생각이에요.",
    # 「들었는데」처럼 운명원을 꺼내는 말 자체가 「~는데」(뒤에 「~던데」 없음)
    "[광고] 남 일 같지 않네요. 최근에 운명원이 연애사주를 엄청 잘 봐준다는 얘기를 들었는데, 저도 "
    "기회 되면 상담받아보고 싶어요.",
    # 「~던데」 뒤의 「~는데」는 순서가 달라 늘어지지 않는다
    "[광고] 남 일 같지 않네요. 요즘 운명원 연애 사주 잘 본다던데 나도 궁금한데 한번 가 보려고.",
])
def test_s6_allows_split_or_single_connective(text):
    assert [i[:2] for i in S.style_issues(text, brand="운명원", disclosure="[광고]")] == []


# ---------------------------------------------------------------- 분석: 설명란 채널 홍보


PROMO_DESC = ("매주 수요일 밤 연애상담 라이브를 합니다. 사연 보내주세요! "
              "오늘은 하루에 한 번 연락하는 커플의 고민을 다뤘습니다.")


def test_channel_promo_in_description_is_not_evidence_or_key_phrase():
    ctx = make_context(description=PROMO_DESC, transcript="하루에 한 번 연락하자고 해서 싸웠어요")
    text = search_text(ctx)
    assert is_channel_promo("연애상담 라이브", ctx)
    assert is_channel_promo("사연 보내주세요", ctx)
    assert not is_channel_promo("하루에 한 번 연락", ctx)  # 라이브 같은 말이 없다
    kept, dropped = check_evidence(
        [{"quote": "매주 수요일 밤 연애상담 라이브를 합니다", "source": "description"},
         {"quote": "하루에 한 번 연락하자고 해서 싸웠어요", "source": "transcript"}],
        ctx, text,
    )
    assert [e.quote for e in kept] == ["하루에 한 번 연락하자고 해서 싸웠어요"]
    assert dropped == ["매주 수요일 밤 연애상담 라이브를 합니다"]
    phrases, lost = check_key_phrases(["연애상담 라이브", "하루에 한 번 연락"], text, ctx)
    assert phrases == ["하루에 한 번 연락"] and lost == ["연애상담 라이브"]
    # 자료를 안 주면(예전 호출) 예전 그대로
    assert "연애상담 라이브" in check_key_phrases(["연애상담 라이브"], text)[0]


def test_same_words_in_the_transcript_are_kept():
    """자막에도 나오는 말이면 영상 얘기일 수 있다(「매주 만나는데」 같은 사연)."""
    ctx = make_context(description="매주 만나는 커플 이야기",
                       transcript="저희는 매주 만나는 커플인데요")
    assert not is_channel_promo("매주 만나는 커플", ctx)
