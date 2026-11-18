"""이야기처럼 쓰기(2026-11-18 대표 결정, `comment.writer: story`).

이 파일이 못 박는 것(대표: 「불필요하게 제한하는 것들은 제거하고 아래만」):
- 프롬프트는 대표가 정한 것만 — 설정 글자 수(표기 빼고) · 자막(없으면 제목·설명)과 인기 댓글을 읽고
  연애 고민을 먼저 정리 · 시청자 입장의 기승전결 · 운명원 사주를 보고 싶어지게 · 영상 속 장면·말
  하나 이상 · 써 본 척하는 후기 금지 · 장면과 운명원의 맥락. 본보기는 과제 예시 하나.
- 뺀 것이 남아 있지 않다 — 말투 유형 배정 · 운명원 조각 · 잇는 문장 · 인연·궁합·타이밍 강제 · 처지
  문장 강제 · 끝말 검사 · 과한 스타일 검사(S5·S9·S13) · 운명원 문장이 같다고 다시 쓰게 하는 것.
- AI가 자막·제목·설명·인기 댓글 원문을 직접 읽는다(`material`).
- V14(이야기 방식)는 넷만 본다 — 이름 · 연애 사주(사주) · 들은 평판 · 보러 갈 뜻. 운명원은 첫
  문장에 나오지 않는다. 지어낸 평판은 걸린다.
- V11(이야기 방식): 끝 문장(운명원 문장)만 닮고 앞부분이 다르면 통과. 통째로 같으면 걸린다.
- 다시 쓰게만 하는 검사는 S1(길이)·S4(앞 글과 거의 똑같은 글)만.
- 맥락 일치 검증: same_topic·comment_topic·one_voice·drift·natural_ad + ok·problems.
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

def _run(text: str, *, story: bool = True, context: str = CONTEXT, keys=KEYS, previous=()):
    return validate(
        text, context_text=context, rules=RULES, brand_facts=FACTS,
        previous_texts=list(previous), key_phrases=keys, story=story,
    )


def _check(result, code: str):
    return next(c for c in result.checks if c.code == code)


# ---------------------------------------------------------------- 뺀 것

def test_removed_helpers_are_gone():
    # 처지 예·좋은 예·나쁜 예·끝 문장 비교는 없다(대표: 불필요한 제한 제거)
    for gone in ("PERSONA_EXAMPLES", "GOOD_EXAMPLES", "BAD_EXAMPLES", "EXAMPLES", "same_closing",
                 "PERSONAS", "GROUPS", "pick_persona"):
        assert not hasattr(S, gone), gone
    for gone in ("SOURCE_NOTES", "THIN_MIN", "CLOSING_CHARS"):
        assert not hasattr(SP, gone), gone


def test_assignment_sample_passes_story_v14():
    result = _run("[광고] " + ASSIGNMENT_SAMPLE, context=ASSIGNMENT_SAMPLE[:20], keys=None)
    assert _check(result, "V14").passed, _check(result, "V14").message
    assert story_pieces("[광고] " + ASSIGNMENT_SAMPLE, "운명원", "[광고]") == []


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


def test_story_v7_accepts_another_real_line_from_the_material():
    # 대표: 「영상 속 구체적인 장면이나 말을 하나 이상」 — AI가 자료에서 고른 다른 말이어도 된다
    ctx = CONTEXT + "\n서운한 건 그때그때 말하는 게 좋다는 조언"
    text = ("[광고] 서운한 건 그때그때 말하는 게 좋다는 조언이 와닿네요. 저도 쌓아 두는 편이라.. "
            "운명원이 연애사주 잘 본다던데 지금 사람이랑 맞는지 보러 가려구요")
    assert _check(_run(text, context=ctx), "V7").passed
    assert not _check(_run(text, context=ctx, story=False), "V7").passed  # 조각 맞추기는 그대로


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
    return S.story_issues(text, brand="운명원", disclosure="[광고]", max_total=120,
                          context=kw.pop("context", CONTEXT), **kw)


def test_story_issues_only_use_s1_and_s4():
    # 조각 맞추기에서 걸리는 꼴도, 예전 이야기 방식의 S5·S9·S13도 보지 않는다(대표)
    text = REACTION + "운명원이 연애사주 잘 본다길래 저도 보러 가려구요"
    assert _issues(text) == []
    issues = _issues(STORY_OK + " 진짜 다들 인연이 있는 듯해요 정말로요 정말 정말로요")
    assert issues and all(i.split(" ", 1)[0] in ("S1", "S4") for i in issues)
    assert not any(i.startswith(STRUCTURE_CODES) for i in issues)
    ctx = "3년 사귄 남자친구와 헤어졌다는 사연 #이별"
    number = ("[광고] 3년 사귄 사람이랑 헤어졌다니ㅠ 저도 미련이 오래 가는 편이라.. "
              "운명원이 연애사주 잘 본다던데 새 인연은 언제 오는지 보러 가려구요")
    ended = ("[광고] 그때그때 말하는 거예요가 답인가 봐요. 저도 서운한 걸 잘 말 못 하는 편이라 "
             "운명원이 연애사주 잘 본다던데 지금 사람이랑 맞는지 보러 가려구요")
    assert _issues(number, context=ctx) == [] and _issues(ended) == []


def test_s1_uses_the_given_cap_without_the_label():
    assert _issues(STORY_OK) == []
    body = STORY_OK.removeprefix("[광고] ")
    assert S.story_issues(STORY_OK, brand="운명원", disclosure="[광고]",
                          max_total=len(body)) == []  # 표기는 세지 않는다
    longer = STORY_OK.replace("맞는 사람이", "처음부터 끝까지 정말 나랑 잘 맞는 사람이 " * 2)
    assert len(longer.removeprefix("[광고] ")) > 120 and _issues(longer)[0].startswith("S1 길이")


def test_s4_blocks_only_near_identical_text():
    assert any(i.startswith("S4 똑같은 글") for i in _issues(STORY_OK, shown=[STORY_OK]))
    assert any(i.startswith("S4 똑같은 글") for i in _issues(STORY_OK, earlier=[STORY_OK]))
    # 흐름·낱말이 비슷한 글은 괜찮다(대표 기준 「비슷한 건 괜찮다」)
    similar = ("[광고] 연락 횟수로 다퉜다는 말에 한참 머물렀어요. 저도 서운한 걸 쌓아 두는 편이라 "
               "다 때가 있나 봐요. 운명원이 연애사주 잘 봐준다던데 지금 사람이랑 맞는지 보러 가 "
               "볼까 해요")
    assert not any(i.startswith("S4") for i in _issues(similar, shown=[STORY_OK]))


def test_same_brand_sentence_alone_is_not_rewritten():
    # 대표: 「브랜드 문장이 조금 비슷하다는 이유만으로 다시 쓰게 하지 않는다」
    other = ("[광고] 기대치 차이라는 말에 한참 머물렀어요. 저도 서운한 걸 쌓아 두는 편이라 다 때가 "
             "있나 봐요. 운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈지 보러 가려구요")
    assert _issues(other, shown=[STORY_OK]) == []


# ---------------------------------------------------------------- 프롬프트

ANALYSIS = {"topic": "장거리 연애 연락 문제", "concern": "연락 때문에 맨날 싸우는데 괜찮을까",
            "tone": "진지한 사연 읽기", "viewer_needs": "다툼 줄이기"}


def _user(**kw):
    base = dict(analysis=ANALYSIS, title="장거리 연애 1년차", quote="하루에 한 번 연락",
                source="transcript", key_phrases=KEYS, mark_len=0, max_body=120)
    base.update(kw)
    return SP.story_user(**base)


def _system():
    return SP.story_system(brand="운명원", disclosure="[광고]", facts=FACTS,
                           sample=ASSIGNMENT_SAMPLE)


def test_story_system_says_only_what_the_boss_asked():
    system = _system()
    for word in ("자막, 자막이 없으면 제목·설명, 그리고 인기 댓글", "연애 고민을 먼저 한 줄로 정리",
                 "시청자 입장에서 기승전결로", "구체적인 장면이나 말을 하나 이상",
                 "맥락이 이어지게", "연애 사주를 보고 싶어지게", "지어낸 후기는 쓰지 않는다",
                 "없는 장면이나 발언을 만들어 내지 않는다", "억지로 붙이지 않는다",
                 "'요새'", "'친구한테 듣기로'", "베끼지 않는다", "\"concern\""):
        assert word in system, word
    assert ASSIGNMENT_SAMPLE in system  # 가장 좋은 본보기는 과제 예시 하나


def test_removed_rules_are_not_in_the_prompt():
    system, user = _system(), _user()
    for gone in ("말투 유형", "다섯 조각", "잇는 한 문장", "이번 끝말", "[글쓴이]", "썸만 타다",
                 "인연·때·궁합 쪽으로", "기:", "여운", "좋은 댓글", "나쁜 댓글", "S5", "S9",
                 P.BRAND_MODELS[0]):
        assert gone not in system and gone not in user, gone


def test_story_schema_asks_for_the_concern_first():
    schema = SP.story_schema()
    assert list(schema["properties"])[0] == "concern"
    assert schema["required"][0] == "concern" and "body" in schema["required"]


def test_story_user_shows_the_raw_material():
    material = SP.material(title="장거리 연애 1년차", description="연락 문제 사연",
                           transcript="하루에 한 번 연락이면 될까요 " * 300,
                           comments=["저도 그래요ㅠ", "", "연락이 전부는 아니죠"])
    assert "- 자막: 하루에 한 번" in material and len(material) < SP.MATERIAL_TRANSCRIPT + 600
    assert "· 저도 그래요ㅠ" in material and "· 연락이 전부는 아니죠" in material
    user = _user(material_text=material)
    assert user.startswith("[영상 자료]\n- 제목: 장거리 연애 1년차")
    assert "[짚을 만한 말] '하루에 한 번 연락'" in user and "하나 이상 넣는다" in user
    none = SP.material(title="제목만", description="", transcript="", comments=[])
    assert "자막: 없음" in none


def test_thin_video_reacts_to_title_or_comments():
    thin = _user(thin=True)
    assert "자막이 없다" in thin and "댓글이라고 밝힌다" in thin
    assert "자막이 없다" not in _user()


def test_story_user_counts_without_the_label():
    user = _user(mark_len=0, max_body=120, min_body=40)
    assert "본문 40~120자(표기는 세지 않는다)" in user and "75~95자쯤" in user
    assert "표기 몫" not in user
    assert "표기 몫 5자" in _user(mark_len=5, max_body=115)  # 예전 셈을 넘기면 그대로 알린다


def test_story_user_shows_earlier_comments():
    earlier = [STORY_OK.replace("[광고] ", ""), "다른 영상에 쓴 글 하나"]
    user = _user(shown=earlier)
    assert "[이미 쓴 글 — 똑같이 쓰지 않는다]" in user
    assert all(f"- {t}" in user for t in earlier)


def test_story_user_drop_lines_and_retry():
    assert SP.DROP_LINES[1] in _user(drop=1) and SP.DROP_LINES[2] in _user(drop=2)
    assert SP.DROP_LINES[1] not in _user()
    retry = _user(failure_lines=["V1 길이"], previous_body="앞 글")
    assert "[다시 쓰기]" in retry and "앞의 본문(3자): 앞 글" in retry
    assert "걸린 항목을 고쳐 새 본문을 써라" in retry


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
