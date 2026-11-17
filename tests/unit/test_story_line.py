"""한 줄기 이야기(2026-11-18 기획 담당 D).

- D-1: ⑤의 기본 꼴은 「저도 + [이 영상 고민에서 나온, 사주로 알고 싶은 것] + 보러 가겠다는 말」.
  코드가 셋 중 둘에 정해 준다(`prompts.assign_reason`), 나머지는 상태 까닭·까닭 없음(본보기 꼴).
  끝은 가 보다·보러 가다·상담받다·사주 보다 쪽 의향(V14 ⑤가 받는다), 「~인지 궁금하네요」만은
  안 된다.
- D-2: ①은 남의 마음 짐작이 아니라 보는 내 반응(S20). 막연한 내 처지 한마디(「저도 미련 많은
  편이라」)는 지어낸 후기가 아니다(S5·AI 검수 (마)가 짚지 않는다).
- D-3: 잇는 문장 → 알고 싶은 것이 한 줄기로, 같은 낱말을 되풀이하지 않는다(S19). 정했는데 알고
  싶은 것이 없으면 S18.
"""

from __future__ import annotations

import random

import pytest

from app.analysis import review as R
from app.analysis import style as S
from app.analysis.validator import ValidatorRules, validate
from app.config import DEFAULT_BRAND_FACTS
from app.llm import prompts as P

BRAND = "운명원"
RULES = ValidatorRules(min_chars=40, max_chars=120, brand=BRAND, disclosure="[광고]")
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
KEYS = ["하루에 한 번 연락"]
REACTION = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "
LEAD = "요즘 운명원이 연애사주를 그렇게 잘 본다고 하더라구요. "
WISHES = ("이 사람이랑 맞는지", "언제쯤 짝을 만나는지", "둘이 궁합이 맞는지",
          "연애운이 언제 풀릴지")

# 기획 담당이 든 목표 본보기(재회 영상)
TARGET = ("[광고] 사진 200장을 못 지웠다니 그 마음 알 것 같아요ㅠㅠ 저도 미련 많은 편이라.. 다시 "
          "만날 인연은 따로 있나 봐요. 요새 운명원이 연애사주를 특히 잘 맞춘다고 하던데, 저도 "
          "재회운이 있는지 한번 보러 가려구요.")
TARGET_CONTEXT = "헤어진 연인과 찍은 사진 200장을 아직 못 지웠다는 사연, 재회를 바라는 마음"


def _run(text: str, context: str = CONTEXT, keys=KEYS, quote: str = "하루에 한 번 연락"):
    return validate(
        text, context_text=context, rules=RULES, brand_facts=list(DEFAULT_BRAND_FACTS),
        previous_texts=[], evidence_quote=quote, key_phrases=keys,
    )


def _style(text: str, **kw) -> list[str]:
    kw.setdefault("key_phrases", KEYS)
    return S.style_issues(text, brand=BRAND, disclosure="[광고]", **kw)


def _codes(issues: list[str]) -> list[str]:
    return [i.split(" ", 1)[0] for i in issues]


# --- D-1: 알고 싶은 것 꼴 -------------------------------------------------------------------


@pytest.mark.parametrize("wish", WISHES)
def test_every_wish_ending_passes_v14_and_is_read_as_a_wish(wish):
    for when in P.END_WHENS:
        for action in P.WISH_ACTIONS:
            text = f"{REACTION}{LEAD}저도 {wish} {when} {action}."
            result = _run(text)
            assert result.passed, (text, result.failure_lines())
            assert P.reason_kind(text, BRAND) == P.REASON_WISH, text
            assert P.intent_reason(text, BRAND) == wish, text


@pytest.mark.parametrize("ending", [
    "저도 이 사람이랑 맞는지 궁금하네요.",
    "저도 언제쯤 짝을 만나는지 궁금해지네요.",
    "저도 둘이 궁합이 맞는지 알고 싶네요.",
])
def test_wish_that_only_wonders_still_fails_v14(ending):
    # 「궁금하다」로만 끝나면 가 보겠다는 말이 없다(V14 ⑤) — 넓힌 것은 보러 가다·보고 싶다 쪽뿐
    result = _run(REACTION + LEAD + ending)
    assert not result.passed
    assert any("V14" in line for line in result.failure_lines())


def test_state_reason_and_no_reason_are_told_apart_from_a_wish():
    state = REACTION + LEAD + "저도 연락 문제로 한번 가보려구요."
    assert P.reason_kind(state, BRAND) == P.REASON_STATE
    assert P.reason_kind(REACTION + LEAD + "저도 한번 가보려구요.", BRAND) == P.REASON_NONE
    assert P.is_wish("다시 만날 인연인지") and P.is_wish("결혼운이 언제 들어오는지")
    assert not P.is_wish("연락 문제로") and not P.is_wish("이게 뭔지")  # 사주로 볼 것이 없다


def _body(kind: str, n: int) -> str:
    end = {P.REASON_WISH: f"저도 {WISHES[n % len(WISHES)]} 한번 보러 가려구요.",
           P.REASON_STATE: "저도 연락 문제로 한번 가보려구요.",
           P.REASON_NONE: "저도 한번 가보려구요."}[kind]
    return REACTION + LEAD + end


def test_assign_reason_gives_a_wish_to_about_two_of_three():
    shown: list[str] = []  # 최신이 앞
    kinds = []
    for n in range(30):
        same_video = shown[:1] if n % 2 else []  # 영상당 초안 둘
        kind = P.assign_reason(BRAND, shown, same_video, bridge=bool(n % 3))
        kinds.append(kind)
        shown.insert(0, _body(kind, n))
    share = kinds.count(P.REASON_WISH) / len(kinds)
    assert 0.55 <= share <= 0.75, kinds
    assert kinds[0] == P.REASON_WISH  # 처음 초안은 알고 싶은 것
    assert P.REASON_STATE in kinds  # 상태 까닭도 섞인다


def test_assign_reason_never_leaves_both_bridge_and_reason_out():
    wished = [_body(P.REASON_WISH, i) for i in range(3)]
    # 잇는 문장이 없으면 까닭 없음은 고르지 않는다
    assert P.assign_reason(BRAND, wished, [], bridge=False) == P.REASON_STATE
    # 같은 영상 앞 초안에 까닭이 없으면 이번에는 까닭을 넣는다
    assert P.assign_reason(BRAND, wished, [_body(P.REASON_NONE, 0)], bridge=True) == \
        P.REASON_STATE
    # 잇는 문장이 있고 같은 영상 앞 초안에 까닭이 있으면 까닭 없는 본보기 꼴도 된다
    assert P.assign_reason(BRAND, [*wished, _body(P.REASON_STATE, 0)],
                           [_body(P.REASON_WISH, 0)], bridge=True) == P.REASON_NONE


def test_wish_pieces_take_a_go_and_see_ending():
    rng = random.Random(3)
    for _ in range(12):
        pieces = P.assign_pieces(BRAND, [], rng=rng, wish=True)
        assert pieces.action in P.WISH_ACTIONS
        assert P.assign_pieces(BRAND, [], rng=rng).action in P.END_ACTIONS
    # 다시 쓸 때 조각을 읽어 내면 알고 싶은 것 끝말도 그대로 읽힌다
    text = REACTION + LEAD + "저도 둘이 궁합이 맞는지 한번 보러 가 보려고요."
    assert P.pieces_of(text, BRAND).action == "보러 가 보려고요"


def test_draft_user_asks_for_the_assigned_form():
    base = dict(analysis={"main_topic": "재회", "concern": "헤어진 사람을 못 잊겠다",
                          "tone": "t", "viewer_need": "n", "key_phrases": ["사진 200장"]},
                quote="q", source="comment", min_body=35, max_body=115)
    pieces = P.assign_pieces(BRAND, [], rng=random.Random(1), wish=True)
    wish = P.draft_user(**base, pieces=pieces, reason_kind=P.REASON_WISH, bridge=True,
                        used_reasons=["다시 만날 인연인지"])
    assert "이번 끝말은 **'저도 + [사주로 알고 싶은 것] + " in wish
    assert "'헤어진 사람을 못 잊겠다'" in wish
    assert "잇는 문장에 쓴 낱말(인연·때·궁합 등)은 알고 싶은 것에서 되풀이하지 않고" in wish
    assert "길이가 넘치면 내 처지 한마디 → 잇는 문장 순으로 뺀다(알고 싶은 것은 남긴다)" in wish
    assert "이미 쓴 까닭·알고 싶은 것: '다시 만날 인연인지'" in wish
    assert "알고 싶은 것은 '저도' 바로 뒤에" in wish
    plain = P.assign_pieces(BRAND, [], rng=random.Random(1))
    state = P.draft_user(**base, pieces=plain, reason_kind=P.REASON_STATE, bridge=True)
    assert "짧은 **상태 까닭**(12자 안)을 넣는다" in state
    assert "길이가 넘치면 내 처지 한마디 → 잇는 문장 순으로 뺀다(까닭은 남긴다)" in state
    none = P.draft_user(**base, pieces=plain, reason_kind=P.REASON_NONE, bridge=True)
    assert "이번 끝말은 까닭 없이 본보기 꼴('저도 " in none
    assert "길이가 넘치면 내 처지 한마디를 뺀다(잇는 문장은 남긴다)" in none


def test_draft_system_explains_the_wish_and_never_predicts_results():
    system = P.draft_system(brand=BRAND, disclosure="[광고]", facts=list(DEFAULT_BRAND_FACTS))
    assert "**이 영상의 고민에서 나온, 사주로 알고 싶은 것**을 넣는 것이 기본이다" in system
    assert "'~인지 궁금하네요'로만 끝내지 않는다" in system
    assert "결과를 미리 단정하지 않는다('가면 다 알려 준다던데' ✗)" in system
    # 꼴 보기는 두되 그대로 베끼지 말라고 한다
    assert "꼴 보기(그대로 베끼지 말고 이 영상의 고민으로)" in system
    for _, form in P.WISH_FORMS:
        assert P.is_wish(form), form


# --- D-3: 한 줄기 · S18 · S19 ---------------------------------------------------------------


def test_s18_when_a_wish_was_asked_but_not_written():
    state = REACTION + LEAD + "저도 연락 문제로 한번 보러 가려구요."
    assert "S18" in _codes(_style(state, reason_wanted=P.REASON_WISH))
    wish = REACTION + LEAD + "저도 이 사람이랑 맞는지 한번 보러 가려구요."
    assert "S18" not in _codes(_style(wish, reason_wanted=P.REASON_WISH))
    # 상태 까닭·까닭 없음을 정했거나, 정하지 않았으면(사람이 고친 글) 보지 않는다
    assert "S18" not in _codes(_style(state, reason_wanted=P.REASON_STATE))
    assert "S18" not in _codes(_style(state))


def test_s19_same_word_in_the_bridge_and_the_wish():
    bridge = "다시 만날 인연은 따로 있나 봐요. "
    twice = REACTION + bridge + LEAD + "저도 이 사람이 인연인지 한번 보러 가려구요."
    issues = _style(twice, need_bridge=True, bridge_wanted=True, reason_wanted=P.REASON_WISH)
    assert "S19" in _codes(issues), issues
    assert any("'인연'" in i for i in issues if i.startswith("S19"))
    other = REACTION + bridge + LEAD + "저도 재회운이 있는지 한번 보러 가려구요."
    assert "S19" not in _codes(_style(other, need_bridge=True, bridge_wanted=True,
                                      reason_wanted=P.REASON_WISH))


def test_target_sample_passes_and_reads_as_one_story():
    keys = ["사진 200장"]
    # 표기를 붙이면 123자로 120자를 넘는다 — 길이 줄의 차례대로 내 처지 한마디부터 빼면 통과
    over = _run(TARGET, context=TARGET_CONTEXT, keys=keys, quote="사진 200장")
    assert [c.code for c in over.checks if not c.passed] == ["V1"]
    short = TARGET.replace(" 저도 미련 많은 편이라..", "")
    result = _run(short, context=TARGET_CONTEXT, keys=keys, quote="사진 200장")
    assert result.passed, result.failure_lines()
    # 표기를 끄면(V4 「표기 끔」) 본보기 그대로 통과
    bare = TARGET.removeprefix("[광고] ")
    off = validate(bare, context_text=TARGET_CONTEXT, rules=RULES,
                   brand_facts=list(DEFAULT_BRAND_FACTS), previous_texts=[],
                   evidence_quote="사진 200장", key_phrases=keys, disclosure_required=False)
    assert off.passed, off.failure_lines()
    for text in (TARGET, short):
        issues = [i for i in _style(text, key_phrases=keys, context=TARGET_CONTEXT,
                                    need_bridge=True, bridge_wanted=True,
                                    reason_wanted=P.REASON_WISH) if not i.startswith("S1 ")]
        # 「재회운이 있는지」는 꼴 보기 문구 그대로라 모델 초안이면 S21로 새로 쓰게 한다
        # (그 밖의 문제는 없다)
        assert _codes(issues) == ["S21"], issues
    assert P.reason_kind(TARGET, BRAND) == P.REASON_WISH
    assert P.intent_reason(TARGET, BRAND) == "재회운이 있는지"
    assert P.bridge_sentence(TARGET, BRAND) == "다시 만날 인연은 따로 있나 봐요."


def test_s21_copying_a_form_example_word_for_word():
    # 루나 실제 실행 24개 중 2개가 꼴 보기 문구를 그대로 옮겼다(「이 사람이 인연인지」)
    for _, form in P.WISH_FORMS:
        text = f"{REACTION}{LEAD}저도 {form} 한번 보러 가려구요."
        assert "S21" in _codes(_style(text, reason_wanted=P.REASON_WISH)), form
    own = REACTION + LEAD + "저도 이 사람이랑 끝까지 갈지 한번 보러 가려구요."
    assert "S21" not in _codes(_style(own, reason_wanted=P.REASON_WISH))
    # 정하지 않은 글(사람이 고친 글)은 보지 않는다
    copied = REACTION + LEAD + "저도 이 사람이 인연인지 한번 보러 가려구요."
    assert "S21" not in _codes(_style(copied))


def test_s22_wish_written_before_the_brand():
    # 루나 실제 실행에서 나온 꼴: 알고 싶은 것이 운명원 문장 앞에 붙고 「저도」가 두 번
    bad = ("[광고] 썸/연애 고민을 차분하게 풀어가는 말이 은근 와닿네요... 저도 맞는 사람을 만날지 "
           "요즘 운명원이 연애 쪽 사주를 진짜 잘 맞춘다고 소문났던데, 저도 기회 되면 보러 가 볼 "
           "생각이에요")
    assert "S22" in _codes(_style(bad, key_phrases=[], reason_wanted=P.REASON_WISH))
    # 처지 한마디의 「저도」가 따로 한 문장이면 괜찮다
    fine = (REACTION + "저도 미련 많은 편이라.. " + LEAD
            + "저도 이 사람이랑 맞는지 한번 보러 가려구요.")
    assert "S22" not in _codes(_style(fine, reason_wanted=P.REASON_WISH))


# --- D-2: 내 반응 · 처지 한마디 -------------------------------------------------------------


@pytest.mark.parametrize("first", [
    "[광고] 사진 200장을 못 지웠다니 미련인가 싶겠어요.",
    "[광고] 하루 연락으로 싸우다니 서운한가 싶었겠어요.",
])
def test_s20_guessing_someone_elses_mind(first):
    issues = _style(first + " " + LEAD + "저도 한번 가보려구요.", reason_wanted=P.REASON_NONE)
    assert "S20" in _codes(issues), issues


def test_s20_leaves_my_own_reaction_alone():
    for first in ("[광고] 사진 200장을 못 지웠다니 그 마음 알 것 같아요ㅠㅠ",
                  "[광고] 하루에 한 번 연락이라니 내 얘기 같아서 찔리네."):
        issues = _style(first + " " + LEAD + "저도 한번 가보려구요.", reason_wanted=P.REASON_NONE)
        assert "S20" not in _codes(issues), issues


@pytest.mark.parametrize("line", ["저도 미련 많은 편이라..", "맨날 썸만 타다 끝나는 1인ㅋㅋ",
                                  "저도 연애만 하면 차이는 편이라"])
def test_a_vague_line_about_my_own_situation_is_not_flagged(line):
    text = f"{REACTION}{line} {LEAD}저도 이 사람이랑 맞는지 한번 보러 가려구요."
    result = _run(text)
    assert result.passed, result.failure_lines()
    issues = _style(text, context=CONTEXT, reason_wanted=P.REASON_WISH)
    assert issues == [], issues


def test_moving_video_numbers_onto_myself_is_still_flagged():
    context = "3년 사귄 커플이 " + CONTEXT
    text = (REACTION + "저도 3년 사귄 사이라.. " + LEAD
            + "저도 이 사람이랑 맞는지 한번 보러 가려구요.")
    assert "S5" in _codes(_style(text, context=context))


def test_boss_models_still_pass_and_story_checks_leave_them_alone():
    for model in P.BRAND_MODELS:
        text = REACTION + model
        assert _run(text).passed, (model, _run(text).failure_lines())
        codes = _codes(_style(text))
        assert not {"S18", "S19", "S20"} & set(codes), (model, codes)


# --- AI 검수 -------------------------------------------------------------------------------


def test_review_asks_whether_it_is_one_story_and_lists_the_situation_line():
    system = R.review_system(brand=BRAND)
    assert "영상 얘기(첫 문장)와 끝의 알고 싶은 것" in system
    assert "같은 고민인가. 왜 운명원에 가 보려는지가 글 안에서 읽히는가" in system
    assert "알고 싶은 것이 영상 고민과 딴 얘기면 false다" in system
    assert "'저도 재회운이 있는지 한번 보러 가려구요'" in system
    assert "(마) 막연한 내 처지 한마디: '저도 미련 많은 편이라..'" in system
    assert "영상 속 숫자·사정을 그대로 옮긴 것만 6번이다" in system
