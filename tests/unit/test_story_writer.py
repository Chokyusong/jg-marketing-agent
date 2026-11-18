"""이야기처럼 쓰기(2026-11-18 대표 결정, `comment.writer: story`).

이 파일이 못 박는 것:
- 글쓴이 처지는 코드가 고르지 않는다 — 프롬프트에 예 여섯 개만 보이고 AI가 정한다(빼도 된다).
- 본보기 여섯 개는 기획 담당이 쓴 글 그대로다(서로 거의 안 닮았다).
- V14(이야기 방식)는 넷만 본다 — 이름 · 연애 사주(사주) · 들은 평판(「잘 본다길래」도) · 보러 갈
  뜻. 때 말은 없어도 된다. 운명원은 첫 문장에 나오지 않는다. 지어낸 평판은 두 방식 모두 걸린다.
- V11(이야기 방식): 끝 문장(운명원 문장)만 닮고 앞부분이 다르면 통과. 통째로 같으면 걸린다.
- 나쁜 꼴 검사는 S1·S4·S5·S9·S13만. S4는 「거의 똑같은」 것만(글 전체 80% 이상이거나 운명원
  문장이 글자까지 같음) — 비슷한 것은 괜찮다.
- 프롬프트: 기승전결 · 처지 예 · 근거 출처 안내(댓글·제목·설명) · 자막 없으면 짧게 · 같은 갈래의
  알고 싶은 것 · 남은 글자 수(표기 켬/끔) · 「이미 쓴 글 — 똑같이 쓰지 않는다」 · 덜어 내기 줄.
- 맥락 일치 검증: same_topic·comment_topic·one_voice·drift·natural_ad + ok·problems. 하나라도
  걸리면 문제로 보고, 벗어난 문장을 맨 앞 줄에 둔다. 화면 한 줄은 「맥락 …」.
"""

from __future__ import annotations

import pytest

from app.analysis import review as rv
from app.analysis import story as S
from app.analysis.validator import (
    ASSIGNMENT_SAMPLE,
    ValidatorRules,
    brand_in_first_sentence,
    story_pieces,
    validate,
)
from app.config import DEFAULT_BRAND_FACTS
from app.llm import prompts as P
from app.llm import story_prompts as SP

RULES = ValidatorRules(min_chars=40, max_chars=120, brand="운명원", disclosure="[광고]")
FACTS = list(DEFAULT_BRAND_FACTS)
CONTEXT = "하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다는 사연"
KEYS = ["하루에 한 번 연락"]
REACTION = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "

# 기획 담당이 2026-11-18에 쓴 본보기 여섯 개 — 한 글자도 바꾸지 않는다(6번은 기획 담당이
# 「길이는 네가 세어 맞춘다」고 해 「숨긴다는 사연,」을 「숨긴다니」로 줄였다)
PLANNER_EXAMPLES = [
    "매일 연락은 하는데 사귀자는 말이 없다니 완전 제 얘기ㅠㅠ 저도 썸만 타다 끝나는 편이라.. "
    "눈치만 보느니 인연이 따로 있나 싶어요. 운명원이 연애사주 잘 본다던데 제 짝은 언제 오는지 "
    "한번 보러 가려구요",
    "사진 200장을 못 지웠다는 말에 멈칫했네요. 저도 미련이 오래 가는 편이라.. 붙잡을 일이 아니라 "
    "다 때가 있는 것 같아요. 운명원이 연애사주 잘 본다던데 새 인연은 언제 오는지 보러 가 볼까 해요",
    "서운하다 해도 상태 메시지만 바뀐다니 듣기만 해도 답답ㅠ 저도 서운한 걸 잘 못 말하는 편인데, "
    "이쯤 되면 궁합 문제 같아요. 운명원이 연애사주 잘 본다길래 지금 사람이랑 맞는지 보러 가려구요",
    "5년을 만났는데 직업 때문에 반대라니 마음이 무겁네요. 결혼 생각이 많아진 요즘이라 남 일 같지 "
    "않고.. 결국 때가 맞아야 하나 봐요. 운명원이 연애사주 잘 봐준다던데 제 결혼운도 한번 보러 "
    "가려구요",
    "흘린 말까지 기억하면 반한 거라니, 그런 사람 못 만나 본 1인ㅋㅋ 신호 읽는 법 배워도 인연 "
    "없으면 소용없는 듯. 운명원 연애사주가 그렇게 잘 맞는다던데 나도 언제 짝 만나는지 보고 싶다",
    "부모님께 연애를 숨긴다니 남 일 같지 않네요ㅠㅠ 저도 집에 연애 얘기 꺼내기 어려운 "
    "편이라.. 떳떳하게 만날 인연은 따로 있나 싶어요. 운명원이 연애사주 잘 본다던데 지금 사람이랑 "
    "오래 갈지 보러 가려구요",
]


def _run(text: str, *, story: bool = True, context: str = CONTEXT, keys=KEYS, previous=()):
    return validate(
        text, context_text=context, rules=RULES, brand_facts=FACTS,
        previous_texts=list(previous), key_phrases=keys, story=story,
    )


def _check(result, code: str):
    return next(c for c in result.checks if c.code == code)


# ---------------------------------------------------------------- 처지 예·본보기


def test_persona_is_only_a_short_tuple_of_examples():
    # 처지 표·주제 묶음·배정 로직은 없다(2026-11-18 기획 담당) — 예 여섯 개뿐
    assert isinstance(S.PERSONA_EXAMPLES, tuple) and len(S.PERSONA_EXAMPLES) == 6
    for gone in ("PERSONAS", "GROUPS", "pick_persona", "group_of", "guess_group"):
        assert not hasattr(S, gone), gone
    for line in S.PERSONA_EXAMPLES:  # 막연하게 — 숫자·사람 없이
        assert not any(ch.isdigit() for ch in line.replace("1인", "")), line
        assert not any(w in line for w in ("남친", "여친", "오빠", "애인")), line


def test_planner_examples_are_kept_verbatim():
    assert list(S.EXAMPLES) == PLANNER_EXAMPLES


def test_planner_examples_are_not_alike_each_other():
    for i, a in enumerate(S.EXAMPLES):
        ratio, _ = S.same_text(a, [b for b in S.EXAMPLES if b != a], brand="운명원")
        assert ratio < S.SAME_TEXT - 0.3, (i, ratio)  # 가장 닮은 쌍(1·6번)도 0.46


@pytest.mark.parametrize("example", PLANNER_EXAMPLES)
def test_planner_examples_pass_story_v14(example):
    result = _run("[광고] " + example, context=example[:20], keys=None)
    assert _check(result, "V14").passed, _check(result, "V14").message
    assert story_pieces("[광고] " + example, "운명원", "[광고]") == []
    assert len("[광고] " + example) <= 120


def test_planner_example_five_ends_like_the_assignment_sample():
    # 알려 둘 것: 본보기 5의 끝 문장은 과제 예시 끝 문장과 거의 같아 V11에 걸린다(프롬프트가 경고)
    result = _run("[광고] " + PLANNER_EXAMPLES[4], context=PLANNER_EXAMPLES[4][:20], keys=None)
    assert not _check(result, "V11").passed
    assert "5번의 끝 문장은 과제 예시" in SP.story_system(brand="운명원", disclosure="[광고]",
                                                     facts=FACTS)


# ---------------------------------------------------------------- V14(이야기 방식)

STORY_OK = (
    REACTION + "저도 자주 부딪히는 편이라 맞는 사람이 따로 있나 싶어요. "
    "운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈지 보러 가려구요"
)


def test_story_v14_passes_without_a_time_word():
    result = _run(STORY_OK)
    assert result.passed, result.failure_lines()
    assert "요즘" not in STORY_OK and "요새" not in STORY_OK
    # 같은 글이 조각 맞추기 V14에는 걸린다(때가 없다) — 두 방식이 갈린다
    assert not _check(_run(STORY_OK, story=False), "V14").passed


def test_story_v14_accepts_plain_saju_and_wish_endings():
    text = (REACTION + "저도 연애만 하면 차이는 1인이라 인연은 따로 있나 봐요. "
            "운명원 사주가 그렇게 잘 맞는다던데 나도 언제 짝 만나는지 보고 싶다")
    assert _check(_run(text), "V14").passed, _check(_run(text), "V14").message


def test_brand_in_first_sentence_fails_story_v14():
    text = ("[광고] 운명원이 연애사주 잘 본다던데 하루에 한 번 연락으로 싸웠다니 저도 궁합이 "
            "맞는지 보러 가려구요")
    assert brand_in_first_sentence(text, "운명원", "[광고]")
    check = _check(_run(text), "V14")
    assert not check.passed and "첫 문장" in check.message


@pytest.mark.parametrize("cut, said", [
    ("운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈지 궁금하네요", "보러 가겠다는 말"),
    ("운명원이 잘 본다길래 지금 사람이랑 오래 갈지 보러 가려구요", "연애 사주"),
    ("운명원에서 연애사주로 지금 사람이랑 오래 갈지 보러 가려구요", "잘 본다는 평판"),
])
def test_story_v14_names_what_is_missing(cut, said):
    text = REACTION + "저도 자주 부딪히는 편이라 맞는 사람이 따로 있나 싶어요. " + cut
    check = _check(_run(text), "V14")
    assert not check.passed and said in check.message, check.message


def test_story_v14_still_blocks_invented_reputation():
    text = (REACTION + "저도 자주 부딪히는 편이라 맞는 사람이 따로 있나 싶어요. "
            "운명원이 연애사주 잘 본다던데 방송에도 나왔다던데 보러 가려구요")
    check = _check(_run(text), "V14")
    assert not check.passed and "방송" in check.message


def test_boss_models_still_pass_in_story_mode():
    from test_brand_structure import BOSS_MODELS

    for model in BOSS_MODELS:
        text = REACTION + model
        result = _run(text)
        assert len(result.checks) == 14 and result.passed, (model, result.failure_lines())


# ---------------------------------------------------------------- V11(이야기 방식)

CLOSE = "운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈 수 있을지 한번 보러 가려구요 진짜로요"
LEAD_A = "[광고] 연락 문제로 싸웠다니 공감돼요ㅠ 저도 그래서.. "
LEAD_B = "[광고] 사진 못 지운 얘기 찡하네요. 저도 미련이.. "


def test_v11_story_passes_when_only_the_closing_matches():
    earlier, mine = LEAD_A + CLOSE, LEAD_B + CLOSE
    # 조각 맞추기는 끝 문장이 길게 같으면 글 전체가 60%를 넘어 걸린다
    assert not _check(_run(mine, story=False, previous=[earlier], keys=None), "V11").passed
    v11 = _check(_run(mine, previous=[earlier], keys=None), "V11")
    assert v11.passed and "끝 문장만 닮은 글" in v11.message, v11.message


def test_v11_story_still_blocks_the_same_comment():
    mine = LEAD_B + CLOSE
    assert not _check(_run(mine, previous=[mine], keys=None), "V11").passed
    near = mine.replace("찡하네요", "찡하네요ㅠ")
    assert not _check(_run(near, previous=[mine], keys=None), "V11").passed


# ---------------------------------------------------------------- 나쁜 꼴 검사(이야기 방식)

STRUCTURE_CODES = ("S2", "S3", "S6", "S7", "S8", "S10", "S11", "S12", "S14", "S15", "S16",
                   "S17", "S18", "S19", "S20", "S21", "S22")


def _issues(text: str, **kw):
    return S.story_issues(text, brand="운명원", disclosure="[광고]", max_total=112,
                          context=kw.pop("context", CONTEXT), **kw)


def test_story_issues_only_use_the_allowed_checks():
    # 조각 맞추기에서 걸리는 꼴(잇는 문장 없음·알고 싶은 것 자리 등)도 이야기 방식에서는 보지 않는다
    text = REACTION + "운명원이 연애사주 잘 본다길래 저도 보러 가려구요"
    assert _issues(text) == []
    issues = _issues(STORY_OK + " 진짜 다들 인연이 있는 듯해요 정말로요")
    assert issues and all(i.split(" ", 1)[0] in ("S1", "S4", "S5", "S9", "S13") for i in issues)
    assert not any(i.startswith(STRUCTURE_CODES) for i in issues)


def test_s1_uses_the_soft_cap():
    assert len(STORY_OK) <= 112 and _issues(STORY_OK) == []
    longer = STORY_OK.replace("맞는 사람이", "처음부터 끝까지 정말 나랑 잘 맞는 사람이")
    assert len(longer) > 112 and _issues(longer)[0].startswith("S1 길이")


def test_s4_blocks_only_near_identical_text():
    copied = "[광고] " + PLANNER_EXAMPLES[2]
    assert any(i.startswith("S4 똑같은 글") for i in _issues(copied, context=""))
    assert any(i.startswith("S4 똑같은 글") for i in _issues(STORY_OK, shown=[STORY_OK]))
    assert any(i.startswith("S4 똑같은 글") for i in _issues(STORY_OK, earlier=[STORY_OK]))
    # 흐름·낱말이 비슷한 글은 괜찮다(대표 기준 「비슷한 건 괜찮다」)
    similar = ("[광고] 연락 횟수로 다퉜다는 말에 한참 머물렀어요. 저도 서운한 걸 쌓아 두는 편이라 "
               "다 때가 있나 봐요. 운명원이 연애사주 잘 봐준다던데 지금 사람이랑 맞는지 보러 가 "
               "볼까 해요")
    assert not any(i.startswith("S4") for i in _issues(similar, shown=[STORY_OK]))


def test_s4_catches_a_character_identical_closing_only():
    other = ("[광고] 기대치 차이라는 말에 한참 머물렀어요. 저도 서운한 걸 쌓아 두는 편이라 다 때가 "
             "있나 봐요. 운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈지 보러 가려구요")
    issues = _issues(other, shown=[STORY_OK])
    assert any(i.startswith("S4 똑같은 끝 문장") for i in issues), issues
    # 띄어쓰기·문장부호만 다른 것도 같은 문장
    spaced = other.replace("오래 갈지", "오래갈지") + "."
    assert any(i.startswith("S4 똑같은 끝 문장") for i in _issues(spaced, shown=[STORY_OK]))
    # 알고 싶은 것이 다르면 괜찮다
    changed = other.replace("오래 갈지", "결혼까지 갈지")
    assert not any(i.startswith("S4") for i in _issues(changed, shown=[STORY_OK]))


def test_s5_and_s9_still_apply():
    ctx = "3년 사귄 남자친구와 헤어졌다는 사연"
    text = ("[광고] 3년 사귄 사람이랑 헤어졌어요ㅠ 저도 미련이 오래 가는 편이라 다 때가 있나 봐요. "
            "운명원이 연애사주 잘 본다던데 새 인연은 언제 오는지 보러 가려구요")
    assert any(i.startswith("S5") for i in _issues(text, context=ctx))
    text9 = ("[광고] 그때그때 말하는 거예요가 답인가 봐요. 저도 서운한 걸 잘 말 못 하는 편이라 "
             "궁합 문제 같아요. 운명원이 연애사주 잘 본다던데 지금 사람이랑 맞는지 보러 가려구요")
    assert any(i.startswith("S9") for i in _issues(text9))


# ---------------------------------------------------------------- 프롬프트

ANALYSIS = {"topic": "장거리 연애 연락 문제", "concern": "연락 때문에 맨날 싸우는데 괜찮을까",
            "tone": "진지한 사연 읽기", "viewer_needs": "다툼 줄이기"}


def _user(**kw):
    base = dict(analysis=ANALYSIS, title="장거리 연애 1년차", quote="하루에 한 번 연락",
                source="transcript", key_phrases=KEYS, mark_len=5, max_body=115)
    base.update(kw)
    return SP.story_user(**base)


def _system():
    return SP.story_system(brand="운명원", disclosure="[광고]", facts=FACTS,
                           sample=ASSIGNMENT_SAMPLE)


def test_story_system_has_the_story_shape_and_the_rules():
    system = _system()
    for word in ("기:", "승:", "전:", "결:", "여운", "한 사람의 목소리", "첫 문장에 쓰지 않는다",
                 "'ㅋㅋ'를 쓰지 않는다", "베끼지 않는다", "120자보다 길다",
                 "같은 갈래다", "이 영상의 문제에서 나온", "다른 시청자의 댓글"):
        assert word in system, word
    for example in PLANNER_EXAMPLES:
        assert example in system
    assert ASSIGNMENT_SAMPLE in system
    # 조각 맞추기의 배정·본보기 10개는 없다
    assert "다섯 조각" not in system and P.BRAND_MODELS[0] not in system


def test_story_system_shows_persona_examples_and_lets_the_ai_choose():
    system = _system()
    assert all(f"'{p}'" in system for p in S.PERSONA_EXAMPLES)
    assert "네가 영상을 보고 정한다" in system and "빼도 되고" in system
    assert "연애가 늘 어려운 1인" in system  # 맞는 처지가 없을 때의 두루 쓰는 말


def test_story_user_has_no_writer_and_no_piece_assignment():
    user = _user()
    assert "[글쓴이]" not in user
    assert "[짚을 장면] '하루에 한 번 연락'" in user
    for banned in ("이번 초안의 운명원 대목", "잇는 한 문장", "이번 끝말", "말투 유형", "까닭"):
        assert banned not in user, banned


@pytest.mark.parametrize("source, said", [
    ("comment", "다른 시청자의 댓글이다. 영상에서 직접 말한 것처럼 쓰지 않는다"),
    ("title", "영상에 없는 장면·대사를 지어내지 않는다"),
    ("description", "영상에 없는 장면·대사를 지어내지 않는다"),
])
def test_story_user_notes_where_the_quote_came_from(source, said):
    assert said in _user(source=source)
    assert "다른 시청자의 댓글이다" not in _user(source="transcript")


def test_thin_video_may_be_short():
    thin = _user(thin=True)
    assert "자막이 없다" in thin and f"{SP.THIN_MIN}자만 넘으면" in thin and "짧게" in thin
    assert "자막이 없다" not in _user()


def test_story_user_tells_the_remaining_characters_with_and_without_the_label():
    on = _user(mark_len=5, max_body=115)
    off = _user(mark_len=0, max_body=120)
    assert "본문 75~95자" in on and "표기 몫 5자" in on and "115자를 넘지" in on
    assert "본문 80~100자" in off and "표기 몫" not in off and "120자를 넘지" in off


def test_story_user_shows_earlier_comments_with_a_soft_rule():
    earlier = [STORY_OK.replace("[광고] ", ""), "다른 영상에 쓴 글 하나"]
    user = _user(shown=earlier)
    assert "[이미 쓴 글 — 똑같이 쓰지 않는다(낱말·흐름이 비슷한 것은 괜찮다)]" in user
    assert all(f"- {t}" in user for t in earlier)


def test_story_user_drop_lines_and_retry():
    assert SP.DROP_LINES[1] in _user(drop=1) and SP.DROP_LINES[2] in _user(drop=2)
    assert SP.DROP_LINES[1] not in _user()
    retry = _user(failure_lines=["V1 길이"], previous_body="앞 글")
    assert "[다시 쓰기]" in retry and "앞의 본문(3자): 앞 글" in retry
    assert "같은 글쓴이" not in retry and "기승전결은 그대로" in retry


# ---------------------------------------------------------------- 맥락 일치 검증

GOOD_VERDICT = {"same_topic": True, "comment_topic": "연락 문제", "one_voice": True,
                "drift": "", "natural_ad": True, "ok": True, "problems": []}


def test_story_review_asks_for_the_four_context_judgments():
    system = rv.review_system(brand="운명원", story=True)
    for word in ("same_topic", "comment_topic", "one_voice", "drift", "natural_ad",
                 "뜻", "바꿔치기", "다른 시청자 댓글의 사연", "억지로", "문제가 아닌 것",
                 "막연한 내 처지", "인연·때·궁합", "분명한 문제만", "기본 꼴이다",
                 "같은 갈래다"):
        assert word in system, word
    assert system != rv.review_system(brand="운명원")
    assert set(rv.STORY_REVIEW_SCHEMA["required"]) == {
        "same_topic", "comment_topic", "one_voice", "drift", "natural_ad", "ok", "problems"}


def test_story_review_user_gives_topic_source_and_transcript():
    user = rv.review_user(body="본문", title="제목", concern="고민", evidence="말", source="댓글",
                          topic="주제", thin=True, story=True)
    assert "[영상 주제] 주제" in user and "[근거 구절(영상 자료의 댓글에서)] 말" in user
    assert "다른 시청자의 댓글이다" in user and "[자막] 없음" in user
    assert "맥락과 맞는지" in user
    old = rv.review_user(body="본문", topic="주제", source="댓글", evidence="말")
    assert "[영상 주제]" not in old and "일곱 가지 기준" in old


def test_parse_story_passes_a_clean_verdict():
    verdict = rv.parse_story(GOOD_VERDICT)
    ok, problems = verdict
    assert ok and problems == [] and verdict.checks["comment_topic"] == "연락 문제"


@pytest.mark.parametrize("field, value, said", [
    ("same_topic", False, "다른 고민으로 바뀜(댓글은 '연락 문제')"),
    ("one_voice", False, "한 사람의 목소리가 아님"),
    ("natural_ad", False, "억지로 넘어감"),
    ("drift", "저도 이 사람과 궁합이 맞는지", "벗어난 문장: 「저도 이 사람과 궁합이 맞는지」"),
])
def test_parse_story_flags_any_context_problem(field, value, said):
    ok, problems = rv.parse_story({**GOOD_VERDICT, field: value})
    assert not ok and said in problems[0]


def test_drift_comes_first_then_grammar():
    data = {**GOOD_VERDICT, "same_topic": False, "drift": "튄 문장", "ok": False,
            "problems": ["'사셔라가' — 조사"]}
    ok, problems = rv.parse_story(data)
    assert not ok and problems[0].startswith("벗어난 문장") and problems[-1] == "'사셔라가' — 조사"


def test_old_shaped_answer_counts_as_no_context_problem():
    ok, problems = rv.parse_story({"ok": True, "problems": []})
    assert ok and problems == []
    with pytest.raises(ValueError):
        rv.parse_story({"same_topic": True})


def test_story_labels_and_retry_lines():
    assert rv.label(rv.PASSED, story=True) == "맥락 검증 통과 · 영상 주제와 일치"
    assert rv.label(rv.REWRITTEN, story=True) == "맥락 검증 통과 · 한 번 고쳐 씀"
    assert rv.label(rv.FLAGGED, story=True) == "맥락 확인 필요"
    assert rv.label(rv.ERROR, story=True) == "맥락 검증 못 함 — 직접 읽어 주세요"
    assert rv.label(rv.PASSED) == "AI 검수 통과"
    lines = rv.retry_lines(["x"], story=True)
    assert lines[0].startswith("맥락 검증: x") and lines[-1].startswith("길이: 앞의 본문보다 길게")


# ---------------------------------------------------------------- 설정


@pytest.mark.parametrize("raw, want", [
    ("story", "story"), ("pieces", "pieces"), ("PIECES", "pieces"), ("", "story"),
    (None, "story"), ("free", "story"),
])
def test_writer_setting_parses_with_story_as_default(raw, want):
    from app.config import _writer

    assert _writer(raw) == want


def test_writer_field_is_a_choice_of_two():
    from app.user_settings import FIELDS, WRITER_LABELS

    field = FIELDS["comment.writer"]
    assert field.kind == "choice" and field.path == ("comment", "writer")
    assert set(field.choices) == set(S.WRITERS) and WRITER_LABELS == S.WRITER_LABELS
