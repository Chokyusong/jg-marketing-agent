"""운명원 대목 다섯 조각(2026-11-17 대표).

대표가 정한 짜임: ① 때(요즘·요새·최근·최근에) ② 이름 ③ 연애 사주(연애사주·연애 쪽 사주) ④ 잘 본다는
평판을 들은 얘기로 ⑤ 이용 의향(가 보다·방문하다·상담받다·사주 보다·알아보다 + 려구요·고 싶네요·볼까
해요·생각이에요). 기본 문장은 「요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요.」

이 파일이 못 박는 것:
- **대표의 본보기 10개는 늘 통과한다**(영상 반응 한 문장을 앞에 붙여 규칙 14개 + 다듬기 검사).
- 조각을 바꾼 조합 12개 이상도 통과한다.
- 하나씩 빠진 글은 V14에 걸리고, 빠진 조각 이름을 알린다.
- V8(써 본 척)·V10(내 단정)의 경계: 의향은 통과, 써 본 말·내 단정은 걸린다.
- 편한 맞춤법(하더라구요·하더라구여·가보려구요·봐보려구요, 연애사주)을 받아 준다.
"""

from __future__ import annotations

import random

import pytest

from app.analysis import style as S
from app.analysis.validator import ValidatorRules, brand_pieces, validate
from app.config import DEFAULT_BRAND_FACTS
from app.llm import prompts as P

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = list(DEFAULT_BRAND_FACTS)
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
KEYS = ["하루에 한 번 연락"]
# 영상 반응 한 문장(대표: 영상 반응은 한 문장, 길어야 두 문장)
REACTION = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "

# 대표가 2026-11-17에 쓴 본보기 10개 — 한 글자도 바꾸지 않는다
BOSS_MODELS = [
    "요즘 운명원이 연애사주를 그렇게 잘 본다고 하더라구요. 저도 언제 한번 방문해서 사주 봐보려구요.",  # noqa: E501
    "요새 운명원이 연애사주를 진짜 잘 맞춘다고 하던데, 저도 조만간 한번 가보고 싶네요.",
    "최근에 운명원이 연애사주를 엄청 잘 봐준다는 얘기를 들었는데, 저도 기회 되면 상담받아보고 싶어요.",  # noqa: E501
    "요즘 운명원이 특히 연애사주를 잘 본다고 하더라구여. 저도 한번 방문해 볼까 싶네요.",
    "요새 운명원에서 연애사주를 되게 잘 봐준다고 하던데, 저도 언제 시간 내서 가보려구요.",
    "요즘 운명원 연애사주가 잘 맞는다는 이야기가 있던데, 저도 한번 상담받아보고 싶네요.",
    "최근 운명원이 연애사주를 잘 봐준다고 하더라구요. 저도 궁금해서 한번 가볼 생각이에요.",
    "요즘 운명원 연애사주가 꽤 정확하다는 얘기가 있더라구요. 저도 한번 직접 알아보고 싶어요.",
    "요새 운명원이 연애 쪽 사주를 잘 본다고 하던데, 저도 조만간 한번 방문해 볼까 해요.",
    "요즘 운명원이 연애사주를 진짜 잘 맞춘다고 하더라구여. 저도 언제 한번 사주 봐보고 싶네요.",
]
BASE = "요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요."


def _run(text: str, *, disclosure_required: bool = True):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        evidence_quote="하루에 한 번 연락", key_phrases=KEYS,
        disclosure_required=disclosure_required,
    )


def _style(text: str, **kw) -> list[str]:
    return S.style_issues(text, brand="운명원", disclosure="[광고]", key_phrases=KEYS,
                          context=CONTEXT, **kw)


def _check(result, code: str):
    return next(c for c in result.checks if c.code == code)


# ---------------------------------------------------------------- 대표의 본보기 10개


def test_boss_models_are_the_ones_in_the_prompt():
    assert list(P.BRAND_MODELS) == BOSS_MODELS


@pytest.mark.parametrize("model", BOSS_MODELS)
def test_boss_models_always_pass(model):
    """대표의 본보기 10개는 늘 통과한다(규칙 14개 + 다듬기 검사)."""
    text = REACTION + model
    result = _run(text)
    assert len(result.checks) == 14 and result.passed, (model, result.failure_lines())
    assert _style(text) == [], model
    assert brand_pieces(text, "운명원", "[광고]") == []
    # 광고 표기를 끈 글(내 채널 영상)도 같다
    plain = REACTION.replace("[광고] ", "") + model
    assert _run(plain, disclosure_required=False).passed
    assert S.style_issues(plain, brand="운명원", disclosure="", key_phrases=KEYS) == []


def test_base_sentence_passes():
    text = REACTION + BASE
    assert _run(text).passed and _style(text) == []


# ---------------------------------------------------------------- 조각을 바꾼 조합

COMBOS = [
    "요즘 운명원이 연애 사주를 진짜 잘 본다고 하던데 저도 조만간 한번 가 보려고요.",
    "요새 운명원 연애 사주가 그렇게 잘 맞는다고 하더라구요. 저도 기회 되면 방문해 볼까 해요.",
    "최근에 운명원이 연애 쪽 사주를 잘 봐준다는 얘기를 들었는데 저도 한번 상담받아보고 싶어요.",
    "최근 운명원에서 연애사주를 되게 잘 봐준다고 하던데 저도 언제 한번 사주 봐보고 싶네요.",
    "요즘 들어 운명원 연애 사주가 꽤 정확하다는 이야기가 있던데 저도 한번 직접 알아보고 싶어요.",
    "요새 들어 운명원이 연애사주를 엄청 잘 맞춘다고 하더라구여. 저도 궁금해서 한번 가볼 "
    "생각이에요.",
    "요즘 운명원이 연애 사주 잘 본다고들 하던데 저도 언제 시간 내서 가보려구요.",
    "요새 운명원이 연애 사주를 특히 잘 본다던데 저도 다음에 한번 찾아가 보려고요.",
    "최근에 운명원 연애 사주가 정말 잘 맞는다는 얘기가 있더라구요. 저도 한번 들러 볼까 해요.",
    "요즘 운명원에서 연애 쪽 사주를 잘 봐준다고 하더라구요. 저도 기회 되면 상담받아 볼 생각이에요.",
    "요새 운명원이 연애사주를 꽤 잘 본다고 하던데, 저도 조만간 한번 방문해 볼까 싶네요.",
    "최근 운명원 연애 사주가 진짜 정확하다고 하던데 저도 언제 한번 가보고 싶네요.",
    "요즘 운명원이 연애 사주로 유명하다던데 저도 한번 방문해서 사주 봐보려구요.",
]


@pytest.mark.parametrize("lead", COMBOS)
def test_combinations_of_pieces_pass(lead):
    text = REACTION + lead
    result = _run(text)
    assert result.passed, (lead, result.failure_lines())
    assert _style(text) == [], lead


def test_at_least_twelve_combinations():
    assert len(COMBOS) >= 12 and len(set(COMBOS)) == len(COMBOS)


def test_suggested_passages_from_the_piece_lists_pass():
    # 조각별 목록에서 고른 꺼내는 말 + 끝말은 늘 다섯 조각을 갖춘다
    rng = random.Random(7)
    for _ in range(20):
        lead = P.hearsay_choices("운명원", [], n=1, rng=rng)[0]
        ending = P.ending_choices([], n=1, rng=rng)[0]
        joint = ". " if lead.endswith(("요", "여")) else " "
        text = f"{REACTION}{lead}{joint}{ending}."
        assert _run(text).passed, (text, _run(text).failure_lines())


# ---------------------------------------------------------------- 하나씩 빠진 글

MISSING = [
    ("운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요.", "'요즘/요새'가 없습니다"),
    ("요즘 운명원 잘 본다고 하던데 저도 언제 한번 가 보려고요.", "연애 사주가 없습니다"),
    ("요즘 운명원 연애 사주 얘기가 자주 보이던데 저도 언제 한번 가 보려고요.",
     "잘 본다는 평판(~다고 하던데)이 없습니다"),
    ("요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 궁금하네요.",
     "가 보겠다는 말(가 보려고요 등)이 없습니다"),
]


@pytest.mark.parametrize(("lead", "words"), MISSING)
def test_one_missing_piece_fails_and_is_named(lead, words):
    result = _run(REACTION + lead)
    v14 = _check(result, "V14")
    assert not v14.passed and words in v14.message, v14.message
    # 빠진 것은 그 조각 하나뿐이다
    assert v14.message.count("없습니다") == 1, v14.message


def test_missing_name_is_left_to_v5():
    text = REACTION + "요즘 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요."
    result = _run(text)
    assert not _check(result, "V5").passed and _check(result, "V14").passed


# ---------------------------------------------------------------- V8·V10 경계

HEAD = "요즘 운명원 연애 사주 잘 본다고 하던데 "


@pytest.mark.parametrize("tail", [
    "저도 상담받아보고 싶어요.", "저도 언제 한번 봐보려구요.", "저도 조만간 가보고 싶네요.",
    "저도 한번 직접 알아보고 싶어요.", "저도 한번 상담받아보려구요.",
])
def test_v8_lets_intent_through(tail):
    assert _check(_run(REACTION + HEAD + tail), "V8").passed, tail


@pytest.mark.parametrize("tail", [
    "저도 상담받아봤어요.", "저도 가봤는데 좋더라고요.", "저도 봤더니 잘 맞았어요.",
])
def test_v8_still_catches_having_used_it(tail):
    assert not _check(_run(REACTION + HEAD + tail), "V8").passed, tail


@pytest.mark.parametrize("lead", [
    "요즘 운명원 연애사주가 꽤 정확하다는 얘기가 있더라구요. 저도 한번 가 보려고요.",
    "요새 운명원이 연애사주를 진짜 잘 맞춘다고 하던데, 저도 한번 가 보려고요.",
])
def test_v10_lets_hearsay_through(lead):
    assert _check(_run(REACTION + lead), "V10").passed, lead


@pytest.mark.parametrize("lead", [
    "요즘 운명원 연애 사주 정확해요. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애 사주 잘 맞춰요. 저도 한번 가 보려고요.",
])
def test_v10_still_catches_my_own_claim(lead):
    assert not _check(_run(REACTION + lead), "V10").passed, lead


# ---------------------------------------------------------------- 편한 맞춤법

@pytest.mark.parametrize("lead", [
    "요즘 운명원이 연애사주를 잘 본다고 하더라구요. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애사주를 잘 본다고 하더라구여. 저도 한번 가 보려고요.",
    "요즘 운명원이 연애 사주를 잘 본다고 하던데 저도 한번 가보려구요.",
    "요즘 운명원이 연애 사주를 잘 본다고 하던데 저도 한번 사주 봐보려구요.",
])
def test_casual_spellings_pass(lead):
    assert _run(REACTION + lead).passed, (lead, _run(REACTION + lead).failure_lines())


def test_rotation_counts_casual_spellings_as_the_same_piece():
    assert P.fold("하더라구요") == P.fold("하더라고요") == P.fold("하더라구여")
    assert P.fold("가보려구요") == P.fold("가 보려고요")
    used = ["[광고] … 요즘 운명원이 연애사주를 잘 본다고 하더라구여. 저도 한번 가보려구요."]
    loves = P._least_used(P.LEAD_LOVES, used, (), random.Random(1))
    # 「연애사주」와 「연애 사주」는 같은 조각으로 센다(둘 다 뒤로 간다)
    assert loves[0] == "연애 쪽 사주" and set(loves[1:]) == {"연애사주", "연애 사주"}
    tails = P._least_used(P.LEAD_TAILS, used, (), random.Random(1))
    assert set(tails[-2:]) == {"고 하더라구요", "고 하더라구여"}


# ---------------------------------------------------------------- 본보기를 연달아 옮기지 않게(S8)


def test_copied_model_finds_the_model_lead():
    for i, model in enumerate(BOSS_MODELS):
        assert P.copied_model(REACTION + model) == i
    assert P.copied_model(REACTION + BASE) == -1


def test_s8_when_two_drafts_in_a_row_copy_the_same_model():
    first = REACTION + BOSS_MODELS[1]
    again = "[광고] 연락 하나로 싸운다니 속상하네요ㅠ " + BOSS_MODELS[1]
    found = _style(again, last_shown=first)
    assert any(i.startswith("S8") and "본보기 2번" in i for i in found), found
    # 다른 꺼내는 말이면 괜찮다
    other = "[광고] 연락 하나로 싸운다니 속상하네요ㅠ " + COMBOS[0]
    assert not any(i.startswith("S8") for i in _style(other, last_shown=first))
    # 앞 초안이 본보기가 아니면 S8은 없다
    assert not any(i.startswith("S8") for i in _style(again, last_shown=REACTION + BASE))


def test_draft_user_tells_not_to_reuse_the_model_just_copied():
    text = P.draft_user(analysis={"topic": "연락", "concern": "c", "tone": "t",
                                  "viewer_needs": "n"},
                        quote="q", source="comment", min_body=35, max_body=115, last_model=4)
    assert "바로 앞 초안이 본보기 5번의 꺼내는 말을 그대로 썼다" in text
