"""이야기처럼 쓰기(2026-11-18 대표 결정, `comment.writer: story`).

이 파일이 못 박는 것(대표: 「불필요하게 제한하는 것들은 제거하고 아래만」):
- 프롬프트는 대표가 정한 것만 — 설정 글자 수(표기 빼고) · 자막(없으면 제목·설명)과 인기 댓글을 읽고
  연애 고민을 먼저 정리 · 시청자 입장의 기승전결 · 운명원 사주를 보고 싶어지게 · 영상 속 장면·말
  하나 이상 · 써 본 척하는 후기 금지 · 장면과 운명원의 맥락. 본보기는 과제 예시 하나.
- 뺀 것이 남아 있지 않다 — 말투 유형 배정 · 운명원 조각 · 잇는 문장 · 인연·궁합·타이밍 강제 · 처지
  문장 강제 · 끝말 검사 · 과한 스타일 검사(S5·S9·S13) · 운명원 문장이 같다고 다시 쓰게 하는 것.
- AI가 자막·제목·설명·인기 댓글 원문을 직접 읽는다(`material`).
- 코드가 보는 것은 대표 표대로(2026-11-18) — 글자 수 · 영상 근거 · 운명원 언급 · 허위 후기(와
  원문 금지·표기). V12·V13은 「보지 않음」, V14는 지어낸 평판·사례만 본다(운명원 자리·조각은
  AI가 쓰고 AI 검토가 본다).
- V11(이야기 방식): 끝 문장(운명원 문장)만 닮고 앞부분이 다르면 통과. 통째로 같으면 걸린다.
- 다시 쓰게만 하는 검사는 S4(앞 글과 거의 똑같은 글)만. 길이는 V1이 본다.
- AI 판단(대표 표): 영상 맥락과 일치(same_topic·drift) · 기승전결이 자연스러운가(flow) · 같은
  사람이 쓴 글처럼(one_voice) · 운명원 언급이 뜬금없는가(natural_ad) + ok·problems.
"""

from __future__ import annotations

import pytest

from app.analysis import review as rv
from app.analysis import story as S
from app.analysis.validator import (
    ASSIGNMENT_SAMPLE,
    ValidatorRules,
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


@pytest.mark.parametrize("text", [
    # 운명원이 첫 문장에 — 뜬금없는지는 AI 검토(natural_ad)가 본다
    "[광고] 운명원이 연애사주 잘 본다던데 하루에 한 번 연락으로 싸웠다니 저도 궁합이 맞는지 "
    "보러 가려구요",
    # 보러 갈 뜻 · 연애 사주 · 평판 조각이 없음 — 쓰는 것은 AI 몫
    REACTION + "저도 자주 부딪히는 편이라 맞는 사람이 따로 있나 싶어요. 운명원이 연애사주 잘 "
    "본다길래 지금 사람이랑 오래 갈지 궁금하네요",
    REACTION + "저도 자주 부딪히는 편이라 맞는 사람이 따로 있나 싶어요. 운명원에서 연애사주로 "
    "지금 사람이랑 오래 갈지 보러 가려구요",
])
def test_story_code_does_not_judge_brand_position_or_pieces(text):
    # 대표 표(2026-11-18): 코드는 운명원 「언급 여부」만 — 자리·조각은 보지 않는다
    check = _check(_run(text), "V14")
    assert check.passed and check.name == "운명원 대목에 지어낸 평판·사례 없음", check.message
    assert _check(_run(text), "V5").passed


def test_story_code_checks_only_the_table():
    # V12(문자 종류)·V13(길게 베낌)은 이야기 방식에서 보지 않는다 — 조각 맞추기는 그대로
    copied = ("[광고] 하루에 한 번 연락하는 커플이 서로 연락 기대치가 달라 싸웠다니 공감돼요. "
              "운명원이 연애사주 잘 본다던데 보러 가려구요")
    odd = REACTION + "저도 마음이揪하네요. 운명원이 연애사주 잘 본다던데 보러 가려구요"
    for text, code in ((copied, "V13"), (odd, "V12")):
        story = _check(_run(text), code)
        assert story.passed and "보지 않음" in story.message
        assert not _check(_run(text, story=False), code).passed
    # 표에 있는 것은 그대로 본다: 글자 수 · 영상 근거 · 운명원 언급 · 허위 후기
    assert not _check(_run("[광고] 운명원 짧아요"), "V1").passed
    assert not _check(_run(REACTION.replace("운명원", "") + "연애 사주 보러 가려구요"), "V5").passed
    review = REACTION + "운명원에서 연애사주 받아 봤는데 진짜 잘 맞았어요"
    assert not _run(review).passed


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


def test_story_review_asks_for_the_four_ai_judgments():
    # 대표 표의 AI 판단 넷: 맥락 일치 · 기승전결 · 같은 사람 · 운명원이 뜬금없는지
    system = rv.story_review_system(brand="운명원")
    for key in ("same_topic", "flow", "one_voice", "natural_ad"):
        assert key in system and key in rv.STORY_REVIEW_SCHEMA["required"], key
    assert "가운데의 생각이 앞에서 나온 상황·감정에서 자연스럽게 이어지는가" in system
    verdict = rv.parse_story({
        "same_topic": True, "comment_topic": "연락", "one_voice": True, "flow": False,
        "drift": "", "natural_ad": True, "ok": True, "problems": [],
    })
    ok, problems = verdict
    assert not ok and verdict.checks["flow"] is False
    assert any("기승전결" in p for p in problems)
    # flow가 빠진 답은 문제 없음으로 본다(모양이 틀린 답으로 글을 바꾸지 않는다)
    assert rv.parse_story({"ok": True, "problems": []}).checks["flow"] is True


def test_story_v7_accepts_another_real_line_from_the_material():
    # 대표: 「영상 속 구체적인 장면이나 말을 하나 이상」 — AI가 자료에서 고른 다른 말이어도 된다
    ctx = CONTEXT + "\n서운한 건 그때그때 말하는 게 좋다는 조언"
    text = ("[광고] 서운한 건 그때그때 말하는 게 좋다는 조언이 와닿네요. 저도 쌓아 두는 편이라.. "
            "운명원이 연애사주 잘 본다던데 지금 사람이랑 맞는지 보러 가려구요")
    assert _check(_run(text, context=ctx), "V7").passed
    assert not _check(_run(text, context=ctx, story=False), "V7").passed  # 조각 맞추기는 그대로


def test_story_skips_v7_so_own_words_pass():
    # 2026-11-18: 영상 말을 글자 그대로 넣게 하면 따옴표 자국이 남고, 제 말로 풀어 쓴 글이 걸렸다
    # — 이야기 방식은 V7을 보지 않는다(영상 근거는 V6, 장면을 맞게 짚었는지는 AI 검수)
    text = ("[광고] 사진 한 장만 콕 집어 고맙다고 하면 다음에도 찍어 주고 싶겠네요. 저도 서운한 "
            "것부터 말하는 편이라 운명원이 연애 사주 잘 본다던데 우리 사이 한번 보고 싶어요")
    v7 = _check(_run(text), "V7")
    assert v7.passed and "보지 않음" in v7.message
    assert not _check(_run(text, story=False), "V7").passed


def test_story_review_sees_the_same_material_and_no_set_ending():
    material = SP.material(title="제목", description="설명", transcript="자막 속 다른 장면",
                           comments=["인기 댓글"])
    user = rv.review_user(body="본문", title="제목", story=True, material=material)
    assert "[영상 자료 — 댓글을 쓴 AI가 본 것과 같다]" in user and "자막: 자막 속 다른 장면" in user
    assert "자막 속 다른 장면" not in rv.review_user(body="본문", title="제목", material=material)
    system = rv.story_review_system(brand="운명원")
    assert "기본 꼴" not in system  # 끝말 한 가지를 정답처럼 굳히던 문장
    assert "제목·자막·설명·고민 한 줄·근거 구절" in system


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


def test_story_issues_only_use_s4():
    # 조각 맞추기에서 걸리는 꼴도, 예전 이야기 방식의 S5·S9·S13도 보지 않는다(대표)
    text = REACTION + "운명원이 연애사주 잘 본다길래 저도 보러 가려구요"
    assert _issues(text) == []
    issues = _issues(STORY_OK + " 진짜 다들 인연이 있는 듯해요 정말로요 정말 정말로요",
                     shown=[STORY_OK + " 진짜 다들 인연이 있는 듯해요 정말로요 정말 정말로요"])
    assert issues and all(i.split(" ", 1)[0] == "S4" for i in issues)
    assert not any(i.startswith(STRUCTURE_CODES) for i in issues)
    ctx = "3년 사귄 남자친구와 헤어졌다는 사연 #이별"
    number = ("[광고] 3년 사귄 사람이랑 헤어졌다니ㅠ 저도 미련이 오래 가는 편이라.. "
              "운명원이 연애사주 잘 본다던데 새 인연은 언제 오는지 보러 가려구요")
    ended = ("[광고] 그때그때 말하는 거예요가 답인가 봐요. 저도 서운한 걸 잘 말 못 하는 편이라 "
             "운명원이 연애사주 잘 본다던데 지금 사람이랑 맞는지 보러 가려구요")
    assert _issues(number, context=ctx) == [] and _issues(ended) == []


def test_length_is_left_to_v1():
    # S1은 V1과 같은 셈(표기 빼고 120자)이 되어 뺐다 — 길이는 규칙 검사 V1만 본다
    longer = STORY_OK.replace("맞는 사람이", "처음부터 끝까지 정말 나랑 잘 맞는 사람이 " * 2)
    assert len(longer.removeprefix("[광고] ")) > 120
    assert _issues(longer) == []
    assert not _check(_run(longer), "V1").passed


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


def test_story_system_is_the_prompt_the_boss_gave():
    # 2026-11-18 대표 「이렇게 해보자」: 붙여 준 시스템 프롬프트 그대로
    system = _system()
    for word in ("## 목표", "## 작성 방법", "## 가장 중요한 원칙", "## 참고 예시",
                 "## 작성 후 검토", "## 출력",
                 "핵심 연애 고민을 한 줄로 정리", "구체적인 장면이나 말을 하나 이상",
                 "인기 댓글의 사연은 영상에서 직접 말한 내용처럼 표현하지 않는다",
                 "기승전결은 네 개의 문장이 아니라 생각의 흐름이다",
                 "말투·관점·문장 수·잇는 말·끝말은 자유다", "지어낸 후기는 절대 작성하지 않는다",
                 "앞에서 등장하지 않은 인물이나 관계를 끝에서 갑자기 언급하지 않는다",
                 "억지 연결 문장은 작성하지 않는다",
                 # 대표 확인 뒤 고친 줄(2026-11-18)
                 "들은 평판으로 꺼내고", "요새·요즘·친구한테 듣기로 같은 말을",
                 "보고 싶은 마음으로 이어지게 맺는다",
                 "보고 싶어지도록", "따옴표로 옮기지 않고 내 말로 풀어 쓴다",
                 "사실상 동일한 경우만 피한다", "그대로 복사하지 않는다",
                 "운명원이 뜬금없이 등장하지 않는가", "댓글 전체를 처음부터 다시 작성한다",
                 # 대표 지시서(2026-11-18): 생각이 발전하는 과정
                 "생각이 발전하는 한 줄기 이야기다", "그 반응에서 자라난 생각이나 궁금증",
                 "답을 문장이나 따로 된 칸으로 내지 않는다",
                 "왜 그 궁금증에서 운명원 연애 사주가 떠올랐는가",
                 "설명할 수 없다면, 그 댓글은 처음부터 다시 쓴다",
                 "다른 연애 영상 댓글에 그대로 붙여도 말이 되는 막연한 것",
                 # 2026-11-18 대표 지시서 3: 가상 관점·고민은 자유, 전해 들은 경위도 된다
                 "가상의 연애 고민·처지를 정해 써도 된다", "## 피해야 할 흐름",
                 "이 문장이나 구성을 쓰라는 뜻이 아니다",
                 "중간 문장 조각은 따로 만들지 않는다", "\"concern\"", "연애 사주를 잘 봐주는"):
        assert word in system, word
    assert ASSIGNMENT_SAMPLE in system  # 참고 예시는 과제 예시 하나


def test_removed_rules_are_not_in_the_prompt():
    system, user = _system(), _user()
    for gone in ("이번 말투", "다섯 조각", "잇는 한 문장", "이번 끝말", "[글쓴이]", "썸만 타다",
                 "인연·때·궁합 쪽으로", "기:", "여운", "좋은 댓글", "나쁜 댓글", "S5", "S9",
                 P.BRAND_MODELS[0],
                 # 조각 칸(2026-11-18 대표: 그것도 새 조각 강제였다)
                 "scene", "situation", "wonder", "filler", "네 칸",
                 # 대표가 고친 글·추임새 목록·글자 수 목표·핵심 말 강제
                 "요즘 저한테 잘해주는 사람이 있는데", "'요새'", "75~95자쯤", "핵심 말",
                 # 「연애 사주로 유명한 운명원 … 궁금하네요」를 만든 줄
                 "관심을 갖도록", "관심으로 연결", "불필요한 추임새", "인연·궁합·타이밍",
                 "곳으로 소개한다",
                 # 2026-11-18 대표 지시서 2·3: 가상의 처지를 막던 말 · 추천 경위 금지
                 "겪지 않은 구체적인 일", "추천해 줬다는 경위를 지어내지",
                 "지어낸 추천 경위",
                 # 끝말 예시 하나 — 모든 댓글이 그 말로 끝났다(2026-11-18)
                 "'연애 사주 잘 본다던데'처럼"):
        assert gone not in system and gone not in user, gone
    assert not hasattr(SP, "BOSS_EXAMPLE") and not hasattr(SP, "PLAN_FIELDS")
    assert not hasattr(SP, "STORY_TARGET")


def test_story_schema_asks_for_the_concern_first():
    schema = SP.story_schema()
    assert list(schema["properties"])[0] == "concern"
    assert schema["required"][0] == "concern" and "body" in schema["required"]
    # 조각 칸은 없다 — 고민 · 본문 · 근거 · 말투 이름만
    assert set(schema["properties"]) == {"concern", "body", "used_quote", "tone_label"}


def test_quotes_are_dropped_from_the_body():
    # 대표: 시청자는 영상 속 말을 따옴표로 옮겨 적지 않는다
    body = "‘다시 얘기할 날만 정하자’는 말이 와닿네요. “그 사람” 마음 'ㅋㅋ'"
    assert SP.drop_quotes(body) == "다시 얘기할 날만 정하자는 말이 와닿네요. 그 사람 마음 ㅋㅋ"


def test_story_user_shows_the_raw_material():
    material = SP.material(title="장거리 연애 1년차", description="연락 문제 사연",
                           transcript="하루에 한 번 연락이면 될까요 " * 300,
                           comments=["저도 그래요ㅠ", "", "연락이 전부는 아니죠"])
    assert "자막: 하루에 한 번" in material and len(material) < SP.MATERIAL_TRANSCRIPT + 600
    assert material.index("자막:") < material.index("설명:") < material.index("인기 댓글:")
    assert "· 저도 그래요ㅠ" in material and "· 연락이 전부는 아니죠" in material
    user = _user(material_text=material)
    assert user.startswith("[영상 자료]\n제목: 장거리 연애 1년차")
    assert "[실제 영상 근거 구절]\n하루에 한 번 연락 (자막)" in user
    assert "영상에서 실제로 확인되는 내용을 하나 이상 언급하고," in user
    none = SP.material(title="제목만", description="", transcript="", comments=[])
    assert "자막: 없음" in none


def test_story_user_gives_only_the_setting_length():
    user = _user(mark_len=0, max_body=120, min_body=40)
    assert "[작성 조건]\n본문 글자 수: 40~120자" in user
    assert "광고 표기는 프로그램에서 별도로 추가한다." in user


def test_story_user_shows_earlier_comments():
    earlier = [STORY_OK.replace("[광고] ", ""), "다른 영상에 쓴 글 하나"]
    user = _user(shown=earlier)
    assert "[이미 쓴 댓글 — 전체가 사실상 같은 글만 피한다]" in user
    assert all(f"- {t}" in user for t in earlier)


def test_story_user_drop_lines_and_retry():
    assert SP.DROP_LINES[1] in _user(drop=1) and SP.DROP_LINES[2] in _user(drop=2)
    assert SP.DROP_LINES[1] not in _user()
    assert all("문장" not in line or "짧" in line for line in SP.DROP_LINES)  # 길이만 알린다
    retry = _user(failure_lines=["V1 길이"], previous_body="앞 글")
    assert "[다시 쓰기]" in retry and "앞의 본문(3자): 앞 글" in retry
    assert "걸린 항목을 고쳐 댓글 전체를 다시 쓴다" in retry


# ---------------------------------------------------------------- 맥락 일치 검증

GOOD_VERDICT = {"same_topic": True, "comment_topic": "연락 문제", "one_voice": True,
                "flow": True, "drift": "", "natural_ad": True, "ok": True, "problems": []}


def test_story_review_asks_for_the_four_context_judgments():
    system = rv.review_system(brand="운명원", story=True)
    for word in ("same_topic", "comment_topic", "one_voice", "drift", "natural_ad",
                 "뜻", "바꿔치기", "다른 시청자 댓글의 사연", "억지로", "문제가 아닌 것",
                 "가상의 내 연애 고민·처지", "인연·때·궁합", "분명한 문제만",
                 "친구가 얘기해 줬는데", "주변에서 추천하길래", "뜻으로 자연스럽게 이어지면 참",
                 "분명히 아무 연애 영상에나 붙는 궁금증",
                 "specific_link", "link_reason", "break_at", "걸려야 하는 예",
                 "같은 갈래다"):
        assert word in system, word
    # 2026-11-18 대표 지시서 2·3: 가상의 경험·전해 들은 추천 경위는 걸리지 않는다
    for gone in ("겪은 일처럼 쓴 구체적인", "지어낸 추천 경위", "구체적인 경험만 문제다"):
        assert gone not in system, gone
    assert system != rv.review_system(brand="운명원")
    assert set(rv.STORY_REVIEW_SCHEMA["required"]) == {
        "same_topic", "comment_topic", "one_voice", "flow", "specific_link", "link_reason",
        "break_at", "drift", "natural_ad", "ok", "problems"}


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


def test_story_v5_needs_love_saju_with_the_brand():
    # 2026-11-18 대표: 운명원 연애 사주 언급은 과제 필수
    ok = ("[광고] 다음 약속 날짜까지 잡아 주면 설레는데 헷갈리네요. 저도 썸에서 혼자 의미 부여하는 "
          "편이라 운명원이 연애사주 잘 본다던데 한번 보고 싶어요")
    assert _check(_run(ok), "V5").passed
    no_love = ok.replace("연애사주", "사주")
    v5 = _check(_run(no_love), "V5")
    assert not v5.passed and "연애 사주" in v5.message
    assert _check(_run(no_love, story=False), "V5").passed  # 조각 맞추기는 그대로


def test_story_shorten_line_only_when_too_long():
    long_retry = _user(failure_lines=["V1 길이: 140자로 깁니다 — 20자 이상 줄이세요"],
                       previous_body="앞 글")
    line = SP.SHORTEN_LINE.format(brand="운명원")
    assert line in long_retry and "거기서 자라난 생각" in line and "내 처지" not in line
    assert line not in _user(failure_lines=["S4 똑같은 글"], previous_body="앞 글")
    assert line not in _user()


def test_story_user_passes_summary_and_real_quote_together():
    # 2026-11-18 대표 5단계: 요약 + 실제 자막 구절 + 필수 조건
    summary = {"topic": "시간 갖자는 말", "concern": "뭐라고 답해야 덜 불안할까"}
    user = SP.story_user(analysis=summary,
                         title="t", quote="다시 얘기할 날만 정하자", source="transcript",
                         material_text="제목: t\n자막: 다시 얘기할 날만 정하자")
    order = [user.index(k) for k in ("[영상 자료]", "[영상 요약]", "[실제 영상 근거 구절]")]
    assert order == sorted(order)
    assert "핵심 연애 고민: 뭐라고 답해야 덜 불안할까" in user
    assert "ㅋㅋ·ㅠㅠ·^^" in _system()


def test_story_review_flags_a_vague_ending_and_missing_link():
    # 2026-11-18 대표 지시서: 끝의 궁금증이 이 영상에서 나왔나 · 운명원 직전 생각을 설명할 수 있나
    base = {"same_topic": True, "comment_topic": "시간 갖자는 말", "one_voice": True,
            "flow": True, "specific_link": True, "link_reason": "날짜를 정해도 맞는 사이인지 궁금",
            "break_at": "", "drift": "", "natural_ad": True, "ok": True, "problems": []}
    good = rv.parse_story(base)
    assert good[0] and good.checks["link_reason"].startswith("날짜를")
    vague = rv.parse_story({**base, "specific_link": False, "link_reason": "",
                            "break_at": "날짜를 정하자는 얘기 → 연애 흐름이 궁금: 상관없는 궁금증"})
    ok, problems = vague
    assert not ok
    assert problems[0].startswith("끊긴 곳: 날짜를 정하자는 얘기")  # 어디서 끊겼는지 먼저
    assert any("막연함" in p for p in problems)
    assert any("설명할 수 없음" in p for p in problems)
    # 새 칸이 빠진 예전 모양의 답은 걸린 것으로 보지 않는다
    old = rv.parse_story({k: v for k, v in base.items()
                          if k not in ("specific_link", "link_reason", "break_at")})
    assert old[0] and old.checks["link_reason"] is None


def test_story_retry_rewrites_the_whole_comment():
    lines = rv.retry_lines(["끊긴 곳: A → B: 상관없음"], story=True)
    assert any("끊긴 곳: A → B" in line for line in lines)
    assert any("끊긴 곳을 메우는 문장을 더하지 말고" in line and "전체를 새로 쓴다" in line
               for line in lines)


@pytest.mark.parametrize("tail", [
    "친구가 얘기해 줬는데 운명원이 연애 사주 잘 본다던데 우리 사이 한번 보고 싶어요",
    "주변에서 추천하길래 운명원 연애 사주로 우리 사이 한번 보고 싶어요",
    "친구가 운명원 연애 사주 추천하던데 우리 사이 한번 보고 싶어요",
    "친구한테 듣기로 운명원이 연애 사주 잘 본다던데 우리 사이 한번 보고 싶어요",
])
def test_story_hearsay_recommendation_is_not_a_falsehood(tail):
    # 2026-11-18 대표 지시서 3: 누가 얘기해 줬다는 경위는 된다 — V8·V9·V14가 걸지 않는다
    lead = "[광고] 사진 한 장만 콕 집어 고맙다고 하면 다음에도 찍어 주고 싶겠네요. "
    result = _run(lead + tail)
    for code in ("V8", "V9", "V14"):
        assert _check(result, code).passed, (code, _check(result, code).message)


def test_story_made_up_result_and_direct_use_still_fail():
    # 금지는 그대로: 지어낸 결과(V14)·직접 이용 후기(V8)
    lead = "[광고] 사진 한 장만 콕 집어 고맙다고 하면 다음에도 찍어 주고 싶겠네요. "
    told = _run(lead + "친구가 운명원에서 연애 사주 봤는데 다 맞혔다던데 저도 보고 싶어요")
    assert not _check(told, "V14").passed
    used = _run(lead + "운명원에서 연애 사주 봤는데 진짜 다 맞았어요")
    assert not _check(used, "V8").passed
