"""규칙 검사 V1~V6·V8~V11 (app/analysis/validator.py, 2026-11-18 지시서 5절): 순수 함수.

규칙마다 통과 예 2개 이상과 실패 예 2개 이상, 경계값(39·40·120·121자), 이모지·영문이 섞인 글,
홍보 담당자의 정상 표현이 V8~V10에 걸리지 않는지, 사람이 고친 글도 같은 함수로 검사되는지 본다.
"""

import pytest

from app.analysis import validator as V
from app.analysis.validator import (
    CheckResult,
    Validation,
    ValidatorRules,
    find_evidence,
    normalize,
    parse_extra_patterns,
    validate,
)

RULES = ValidatorRules()  # 40~120자, 운명원, [광고]
FACTS = ["운명원은 연애 사주 상담을 하는 곳이다"]
CONTEXT = (
    "장거리 연애 1년차, 연락 문제로 자주 싸워요\n"
    "시청자 사연: 연락 빈도 때문에 다투는 장거리 커플 이야기.\n"
    "0:01 오늘은 연락 문제를 얘기해 볼게요\n"
    "1:23 하루에 한 번 연락이면 충분할까요?\n"
    "저도 하루에 한 번 연락으로 싸운 적 있어요\n"
    "연락 문제는 결국 서로 기대치 차이 같아요"
)
GOOD = (
    "[광고] 하루에 한 번 연락이면 될까요라는 질문이 와닿았어요. "
    "요즘 운명원 연애 사주 잘 본다고 하던데 저도 한번 가 보고 싶어요."
)


def run(text, *, context=CONTEXT, rules=RULES, facts=FACTS, previous=(), quote=None):
    return validate(
        text,
        context_text=context,
        rules=rules,
        brand_facts=facts,
        previous_texts=list(previous),
        evidence_quote=quote,
    )


def check(result: Validation, code: str) -> CheckResult:
    return next(c for c in result.checks if c.code == code)


def sized(n: int) -> str:
    """표기를 빼고 정확히 n자인 글(2026-11-18 대표: 「[광고]는 빼고 120자」). 근거·브랜드를 담아
    V1 말고는 통과하게 만든다."""
    mark = "[광고] "
    base = mark + "하루에 한 번 연락이면 될까요 운명원"
    assert len(base) - len(mark) <= n
    return base + "가" * (n - (len(base) - len(mark)))


# ---------------------------------------------------------------- 전체 모양


def test_good_draft_passes_every_rule():
    result = run(GOOD)
    assert result.passed is True
    assert [c.code for c in result.checks] == [
        "V1", "V2", "V3", "V4", "V5", "V6", "V8", "V9", "V10", "V11"]
    assert all(c.passed for c in result.checks)
    assert result.char_count == len(GOOD)
    assert result.evidence_quote == "하루에 한 번 연락이면"
    assert result.failures == ()
    assert result.failure_lines() == []


def test_every_check_has_name_and_one_line_message():
    bad = (
        "광고 운명원 운명원 운명원 http://x.com #태그 제일 용한 곳 "
        "다녀왔는데 소름 저도 한번 가봐야겠다"
    )
    result = run(bad, previous=[bad])
    assert result.passed is False
    for c in result.checks:
        assert c.name == V.CHECK_NAMES[c.code]
        assert c.message and "\n" not in c.message
    for c in result.failures:
        assert " — " in c.message  # 무엇이 걸렸는지 — 어떻게 고치는지
    assert len(result.failure_lines()) == len(result.failures)
    assert result.failure_lines()[0].startswith(f"{result.failures[0].code} ")


def test_to_dict_shape():
    data = run(GOOD).to_dict()
    assert set(data) == {"passed", "checks", "char_count", "evidence_quote"}
    assert set(data["checks"][0]) == {"code", "name", "passed", "message"}


# ---------------------------------------------------------------- normalize / find_evidence


def test_normalize_removes_spaces_punctuation_emoji_and_lowercases():
    assert normalize("  하루에, 한 번!  ") == "하루에한번"
    assert normalize("Hello 👍🏻 WORLD~ ^^ ❤️") == "helloworld"
    assert normalize("ㅋㅋ 좋아요…") == "ㅋㅋ좋아요"


def test_normalize_composes_hangul_nfc():
    decomposed = "하루"  # "하루"를 자모로 쪼갠 글(NFD)
    assert normalize(decomposed) == "하루"


def test_find_evidence_returns_original_phrase_from_context():
    assert find_evidence("하루에한번 연락이면 "
                         "충분할까요!!", CONTEXT) == "하루에 한 번 연락이면 충분할까요"


def test_find_evidence_none_when_nothing_shared():
    assert find_evidence("완전히 다른 말 xyz", "abc") is None
    assert find_evidence("", CONTEXT) is None


# ---------------------------------------------------------------- V1 길이 40~120자, 한 줄


@pytest.mark.parametrize("n", [40, 120])
def test_v1_boundaries_pass(n):
    result = run(sized(n))
    assert result.char_count == n + 5  # char_count는 표기까지 센 전체 길이(V1만 표기를 뺀다)
    assert check(result, "V1").passed


@pytest.mark.parametrize("n,word", [(39, "늘리세요"), (121, "줄이세요")])
def test_v1_boundaries_fail(n, word):
    v1 = check(run(sized(n)), "V1")
    assert not v1.passed
    assert f"{n}자" in v1.message and word in v1.message and "1자" in v1.message


def test_v1_does_not_count_the_disclosure():
    """대표(2026-11-18): 「[광고]는 빼고 120자」 — 표기와 그 뒤 한 칸은 세지 않는다."""
    text = sized(120)
    assert len(text) == 125  # 표기 「[광고] 」 5자 + 본문 120자
    result = run(text)
    assert check(result, "V1").passed and "120자" in check(result, "V1").message
    assert not check(run(sized(121)), "V1").passed
    assert "표기 빼고" in check(result, "V1").message


def test_v1_counts_disclosure_and_ignores_outer_spaces():
    text = sized(40)
    result = run(f"   {text}  \n ")
    assert result.char_count == 45
    assert check(result, "V1").passed


@pytest.mark.parametrize("text", [GOOD.replace("요. ", "요.\n"), GOOD.replace("요. ", "요.\r\n")])
def test_v1_newline_fails(text):
    v1 = check(run(text), "V1")
    assert not v1.passed and "줄바꿈" in v1.message


def test_v1_empty_text_fails():
    result = run("")
    assert result.char_count == 0
    assert not check(result, "V1").passed


def test_v1_emoji_and_english_count_by_code_point():
    text = sized(40)[:-2] + "👍A"  # 이모지 1자 + 영문 1자
    assert run(text).char_count == 45
    skin = sized(40)[:-2] + "👍🏻"  # 피부색이 붙은 이모지는 2자로 센다(엄격한 쪽)
    assert run(skin).char_count == 45


# ---------------------------------------------------------------- V2 링크 없음


@pytest.mark.parametrize("text", [GOOD, GOOD.replace("좋겠어요.", "좋겠어요. 사주.자세히 보세요")])
def test_v2_pass(text):
    assert check(run(text), "V2").passed


@pytest.mark.parametrize(
    "link",
    ["http://unmyung.kr", "https://x.co", "www.unmyung", "unmyung.com", "운명원.shop",
     "도메인.co.kr", "unmyung . net", "ｗｗｗ．ｕｎｍｙｕｎｇ", "운명원닷컴", "HTTPS://A.IO"],
)
def test_v2_fail(link):
    v2 = check(run(GOOD + " " + link), "V2")
    assert not v2.passed
    assert "주소로 보이는 글자" in v2.message and "링크를 지우세요" in v2.message


# ---------------------------------------------------------------- V3 해시태그 없음


@pytest.mark.parametrize("text", [GOOD, GOOD.replace("좋겠어요", "좋겠어요 ~^^")])
def test_v3_pass(text):
    assert check(run(text), "V3").passed


@pytest.mark.parametrize("tag", ["#연애", "＃장거리연애", "#love"])
def test_v3_fail(tag):
    v3 = check(run(f"{GOOD} {tag}"), "V3")
    assert not v3.passed and tag in v3.message and "#" in v3.message


# ---------------------------------------------------------------- V4 홍보 표기 맨 앞


def test_v4_pass():
    assert check(run(GOOD), "V4").passed
    other = ValidatorRules(disclosure="[AD]")
    assert check(run(GOOD.replace("[광고]", "[AD]"), rules=other), "V4").passed


@pytest.mark.parametrize(
    "text,word",
    [
        (GOOD.replace("[광고] ", ""), "없습니다"),
        (GOOD.replace("[광고] ", "") + " [광고]", "맨 앞에 있지 않습니다"),
        (GOOD.replace("[광고] ", "[광고]"), "한 칸"),
        (GOOD.replace("[광고]", "(광고)"), "없습니다"),
    ],
)
def test_v4_fail(text, word):
    v4 = check(run(text), "V4")
    assert not v4.passed and word in v4.message and "[광고]" in v4.message


def test_v4_off_passes_without_label_and_length_counts_full_text():
    """R3: 광고 표기를 끈 초안은 V4가 「표기 끔」으로 통과. 글자 수(V1)는 늘 전체 글로 센다."""
    bare = GOOD.replace("[광고] ", "")
    off = validate(bare, context_text=CONTEXT, rules=RULES, brand_facts=FACTS,
                   previous_texts=[], disclosure_required=False)
    v4 = check(off, "V4")
    assert v4.passed and v4.message == "표기 끔"
    assert off.char_count == len(bare)
    on = run(GOOD)
    assert on.char_count == len(GOOD)  # 표기 포함
    # 끈 초안에 표기가 남아 있어도 막지 않는다(사람이 붙여 쓴 글)
    kept = validate(GOOD, context_text=CONTEXT, rules=RULES, brand_facts=FACTS,
                    previous_texts=[], disclosure_required=False)
    assert check(kept, "V4").passed


# ---------------------------------------------------------------- V5 브랜드 이름 1~2번


def test_v5_pass_once_and_twice():
    assert check(run(GOOD), "V5").passed
    twice = GOOD.replace("싶어요.", "싶어요. 운명원 응원해요.")
    v5 = check(run(twice), "V5")
    assert v5.passed and "2번" in v5.message


@pytest.mark.parametrize("text,word", [(GOOD.replace("운명원 ", ""), "없습니다"),
                                       (GOOD + " 운명원 운명원", "3번")])
def test_v5_fail(text, word):
    v5 = check(run(text), "V5")
    assert not v5.passed and word in v5.message and "운명원" in v5.message


# ---------------------------------------------------------------- V6 근거가 영상 자료에 있음


def test_v6_pass_found_in_context():
    v6 = check(run(GOOD), "V6")
    assert v6.passed and "하루에 한 번 연락이면" in v6.message


def test_v6_pass_ignores_spaces_and_punctuation():
    text = (
        "[광고] 연락문제는결국, 기대치 차이라는 댓글에 공감해요. "
        "운명원에서 연애 사주 상담을 받아 보세요."
    )
    result = run(text)
    assert check(result, "V6").passed
    assert result.evidence_quote == "연락 문제는 결국"


def test_v6_pass_with_given_quote_exact_and_similar():
    assert check(run(GOOD, quote="하루에 한 번 연락이면 충분할까요?"), "V6").passed
    # 한 글자 다른 근거(유사도 0.85 이상)도 통과
    similar = check(run(GOOD, quote="하루에 한번 연락이면 충분할까"), "V6")
    assert similar.passed


@pytest.mark.parametrize(
    "quote,word",
    [("헤어진 연인에게 다시 연락하는 "
      "방법", "영상 자료에 없습니다"), ("연락 문제", "너무 짧습니다")],
)
def test_v6_fail_with_given_quote(quote, word):
    v6 = check(run(GOOD, quote=quote), "V6")
    assert not v6.passed and word in v6.message


def test_v6_fail_when_nothing_from_video():
    text = (
        "[광고] 연애 고민이 많을 때는 혼자 앓기보다 누군가와 이야기를 나눠 "
        "보세요. 운명원에서 상담받아 보세요."
    )
    result = run(text)
    v6 = check(result, "V6")
    assert not v6.passed and "6자 이상" in v6.message


def test_v6_fail_against_empty_context():
    assert not check(run(GOOD, context=""), "V6").passed


def test_v6_ignores_disclosure_and_brand_in_context():
    # 영상 자료에 "[광고]"나 "운명원"이 있어도 그것은 근거가 아니다
    context = "[광고] 운명원 협찬 영상입니다"
    text = "[광고] 운명원 협찬 영상이라는 점을 밝힙니다. 연애 고민에 도움이 됐으면 해요."
    result = run(text, context=context)
    quote = result.evidence_quote or ""
    assert "운명원" not in quote and "광고" not in quote
    assert quote == "협찬 영상"  # 표기·브랜드를 뺀 뒤 겹치는 말(5자라 V6은 실패)
    assert not check(result, "V6").passed


# ---------------------------------------------------------------- 핵심 말 고르기(분석)
# 2026-11-18 지시서로 V7(댓글에 핵심 말)은 뺐다. 분석이 핵심 말을 거르는 함수만 본다.


def test_common_words_alone_are_not_key_phrases():
    assert V.usable_key_phrases(["연락", "연애", "남자", "영상", "기대치 차이"], CONTEXT) == [
        "기대치 차이"]
    assert V.usable_key_phrases(["손편지", "장거리"], CONTEXT) == ["장거리"]


def test_title_words_become_key_phrases_when_the_model_gives_none():
    phrases = V.derive_key_phrases(["장거리 연애 1년차, 연락 문제로 자주 싸워요"], CONTEXT)
    assert "장거리" in phrases


# ---------------------------------------------------------------- V8 이용 후기 표현 없음


NORMAL_PROMOTER_LINES = [
    "[광고] 하루에 한 번 연락이면 될까요라는 말에 공감돼요. 운명원에서 "
    "연애 사주 상담을 받아 보셔도 좋겠어요.",
    "[광고] 하루에 한 번 연락이면 될까요, 이 고민에 도움이 됐으면 해요. "
    "운명원은 연애 사주 상담을 하는 곳이에요.",
    "[광고] 연락 빈도로 다투는 장거리 커플 얘기 잘 봤어요. "
    "운명원에서 상담받아 보세요. 응원할게요!",
    "[광고] 결국 서로 기대치 차이라는 말이 와닿네요. "
    "운명원에서 상담받으실 수 있어요. 참고해 보세요.",
]


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES)
def test_normal_promoter_expressions_pass_v8_v9_v10(text):
    result = run(text)
    for code in ("V8", "V9", "V10"):
        assert check(result, code).passed, (code, check(result, code).message)
    # 연애 사주 얘기 없이 운명원만 권하면 V5에 걸린다. V8~V10에 대해서는 정상 표현이다
    assert {c.code for c in result.failures} <= {"V5"}, result.failure_lines()


@pytest.mark.parametrize(
    "phrase",
    ["운명원 봤는데 소름", "상담 받아봤어요", "운명원 다녀왔는데", "운명원 가봤어요",
     "상담받았는데 좋았어요",
     "후기 남겨요", "진짜 맞더라고요", "제 사주를 "
                           "맞췄어요", "덕분에 해결했어요", "직접 상담해 봤어요",
     "상담받고 나서 편해졌어요"],
)
def test_v8_fail(phrase):
    v8 = check(run(f"{GOOD} {phrase}"), "V8")
    assert not v8.passed and "후기" in v8.message


# ---------------------------------------------------------------- V9 지어낸 연애 사연 없음
# 2026-11-17 시청자 말투로 전환(과제 PDF): 공감·의향은 통과, 지어낸 애인 이야기만 막는다.


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES[:2])
def test_v9_pass(text):
    assert check(run(text), "V9").passed


VIEWER_PERSONA_PHRASES = [
    "나도 한번 보고 싶다", "저도 언젠가 한번 가봐야겠다", "저도 비슷한 고민이 있어요",
    "완전 제 얘기네요", "저도 그랬어요", "상담 받아보고 싶네",
    "요즘 많이 보이던데 저도 한번 이용해 보고 싶네요",
]


@pytest.mark.parametrize("phrase", VIEWER_PERSONA_PHRASES)
def test_viewer_persona_intent_passes_v8_v9_v10(phrase):
    result = run(f"{GOOD} {phrase}")
    for code in ("V8", "V9", "V10"):
        assert check(result, code).passed, (phrase, code, check(result, code).message)


@pytest.mark.parametrize(
    "phrase",
    ["제 남친도 그래요", "제 여자친구가 딱 이래요", "우리 오빠도 그래요", "제 전 남친이 그랬어요"],
)
def test_v9_fail(phrase):
    v9 = check(run(f"{GOOD} {phrase}"), "V9")
    assert not v9.passed and "연애 사연" in v9.message


def test_reservation_claim_is_a_review_v8():
    # "예약했어요"는 써 본 척(이용 사실)이라 V8로 옮겼다
    assert not check(run(f"{GOOD} 운명원 예약했어요"), "V8").passed


def test_v9_does_not_catch_words_that_only_contain_short_forms():
    # "하나도", "안내", "마저도" 안의 글자는 "나도·내·저도"로 보지 않는다
    text = (
        "[광고] 하루에 한 번 연락이면 될까요, 하나도 어렵지 않게 안내 "
        "이야기를 나눠요. 운명원 상담도 있어요."
    )
    assert check(run(text), "V9").passed


# ---------------------------------------------------------------- V10 효능·최상급 표현 없음


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES[:2] + [
    "[광고] 하루에 한 번 연락이면 될까요? 이용한 분들 이야기도 "
    "참고하세요. 운명원 연애 사주 상담도 있어요.",
])
def test_v10_pass(text):
    assert check(run(text), "V10").passed


@pytest.mark.parametrize(
    "phrase",
    ["100% 맞음", "제일 용한 곳", "최고의 상담", "무조건 "
                                     "해결돼요", "보장해요", "유일한 곳", "족집게예요",
     "정확한 풀이", "잘 맞혀요", "효과 있어요", "연애운 1위"],
)
def test_v10_fail(phrase):
    v10 = check(run(f"{GOOD} {phrase}"), "V10")
    assert not v10.passed and "효능·최상급" in v10.message


def test_v10_allows_phrase_written_in_brand_facts():
    facts = FACTS + ["운명원은 연애 사주만 30년째 하는 제일 오래된 상담소다"]
    text = (
        "[광고] 하루에 한 번 연락이면 될까요? 운명원은 제일 오래된 "
        "상담소예요. 연애 사주 상담을 받아 보세요."
    )
    assert check(run(text, facts=facts), "V10").passed
    # 같은 낱말이라도 사실 문장과 다른 자리에 쓰면 그대로 걸린다
    other = (
        "[광고] 하루에 한 번 연락이면 될까요? 운명원은 제일 용한 "
        "곳이에요. 연애 사주 상담을 받아 보세요."
    )
    assert not check(run(other, facts=facts), "V10").passed
    # 사실 목록이 없으면 허용하지 않는다
    assert not check(run(text, facts=[]), "V10").passed


# ---------------------------------------------------------------- V11 이전 글과 다름


def test_v11_pass_without_previous_and_with_different_previous():
    v11 = check(run(GOOD), "V11")
    assert v11.passed and "이전 글 없음" in v11.message
    prev = ["[광고] 썸에서 연애로 넘어가지 못하는 흔한 이유가 "
            "공감됐어요. 운명원에서 상담받아 보세요."]
    assert check(run(GOOD, previous=prev), "V11").passed


@pytest.mark.parametrize(
    "prev",
    [
        GOOD,
        # 표기·브랜드만 빼고 같은 문장(다른 영상에 그대로 쓴 글)
        GOOD.replace("[광고] ", "").replace("운명원", "그곳"),
    ],
)
def test_v11_fail_similar_previous(prev):
    v11 = check(run(GOOD, previous=["완전히 다른 이전 글입니다 하하", prev]), "V11")
    assert not v11.passed and "같습니다" in v11.message and "새로 쓰세요" in v11.message


# ---------------------------------------------------------------- 사람이 고친 글


def test_human_edited_text_goes_through_same_function():
    """AI 초안을 사람이 고쳐도 같은 validate가 같은 기준으로 다시 검사한다."""
    ai_draft = GOOD
    assert run(ai_draft, quote="하루에 한 번 연락이면 충분할까요?").passed
    # 사람이 링크와 후기 표현을 넣으면 같은 함수에서 걸린다
    edited = ai_draft.replace("싶어요.", "싶어요. 저도 받아봤어요 unmyung.com")
    result = run(edited, quote="하루에 한 번 연락이면 충분할까요?")
    assert {c.code for c in result.failures} == {"V2", "V8"}
    # 다시 고치면 통과
    fixed = edited.replace(" 저도 받아봤어요 unmyung.com", "")
    assert run(fixed, quote="하루에 한 번 연락이면 충분할까요?").passed
    # 근거 없이(사람이 처음부터 쓴 글) 검사해도 같은 결과
    assert run(fixed).passed


def test_emoji_and_english_mixed_text():
    # 2026-11-18 지시서로 V12(허용 글자)를 뺐다: 영문·이모지가 섞여도 규칙 검사는 통과
    text = (
        "[광고] 하루에 한 번 연락이면 될까요 😢 LDR couple 이야기 "
        "공감돼요! 요즘 운명원 연애 사주 잘 본다던데 상담받아 보고 싶네요 🙏"
    )
    result = run(text)
    assert result.passed, result.failure_lines()
    assert result.evidence_quote == "하루에 한 번 연락이면"
    without_emoji = text.replace(" 😢", "").replace(" 🙏", "")
    assert run(without_emoji).passed, run(without_emoji).failure_lines()


# ---------------------------------------------------------------- 설정: 추가 표현


def test_extra_patterns_are_applied_per_rule():
    rules = ValidatorRules(extra_patterns=(("V10", "기가\\s?막히"), ("V9", "궁금해서")))
    text = GOOD + " 기가 막히게 봐줘요"
    assert not check(run(text, rules=rules), "V10").passed
    assert check(run(text), "V10").passed  # 기본 목록에는 없다
    assert not check(run(GOOD + " 궁금해서요", rules=rules), "V9").passed


def test_rules_from_config():
    rules = ValidatorRules.from_config(
        {"comment": {"min_chars": 30, "max_chars": 90, "brand": "운명원", "disclosure": "[AD]"}},
        [("V8", "체험")],
    )
    assert (rules.min_chars, rules.max_chars, rules.disclosure) == (30, 90, "[AD]")
    assert rules.extra_patterns == (("V8", "체험"),)


def test_parse_extra_patterns_ok_and_empty():
    assert parse_extra_patterns(None) == ()
    assert parse_extra_patterns([]) == ()
    parsed = parse_extra_patterns([{"code": "v10", "pattern": "기가 막히"}])
    assert parsed == (("V10", "기가 막히"),)


@pytest.mark.parametrize(
    "raw,word",
    [
        ("문자열", "목록"),
        (["기가 막히"], "모양"),
        ([{"code": "V2", "pattern": "x"}], "V8·V9·V10"),
        ([{"code": "V8", "pattern": " "}], "비어"),
        ([{"code": "V8", "pattern": "(깨진"}], "정규식"),
    ],
)
def test_parse_extra_patterns_errors(raw, word):
    with pytest.raises(ValueError, match=word):
        parse_extra_patterns(raw)


def test_long_context_is_fast_enough():
    # 붙여 넣은 자막 20,000자 + 댓글이 있어도 입력마다 부를 수 있을 만큼 빠르다
    import time

    context = ("연애 고민 사연을 읽어 드립니다 " * 900) + CONTEXT
    start = time.perf_counter()
    result = run(GOOD, context=context, quote="하루에 한번 연락이면 충분할까")
    assert time.perf_counter() - start < 2.0
    assert check(result, "V6").passed


# ---------------------------------------------------------------- 전해 들은 말(V10)
# 5단계에는 "잘 본다던데" 같은 평판도 V10으로 막았다. 2026-11-17 시청자 말투로 전환하면서 과제 PDF의
# 예("잘 본다던데")와 brand.facts("잘 봐주는 곳으로 알려져 있다")에 맞춰 가벼운 평판은 허용하고,
# 맞힌다는 효능(용하다·잘 맞는다·정확하다)만 남의 말로 옮겨도 막았다.
# 2026-11-17(대표, 운명원 페르소나 = 「연애 사주 잘 봐주는 곳으로 유명한 곳」): 「잘 맞는다고
# 하던데」「잘 맞는대요」「다 맞힌다더라」처럼 **들은 얘기 꼴의 평판은 통과**로 바꿨다. 「용하다」
# 「정확하다」「100%」「무조건」은 들은 얘기라도 막는다(아래 두 테스트).


@pytest.mark.parametrize(
    "phrase",
    ["운명원이 잘 본다던데", "운명원 유명하다던데", "운명원 잘 보는 곳이래요", "연애운 잘 봐준대요",
     "입소문 난 곳이에요", "평이 좋은 곳이에요", "인기 많은 상담소예요", "요즘 많이 보이던데"],
)
def test_v10_allows_light_reputation(phrase):
    assert check(run(f"{GOOD} {phrase}"), "V10").passed, phrase


@pytest.mark.parametrize(
    "phrase",
    # 2026-11-17 대표 본보기(「꽤 정확하다는 얘기가 있더라구요」): 「정확하다고들 해요」는 들은
    # 얘기 꼴이라 통과로 옮겼다(아래 test_v10_allows_relayed_reputation_since_persona)
    ["운명원 용하대요", "운명원이 용하다고 들었어요",
     "100% 맞는대요", "무조건 맞는다던데", "제일 잘 본다던데"],
)
def test_v10_catches_hearsay_accuracy_claims(phrase):
    v10 = check(run(f"{GOOD} {phrase}"), "V10")
    assert not v10.passed, phrase
    assert "효능·최상급" in v10.message


@pytest.mark.parametrize(
    "phrase",
    ["다들 잘 맞는다더라고요", "잘 맞는다고 하던데요", "연애운 잘 맞는대요", "다 맞힌다더라",
     "정확하다고들 해요", "꽤 정확하다는 얘기가 있더라구요"],
)
def test_v10_allows_relayed_reputation_since_persona(phrase):
    """2026-11-17(대표): 예전에는 걸렸던 들은 얘기 꼴의 평판 — 이제 통과(위 주석)."""
    assert check(run(f"{GOOD} {phrase}"), "V10").passed, phrase


@pytest.mark.parametrize("text", [
    # 영상 속 말을 옮기거나 권하는 말은 걸리지 않는다
    "[광고] '하루에 한 번 연락이면 될까요'라는 질문에 마음이 쓰였어요. 운명원에서 "
    "연애 사주 상담을 받아 보세요.",
    "[광고] 하루에 한 번 연락이면 될까요, 서로 잘 맞는지 궁금하다면 운명원의 연애 사주 "
    "상담을 추천드려요.",
    "[광고] 하루에 한 번 연락이면 될까요라는 고민, 이용하실 수 있는 운명원의 연애 사주 "
    "상담이 있어요.",
])
def test_v10_hearsay_patterns_leave_normal_lines_alone(text):
    result = run(text)
    assert check(result, "V10").passed, check(result, "V10").message
    # C1-V14: 권하는 말만 있는 글은 V14(뜬금없는 운명원)에만 걸린다
    assert {c.code for c in result.failures} <= {"V14"}, result.failure_lines()


def test_quote_in_context_uses_v6_rule():
    assert V.quote_in_context("하루에 한 번 연락으로 싸운 적", CONTEXT)
    assert V.quote_in_context("하루에 한번 연락으로, 싸운 적!", CONTEXT)  # 공백·부호 무시
    assert not V.quote_in_context("매일 밤 손편지를 써서 보냈대요", CONTEXT)
    assert not V.quote_in_context("연락", CONTEXT)  # 6자보다 짧다


# ---------------------------------------------------------------- 5단계: 따옴표로 옮긴 영상 속 말
# 모델 비교에서 영상 자막 "그게 제일 걱정이라고 하네요"를 따옴표로 옮긴 초안이 V10("제일")에 걸렸다.
# 영상의 말은 홍보 담당자의 주장이 아니므로 좁게 허용한다(따옴표 안, 브랜드와 떨어져 있을 때만).

QUOTE_CTX = (
    CONTEXT
    + "\n다시 만나도 같은 이유로 싸울까 봐 그게 제일 걱정이래요\n여기가 제일 정확한 곳이에요"
)
# C1: 따옴표로 옮겨도 길게(13자 이상) 옮기면 V13에 걸리므로 짧은 한 마디만 옮긴다
QUOTED = "[광고] '그게 제일 걱정이래요'라는 말이 남아요. "


def test_words_inside_a_quoted_video_line_are_not_claims():
    text = QUOTED + "요새 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요."
    result = run(text, context=QUOTE_CTX, quote="같은 이유로 싸울까 봐 그게 제일 걱정이래요")
    assert check(result, "V10").passed, check(result, "V10").message
    assert result.passed, result.failure_lines()
    # 사람이 쓴 글(근거를 글에서 찾음)도 같다
    assert check(run(text, context=QUOTE_CTX), "V10").passed
    # 영상 자료에 없는 말을 따옴표로 감싸도 면제되지 않는다
    made_up = ("[광고] '하루에 한 번 연락, 제일 좋은 방법은 없어요'라는 말이 남아요. "
               "운명원에서 상담받아 보세요.")
    assert not check(run(made_up, context=QUOTE_CTX), "V10").passed


def test_same_words_without_quote_marks_are_still_caught():
    text = ("[광고] 다시 만나도 같은 이유로 싸울까 봐 그게 제일 걱정이래요라는 말이 남아요. "
            "운명원에서 연애 사주 상담을 받아 보세요.")
    assert not check(run(text, context=QUOTE_CTX), "V10").passed


def test_claim_outside_the_quote_is_still_caught():
    text = QUOTED + "운명원이 제일 용해요."
    v10 = check(run(text, context=QUOTE_CTX), "V10")
    assert not v10.passed and "제일" in v10.message


def test_quoted_claim_next_to_the_brand_is_caught():
    # 댓글 속 "여기가 제일 정확한 곳"을 브랜드에 붙여 옮기면 전해 들은 효능이다
    text = ("[광고] 연락 문제로 힘드시죠. 운명원은 '여기가 제일 정확한 곳이에요'라는 말을 들어요. "
            "연애 사주 상담을 받아 보세요.")
    assert not check(run(text, context=QUOTE_CTX), "V10").passed


# ---------------------------------------------------------------- V4 내 채널 영상(표기 끔)


def test_v4_label_optional_only_when_not_required():
    body = GOOD.removeprefix("[광고] ")
    assert not check(run(body), "V4").passed
    off = V.validate(
        body, context_text=CONTEXT, rules=RULES, brand_facts=FACTS, previous_texts=[],
        disclosure_required=False,
    )
    assert check(off, "V4").passed and "표기 끔" in check(off, "V4").message
    # 표기를 붙였으면 끈 상태여도 맨 앞이어야 한다
    misplaced = V.validate(
        f"{body} [광고]", context_text=CONTEXT, rules=RULES, brand_facts=FACTS,
        previous_texts=[], disclosure_required=False,
    )
    assert not check(misplaced, "V4").passed


# ---------------------------------------------------------------- 시청자 말투
# 과제 PDF의 예시 댓글 말투(혼잣말·한탄·들은 얘기·막연한 처지 한마디)는 걸리지 않아야 한다
VIEWER_LINES = [
    "[광고] 근데 장거리는 진짜 연락이 전부인 듯...ㅠㅠ 연애만 하면 차이는 1인. 요즘 운명원 연애 "
    "사주 잘 본다던데 이번 인연은 오래 갈지 한번 상담받아보고 싶다.",
    "[광고] 기대치 차이라니 뼈 맞았네ㅋㅋ 썸만 타다 끝나는 편이라 더 찔림. 요즘 운명원 연애 사주 "
    "잘 본다는 얘기 많이 보이던데 나도 한번 가 볼까 싶네요.",
    "[광고] 하루에 한 번 연락이면 될까... 저도 연락 문제로 늘 고민하는 편이에요. 요새 운명원 연애 "
    "사주가 그렇게 잘 본다던데 언젠가 한번 가 보려고요^^",
]


@pytest.mark.parametrize("text", VIEWER_LINES)
def test_viewer_voice_with_hearsay_and_vague_self_talk_passes(text):
    # 실제 흐름처럼 근거 구절(V6)을 준다. 근거를 글자 그대로 옮기지 않아도 된다
    result = run(text, quote="연락 문제는 결국 서로 기대치 차이 같아요")
    assert result.passed, result.failure_lines()


# ---------------------------------------------------------------- 운명원 문장의 V8·V10 경계
HEAD = "[광고] 하루에 한 번 연락이면 될까요라는 말 공감돼요ㅠㅠ "


def test_hearsay_is_not_a_claim_but_my_own_assertion_is():
    # 들은 얘기 꼴은 V10을 통과한다
    heads = ("요즘 운명원 연애 사주 잘 본다던데",
             "요새 운명원이 연애 사주를 그렇게 잘 본다고 하던데",
             "요즘 운명원 연애사주가 꽤 정확하다는 얘기가 있더라구요.")
    for head in heads:
        result = run(f"{HEAD}{head} 저도 다음에 한번 가 보려고요.")
        assert check(result, "V10").passed, (head, check(result, "V10").message)
    # 내 단정은 V10에 걸린다
    for claim in ("운명원은 연애 사주 잘 봐요.", "운명원 연애 사주 잘 보는 곳이에요.",
                  "운명원이 정확히 맞혀요.", "운명원 연애 사주 정확해요."):
        v10 = check(run(f"{HEAD}{claim} 다음에 한번 가 보고 싶다."), "V10")
        assert not v10.passed, claim


def test_intent_passes_but_having_gone_fails_v8():
    ok = run(f"{HEAD}요즘 운명원 연애 사주 잘 본다던데 다음에 한번 가 봐야겠네요.")
    assert check(ok, "V8").passed and ok.passed, ok.failure_lines()
    ok2 = run(f"{HEAD}요즘 운명원 연애 사주 잘 본다던데 한번 가 보고 싶다.")
    assert check(ok2, "V8").passed
    gone = run(f"{HEAD}요즘 운명원 연애 사주 잘 본다던데 가 봤는데 좋았어요.")
    assert not check(gone, "V8").passed


def test_brand_facts_sentence_passes_v10():
    facts = ["운명원은 연애 사주를 잘 봐주는 곳으로 알려져 있다"]
    text = HEAD + "운명원은 연애 사주를 잘 봐주는 곳으로 알려져 있다던데 한번 가 보고 싶다."
    assert check(run(text, facts=facts), "V10").passed


# ---------------------------------------------------------------- 핵심 말 토막(분석)
# 2026-11-18 대표 시연 초안 「을이 되지 말고라니」: 말하다 만 자막 토막과 어미를 바꾼 핵심 말


@pytest.mark.parametrize(
    "phrase", ["을이 되지 말고", "기갑부터 잡고", "연락이 없어서", "보고 싶은데"]
)
def test_cut_fragment_is_not_a_key_phrase(phrase):
    assert V.is_cut_fragment(phrase)
    assert not V.key_phrase_ok(phrase, V.normalize(f"영상 자막 {phrase} 다음 말"))


@pytest.mark.parametrize("phrase", ["자존심이 아니라 겁", "석 달", "최고", "읽씹", "복종남"])
def test_whole_phrases_are_not_cut_fragments(phrase):
    assert not V.is_cut_fragment(phrase)
