"""② 잇는 한 문장(2026-11-18 기획 담당, 대표 승인).

영상 반응 → 잇는 한 문장(이 고민이 인연·타이밍·때·궁합·맞는 사람의 문제일지도 모른다는 혼잣말)
→ 운명원 대목 다섯 조각. 잇는 문장·까닭이 둘 다 없는 모델 초안은 다듬기 검사 S11이 한 번 다시
쓰게 한다(규칙 검사로는 막지 않는다 — 사람이 고친 글과 대표 본보기 10개는 그대로 통과).
"""

from __future__ import annotations

import pytest

from app.analysis import style as S
from app.analysis.validator import ValidatorRules, validate
from app.config import DEFAULT_BRAND_FACTS
from app.llm import prompts as P

REACTION = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "
LEAD = "요즘 운명원이 연애사주를 그렇게 잘 본다고 하더라구요. "
END = "저도 언제 한번 가보려구요."
KEYS = ["하루에 한 번 연락"]

# 기획 담당이 든 꼴(그대로 프롬프트에 넣지는 않는다) + 같은 결의 다른 말
BRIDGES = [
    "이런 건 결국 인연이 따로 있나 싶기도 해요.",
    "결국 타이밍 문제인가 싶네요.",
    "맞는 사람은 따로 있는 건가...",
    "다 때가 있는 건가 봐요.",
    "노력만으론 안 되는 게 있나 싶네.",
    "궁합이라는 게 진짜 있긴 한가 봐요.",
    "이것도 다 정해진 짝이 있는 걸까요.",
]


RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"


def _run(text: str):
    return validate(
        text, context_text=CONTEXT, rules=RULES, brand_facts=list(DEFAULT_BRAND_FACTS),
        previous_texts=[], evidence_quote="하루에 한 번 연락", key_phrases=KEYS,
    )


def _style(text: str, **kw) -> list[str]:
    return S.style_issues(text, brand="운명원", disclosure="[광고]", key_phrases=KEYS, **kw)


def _codes(issues: list[str]) -> list[str]:
    return [i.split(" ", 1)[0] for i in issues]


@pytest.mark.parametrize("bridge", BRIDGES)
def test_bridge_sentence_is_found_between_reaction_and_brand(bridge):
    text = REACTION + bridge + " " + LEAD + END
    assert P.bridge_sentence(text, "운명원") == bridge


def test_no_bridge_when_brand_comes_right_after_the_reaction():
    assert P.bridge_sentence(REACTION + LEAD + END, "운명원") == ""


def test_reaction_itself_is_not_a_bridge_even_with_the_words():
    # 첫 문장(영상 반응)에 「인연」이 있어도 잇는 문장이 아니다
    text = "[광고] 인연이면 다시 만난다는 말이 계속 남네요. " + LEAD + END
    assert P.bridge_sentence(text, "운명원") == ""


def test_bridge_sentence_must_not_talk_about_the_brand_or_saju():
    text = REACTION + "사주로 보면 타이밍이 있나 싶네요. " + LEAD + END
    assert P.bridge_sentence(text, "운명원") == ""


def test_sentence_without_bridge_words_is_not_a_bridge():
    text = REACTION + "보는 제가 다 답답하네. " + LEAD + END
    assert P.bridge_sentence(text, "운명원") == ""


# ---------------------------------------------------------------- S11


def test_s11_when_neither_bridge_nor_reason():
    text = REACTION + LEAD + END
    assert "S11" in _codes(_style(text, need_bridge=True))


def test_s11_is_off_unless_asked_so_human_text_and_boss_models_are_untouched():
    text = REACTION + LEAD + END
    assert "S11" not in _codes(_style(text))
    for model in P.BRAND_MODELS:
        assert "S11" not in _codes(_style(REACTION + model)), model


@pytest.mark.parametrize("bridge", BRIDGES)
def test_bridge_satisfies_s11_and_passes_all_rules(bridge):
    text = REACTION + bridge + " " + LEAD + END
    assert _style(text, need_bridge=True) == [], text
    result = _run(text)
    assert result.passed, result.failure_lines()


def test_reason_alone_also_satisfies_s11():
    text = REACTION + LEAD + "저도 연락 문제로 조만간 한번 가보려구요."
    assert P.intent_reason(text, "운명원")
    assert "S11" not in _codes(_style(text, need_bridge=True))


def test_bridge_and_reason_together_pass():
    text = "[광고] 하루에 한 번 연락으로 싸운다니ㅠㅠ 결국 맞는 사람 문제인가. " + LEAD + \
        "저도 연락 문제로 조만간 가보려구요."
    assert len(text) <= 120
    assert _style(text, need_bridge=True) == []
    assert _run(text).passed


@pytest.mark.parametrize("model", P.BRAND_MODELS)
def test_boss_models_with_a_bridge_still_pass(model):
    text = REACTION + "결국 타이밍 문제인가 싶네요. " + model
    if len(text) > 120:
        pytest.skip("본보기가 길어 잇는 문장까지 넣으면 120자를 넘는다(모델에게는 ①을 줄이게 한다)")
    assert _run(text).passed, (text, _run(text).failure_lines())
    assert "S11" not in _codes(_style(text, need_bridge=True))


def test_rule_checks_never_require_a_bridge():
    # V는 잇는 문장을 보지 않는다(사람이 고친 글은 그대로 통과)
    assert _run(REACTION + LEAD + END).passed


# ---------------------------------------------------------------- S12


def test_s12_same_bridge_as_an_earlier_draft():
    text = REACTION + "결국 타이밍 문제인가 싶네요. " + LEAD + END
    got = _style(text, need_bridge=True, used_bridges=["결국 타이밍 문제인가 싶네요"])
    assert "S12" in _codes(got)
    # 2026-11-18(기획 담당 C): 낱말이 겹치는 것(끝만 다름)은 괜찮다 — 통째로 같을 때만
    # (예전에는 「싶어요」로 끝난 이 문장도 70% 넘게 같아 잡았다)
    near = _style(text, need_bridge=True, used_bridges=["결국 타이밍 문제인가 싶어요."])
    assert "S12" not in _codes(near)


def test_s12_copying_a_good_example_bridge():
    copied = P.EXAMPLE_BRIDGES[0]
    text = REACTION + copied + " " + LEAD + END
    assert "S12" in _codes(_style(text, used_bridges=P.EXAMPLE_BRIDGES))


def test_s12_different_bridges_pass():
    text = REACTION + "다 때가 있는 건가 봐요. " + LEAD + END
    used = ["결국 타이밍 문제인가 싶네요.", "맞는 사람은 따로 있는 건가..."]
    assert "S12" not in _codes(_style(text, used_bridges=used))


# ---------------------------------------------------------------- 프롬프트


def test_good_examples_show_bridges_but_their_words_are_marked_as_not_to_copy():
    assert len(P.EXAMPLE_BRIDGES) >= 2
    for ex in P.GOOD_EXAMPLES:
        bridge = P.bridge_sentence(ex.body, "운명원")
        assert bridge or P.intent_reason(ex.body, "운명원"), ex.body  # 적어도 하나
        if bridge:
            assert "그대로 쓰지 않는다" in ex.why


def test_draft_user_asks_for_a_bridge_and_lists_used_ones():
    user = P.draft_user(
        analysis={"concern": "연락 횟수 때문에 맨날 싸우는데 우리 괜찮은 걸까"}, quote="q",
        source="comment", min_body=35, max_body=115, bridge=True, reason=True,
        used_bridges=["결국 타이밍 문제인가 싶네요."],
    )
    assert "**잇는 한 문장**(12~20자)" in user
    assert "인연·타이밍·때·궁합·맞는 사람" in user
    assert "권태기·다툼·성격 차이 → 맞는 사람·궁합" in user
    assert "'운명원'·'사주'는 이 문장에 쓰지 않는다" in user
    assert "이미 쓴 잇는 문장: '결국 타이밍 문제인가 싶네요.'" in user
    assert "영상 반응은 25~35자로 짧게" in user
    assert "길이가 넘치면 까닭을 뺀다" in user


def test_draft_user_without_bridge_says_nothing_about_it():
    user = P.draft_user(analysis={"concern": "c"}, quote="q", source="comment", min_body=35,
                        max_body=115)
    assert "잇는 한 문장" not in user


def test_draft_system_explains_the_three_blocks():
    system = P.draft_system(brand="운명원", disclosure="[광고]", facts=())
    assert "① 영상 반응 한 문장 → ② 잇는 한 문장 → ③ 운명원 대목" in system
    assert "② **잇는 한 문장**(12~20자쯤)" in system
    assert "'운명원'·'사주'를 쓰지 않는다" in system
    # 그대로 베낄 수 있는 문구로 주지 않는다: 기획 담당이 든 예 문장은 프롬프트에 없다
    for example in BRIDGES[:5]:
        assert example.rstrip(".") not in system
