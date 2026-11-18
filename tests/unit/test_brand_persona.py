"""운명원 페르소나(2026-11-17 대표): 「연애 사주 잘 봐주는 곳으로 유명한 곳」(과제 원문).

- 들은 얘기 꼴의 평판은 통과한다: 「잘 맞는다고 하던데」「잘 봐준다고 하던데」.
- 남이 **직접 받아 본 결과**나 설정에 없는 새 평판·사례(예약·방송·경력·적중률)는 V10이 막는다
  (2026-11-18 지시서: 예전 V14의 지어낸 평판 검사를 V10으로 합쳤다).
- 그대로 막는 것: **내가 써 본 척**(V8)과 **내 단정·효능 단정**(V10).
- 댓글 프롬프트의 [운명원] 첫 줄은 설정 brand.facts에서 읽는다(지시서 4절).
"""

from __future__ import annotations

import pytest

from app.analysis.validator import ValidatorRules, invented_repute, validate
from app.config import DEFAULT_BRAND_FACTS, forget_old_defaults, load_settings
from app.llm import prompts as P

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = list(DEFAULT_BRAND_FACTS)
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
OPEN = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "


def _run(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락",
    )


PASS = [
    # 대표가 든 꼴
    "요새 운명원이 연애 사주를 그렇게 잘 본다던데 나도 한번 가 보고 싶다.",
    "요즘 운명원이 연애 사주를 잘 봐준다고 하던데 나도 한번 가 보고 싶다.",
    "요즘 운명원이 연애 사주 잘 보기로 유명하다던데 나도 한번 가 보고 싶다.",
    "요즘 주변에서 운명원 연애 사주 잘 본다고들 하던데 나도 한번 가 보고 싶다.",
    # 같은 뜻의 다른 꼴
    "요즘 운명원이 연애 사주 잘 맞춘다고 하던데 나도 한번 가 보고 싶다.",
    "요새 운명원 연애 사주가 잘 맞힌다고 하던데 나도 한번 가 보고 싶다.",
    "요즘 운명원 연애 사주 잘 맞는대요. 나도 한번 가 보고 싶다.",
    "요즘 운명원이 연애사주 잘 본다고 하는 얘기가 자주 보이던데 저도 한번 가 보려고요.",
    "요새 운명원이 연애 사주를 잘 봐준다길래 저도 한번 가 볼까 해요.",
    # 2026-11-17 대표 본보기: 정확하다는 말도 들은 얘기 꼴이면 된다
    "요즘 운명원 연애사주가 꽤 정확하다는 얘기가 있더라구요. 저도 한번 직접 알아보고 싶어요.",
    "요즘 운명원 연애 사주가 정확하다던데 나도 한번 가 보고 싶다.",
    # 2026-11-18 대표 의견: 같은 설정(연애 사주 잘 봐주는 곳으로 유명)을 다른 말로 옮긴 들은 평판
    "요즘 운명원이 연애사주로 유명하던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다고 소문났던데 저도 한번 가 보려고요.",
    "요새 운명원 연애사주가 잘 본다고 입소문이 났던데 저도 언제 한번 가 볼까 해요.",
    "요즘 운명원이 연애사주 잘 본다는 얘기가 많던데 저도 한번 가 보려고요.",
    "요즘 연애사주는 운명원이라는 말이 많던데 저도 한번 가 보려고요.",
    "요즘 주변에서 연애사주는 운명원을 많이 추천하던데 저도 한번 가 보려고요.",
    "요즘 친구가 운명원 연애사주 잘 본다고 추천하던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다는 후기가 많던데 저도 한번 가 보려고요.",
    "요새 운명원이 연애사주 잘 본다고 입소문이 났더라구요. 저도 한번 가 보려구요.",
]
# 2026-11-18 대표 의견: 설정에 없는 새 평판·사례와 남이 직접 받아 본 결과는 V10이 막는다
INVENTED = [
    "최근에 친구가 운명원에서 연애 사주 봤는데 잘 맞는다고 하던데 나도 한번 가 보고 싶다.",
    "최근에 아는 언니가 운명원에서 연애 사주 받아 봤는데 잘 봐준다던데 저도 상담받아 보고 싶어요.",
    "요즘 동생이 운명원 다녀왔는데 연애 사주 잘 맞췄대요. 나도 한번 가 보고 싶다.",
    "요즘 운명원 연애사주 잘 본다던데 예약이 석 달 밀렸다던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다고 방송에 나왔다던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다던데 연예인도 다녀갔대요. 저도 한번 가 보려고요.",
    "요즘 운명원 연애사주가 잘 맞는다던데 적중률이 높대요. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다던데 30년 경력이래요. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다던데 거기서 보고 재회했다던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다던데 결혼 날짜를 맞혔다던데 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주를 잘 본다던데 친구가 봤는데 다 맞혔대요. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주 잘 본다던데 가격도 저렴하대요. 저도 한번 가 보려고요.",
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
    ("요즘 운명원 연애 사주 정확해요. 나도 한번 가 보고 싶다.", "V10"),
    ("요즘 운명원이 연애 사주 잘 맞춰요. 나도 한번 가 보고 싶다.", "V10"),
    ("운명원 연애 사주가 용하대요. 나도 한번 보고 싶다.", "V10"),
    ("운명원이 제일 잘 본다던데 나도 한번 보고 싶다.", "V10"),
]


@pytest.mark.parametrize("lead", PASS)
def test_relayed_reputation_passes_every_rule(lead):
    result = _run(OPEN + lead)
    assert result.passed, (lead, result.failure_lines())


@pytest.mark.parametrize("lead", INVENTED)
def test_invented_reputation_and_others_results_fail_v10(lead):
    """2026-11-18 지시서: 예전 V14의 지어낸 평판 검사는 V10으로 합쳤다."""
    result = _run(OPEN + lead)
    v10 = next(c for c in result.checks if c.code == "V10")
    assert not v10.passed and "설정에 없는 평판·사례" in v10.message, (lead, v10.message)


def test_invented_words_that_are_brand_facts_pass():
    # brand.facts에 그대로 있는 말은 지어낸 것이 아니다
    lead = "요즘 운명원이 연애사주 잘 본다던데 강남역 근처래요. 저도 한번 가 보려고요."
    rules_facts = [*FACTS, "운명원은 강남역 근처에 있다"]
    result = validate(
        OPEN + lead, context_text=CONTEXT, rules=RULES, brand_facts=rules_facts, previous_texts=[],
        evidence_quote="하루에 한 번 연락",
    )
    assert next(c for c in result.checks if c.code == "V10").passed, result.failure_lines()


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
CEO_AFTER = ("좋은 소리를 들으면 스스로 움직이죠, 그 말에 매번 타박부터 한 게 생각나네요. "
             "요즘 운명원이 연애사주 잘 본다고 하는 얘기가 자주 보이던데 저도 한번 가 "
             "보려고요.")


def test_ceo_corrected_sentence_passes_all_ten_checks():
    assert len(CEO_AFTER) == 92
    result = validate(
        CEO_AFTER, context_text=CEO_CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="좋은 소리를 들으면 또 하고 싶어져요", disclosure_required=False,
    )
    assert len(result.checks) == 10 and result.passed, result.failure_lines()


def test_prompt_carries_the_persona_from_brand_facts():
    """2026-11-18 지시서: [운명원]의 첫 줄은 설정 brand.facts에서 읽는다."""
    system = P.draft_system(brand="운명원", facts=FACTS, voice="존댓말",
                            heard="요즘 자주 들어서", from_comment=False)
    assert "- 운명원은 연애 사주를 잘 봐주는 곳으로 유명하다." in system
    assert "가 본 적은 없다" in system


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


# ---------------------------------------------------------------- 들은 평판 여러 꼴


def test_heard_reviews_are_not_my_review_but_my_review_still_fails():
    ok = _run(OPEN + "요즘 운명원이 연애사주 잘 본다는 후기가 많던데 저도 한번 가 보려고요.")
    assert "V8" not in {c.code for c in ok.failures}, ok.failure_lines()
    mine = _run(OPEN + "요즘 운명원 연애사주 잘 본다던데 후기 남길게요. 저도 한번 가 보려고요.")
    assert "V8" in {c.code for c in mine.failures}


def test_invented_repute_names_the_kind():
    found = invented_repute("예약이 석 달 밀린 데라던데 이럴 땐 사주라도 보고 싶어지네요")
    assert found and found[0] == "예약·대기"


def test_reasons_and_video_words_are_not_mistaken_for_invented_facts():
    # 까닭(「재회 문제로」「배우자 운」)과 흔한 말은 새 평판이 아니다
    for lead in ("요즘 운명원이 연애사주 잘 본다던데 저도 재회 문제로 한번 가 보려고요.",
                 "요즘 운명원이 연애사주 잘 본다던데 저도 배우자 운이 궁금해서 가 보려고요.",
                 "요즘 운명원이 연애사주 잘 본다던데 저도 언제 시간 내서 가 보려고요."):
        v10 = next(c for c in _run(OPEN + lead).checks if c.code == "V10")
        assert v10.passed, (lead, v10.message)
