"""운명원 페르소나(2026-11-17 대표): 「연애 사주 잘 봐주는 곳으로 유명한 곳」(과제 원문).

- 꺼내는 말에 무엇을 잘하는지(잘 본다·잘 봐준다·잘 맞는다·유명하다)가 들어간다.
- 들은 얘기 꼴의 평판은 통과한다: 「친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데」처럼
  **남이 본 얘기를 전하는 것**도(V8), 「잘 맞는다고 하던데」「잘 봐준다고 하던데」(V10)도.
- 그대로 막는 것: **내가 써 본 척**(V8)과 **내 단정·효능 단정**(V10).
- 평판이 빠진 꺼내는 말(「운명원 얘기 자주 보이던데」)은 다듬기 검사 S7이 다시 쓰게 한다.
"""

from __future__ import annotations

import pytest

from app.analysis import style as S
from app.analysis.validator import ValidatorRules, validate
from app.config import DEFAULT_BRAND_FACTS, forget_old_defaults, load_settings
from app.llm import prompts as P

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = list(DEFAULT_BRAND_FACTS)
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
OPEN = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "


def _run(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락", key_phrases=["하루에 한 번 연락"],
    )


PASS = [
    # 대표가 든 꼴
    "요새 운명원이 연애 사주를 그렇게 잘 본다던데 나도 한번 보고 싶다.",
    "운명원이 연애 사주를 잘 봐준다고 하던데 나도 한번 보고 싶다.",
    "운명원이 연애 사주 잘 보기로 유명하다던데 나도 한번 보고 싶다.",
    "친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데 나도 한번 보고 싶다.",
    "주변에서 운명원 연애 사주 잘 본다고들 하던데 나도 한번 보고 싶다.",
    # 같은 뜻의 다른 꼴
    "운명원이 연애 사주 잘 맞춘다고 하던데 나도 한번 보고 싶다.",
    "운명원 연애 사주가 잘 맞힌다고 하던데 나도 한번 보고 싶다.",
    "운명원 연애 사주 잘 맞는대요. 나도 한번 보고 싶다.",
    "아는 언니가 운명원에서 연애 사주 받아 봤는데 잘 봐준다던데 저도 궁금해요.",
    "동생이 운명원 다녀왔는데 잘 맞췄대요. 나도 한번 보고 싶다.",
    "요즘 운명원이 연애사주 잘 본다고 하는 얘기가 자주 보이던데 오래 갈지 물어보고 싶어요.",
    "운명원이 연애운을 잘 봐준다길래 우리도 오래 갈 수 있을지 궁금해졌어요.",
]
FAIL = [
    # 내가 써 본 척(V8) — 과제 금지
    ("제가 운명원에서 봤는데 잘 맞더라고요. 또 보고 싶다.", "V8"),
    ("운명원 다녀왔는데 진짜 좋았어요. 또 가 보고 싶다.", "V8"),
    ("운명원에서 받아 봤어요. 요즘 잘 본다던데 또 보고 싶다.", "V8"),
    ("친구가 운명원 봤는데 저도 봤는데 잘 맞는다고 하던데 보고 싶다.", "V8"),
    ("친구랑 운명원에서 같이 봤는데 좋았어요. 또 보고 싶다.", "V8"),
    ("친구가 운명원 봤는데 후기가 좋더라고요. 나도 보고 싶다.", "V8"),
    # 내 단정·효능 단정(V10)
    ("운명원은 잘 맞혀요. 요즘 많이들 본다던데 보고 싶다.", "V10"),
    ("운명원 연애 사주 잘 맞아요. 다들 본다던데 보고 싶다.", "V10"),
    ("운명원 잘 봐요. 요즘 소문 났던데 보고 싶다.", "V10"),
    ("운명원은 무조건 맞는다던데 나도 한번 보고 싶다.", "V10"),
    ("운명원 100% 맞는다던데 나도 한번 보고 싶다.", "V10"),
    ("운명원이 정확하다던데 나도 한번 보고 싶다.", "V10"),
    ("운명원 연애 사주가 용하대요. 나도 한번 보고 싶다.", "V10"),
    ("운명원이 제일 잘 본다던데 나도 한번 보고 싶다.", "V10"),
]


@pytest.mark.parametrize("lead", PASS)
def test_relayed_reputation_passes_every_rule(lead):
    result = _run(OPEN + lead)
    assert result.passed, (lead, result.failure_lines())


@pytest.mark.parametrize(("lead", "code"), FAIL)
def test_own_use_and_own_claims_still_fail(lead, code):
    result = _run(OPEN + lead)
    assert code in {c.code for c in result.failures}, (lead, result.failure_lines())


def test_enough_boundary_cases():
    assert len(PASS) >= 10 and len(FAIL) >= 10


# ---------------------------------------------------------------- 대표가 고쳐 보인 문장

CEO_CONTEXT = (
    "[제목] 남자친구가 스스로 잘해 주게 만드는 말\n[자막] 사람은 누구나 뭔가 해줬을 때 좋은 소리를 "
    "들으면 또 하고 싶어져요. 부탁은 그때그때 말하는 거예요. 그러면 남자는 스스로 움직이죠."
)
CEO_BEFORE = ("좋은 소리를 들으면 스스로 움직이죠, 그 말에 매번 타박부터 한 게 생각나네요. "
              "요즘 운명원 얘기 자주 보이던데 다음 연애는 오래 갈지 물어보고 싶어요.")
CEO_AFTER = ("좋은 소리를 들으면 스스로 움직이죠, 그 말에 매번 타박부터 한 게 생각나네요. "
             "요즘 운명원이 연애사주 잘 본다고 하는 얘기가 자주 보이던데 다음 연애는 오래 갈지 "
             "물어보고 싶어요.")


def test_ceo_corrected_sentence_passes_all_fourteen_checks():
    assert len(CEO_AFTER) == 101
    result = validate(
        CEO_AFTER, context_text=CEO_CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="좋은 소리를 들으면 또 하고 싶어져요", key_phrases=["스스로 움직이죠"],
        concern="어떻게 해야 남자친구가 스스로 잘해 줄까?", disclosure_required=False,
    )
    assert len(result.checks) == 14 and result.passed, result.failure_lines()
    assert S.style_issues(CEO_AFTER, brand="운명원", disclosure="[광고]") == []


def test_lead_without_reputation_is_written_again_s7():
    found = S.style_issues(CEO_BEFORE, brand="운명원", disclosure="[광고]")
    assert [i[:2] for i in found] == ["S7"]
    assert "잘 본다" in found[0]
    for lead in ("주변에서 운명원 얘기 종종 하던데", "요즘 운명원 얘기가 자꾸 눈에 띄던데"):
        text = f"[광고] 남 일 같지 않네요. {lead} 나도 한번 보고 싶다."
        assert [i[:2] for i in S.style_issues(text, brand="운명원", disclosure="[광고]")] == ["S7"]
    # 평판이 앞 문장에 있어도 된다
    text = "[광고] 운명원이 연애 사주 잘 본다고 하더라고요. 운명원 가서 나도 물어보고 싶다."
    assert "S7" not in [i[:2] for i in S.style_issues(text, brand="운명원", disclosure="[광고]")]


def test_every_lead_in_the_list_carries_a_reputation():
    for template, _ in P.HEARSAY_LINES:
        lead = P.fill_hearsay(template, "운명원")
        assert S.has_reputation(lead + " 나도 보고 싶다.", "운명원"), lead
    leads = [P.fill_hearsay(t, "운명원") for t, _ in P.HEARSAY_LINES]
    assert "요새 운명원이 연애 사주를 그렇게 잘 본다던데" in leads
    assert "운명원이 연애 사주를 잘 봐준다고 하던데" in leads
    assert "운명원이 연애 사주 잘 보기로 유명하다던데" in leads
    assert "친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데" in leads
    assert "주변에서 운명원 연애 사주 잘 본다고들 하던데" in leads
    assert not any(lead.endswith(("얘기 자주 보이던데", "눈에 띄던데")) and "잘" not in lead
                   for lead in leads)


def test_brand_particle_follows_the_name():
    assert P.with_i("운명원") == "운명원이" and P.with_i("사주나라") == "사주나라가"
    assert P.fill_hearsay("{brand_i} 잘 본다던데", "사주나라") == "사주나라가 잘 본다던데"


def test_good_examples_use_different_reputations_and_one_relays_a_friend():
    marks = ("잘 보기로 유명하다던데", "잘 맞는다고 하던데", "잘 본다고들 하던데",
             "그렇게 잘 본다고 하던데")
    used = [next(m for m in marks if m in ex.body) for ex in P.GOOD_EXAMPLES]
    assert len(set(used)) == 4, used
    assert any("친구가" in ex.body and "봤는데" in ex.body for ex in P.GOOD_EXAMPLES)


def test_prompt_states_the_persona():
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=FACTS)
    assert "연애 사주 잘 봐주는 곳으로 유명한 곳" in system
    assert "남이 본 얘기를 전하는 것" in system
    assert "운명원은 연애 사주를 잘 봐주는 곳으로 유명하다" in system  # 사실 문장


# ---------------------------------------------------------------- 설정 기본값


def test_brand_facts_default_follows_the_assignment(clean_env, tmp_path):
    settings = load_settings(env_path=tmp_path / "없음.env")
    assert settings.brand_facts == ("운명원은 연애 사주를 잘 봐주는 곳으로 유명하다",)


def test_old_saved_default_gives_way_but_edited_facts_stay():
    old = {"brand.facts": ["운명원은 연애 사주 상담을 하는 곳이다"], "limits.daily_max_comments": 5}
    assert forget_old_defaults(old) == {"limits.daily_max_comments": 5}
    mine = {"brand.facts": ["운명원은 연애 사주 상담을 하는 곳이다", "운명원은 온라인으로 "
        "상담한다"]}
    assert forget_old_defaults(mine) == mine


def test_old_saved_default_in_user_folder_loads_the_new_default(clean_env, tmp_path):
    from app.user_settings import UserStore

    store = UserStore(tmp_path / "user")
    store.write_values({"brand.facts": ["운명원은 연애 사주 상담을 하는 곳이다"]})
    settings = load_settings(env_path=None, environ={}, user_dir=tmp_path / "user")
    assert settings.brand_facts == DEFAULT_BRAND_FACTS
