"""규칙 검사 V1~V11 (app/analysis/validator.py): 네트워크·DB·LLM 없이 도는 순수 함수.

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
    "[광고] 하루에 한 번 연락이면 충분할까요라는 질문이 와닿았어요. "
    "운명원에서 연애 사주 상담을 받아 보셔도 좋겠어요."
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
    """정확히 n자(표기 포함)인 글. 근거·브랜드를 담아 V1 말고는 통과하게 만든다."""
    base = "[광고] 하루에 한 번 연락이면 충분할까요 운명원"
    assert len(base) <= n
    return base + "가" * (n - len(base))


# ---------------------------------------------------------------- 전체 모양


def test_good_draft_passes_every_rule():
    result = run(GOOD)
    assert result.passed is True
    assert [c.code for c in result.checks] == [f"V{i}" for i in range(1, 12)]
    assert all(c.passed for c in result.checks)
    assert result.char_count == len(GOOD)
    assert result.evidence_quote == "하루에 한 번 연락이면 충분할까요"
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
    assert result.char_count == n
    assert check(result, "V1").passed


@pytest.mark.parametrize("n,word", [(39, "늘리세요"), (121, "줄이세요")])
def test_v1_boundaries_fail(n, word):
    v1 = check(run(sized(n)), "V1")
    assert not v1.passed
    assert f"{n}자" in v1.message and word in v1.message and "1자" in v1.message


def test_v1_counts_disclosure_and_ignores_outer_spaces():
    text = sized(40)
    result = run(f"   {text}  \n ")
    assert result.char_count == 40
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
    assert run(text).char_count == 40
    skin = sized(40)[:-2] + "👍🏻"  # 피부색이 붙은 이모지는 2자로 센다(엄격한 쪽)
    assert run(skin).char_count == 40


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


# ---------------------------------------------------------------- V5 브랜드 이름 1~2번


def test_v5_pass_once_and_twice():
    assert check(run(GOOD), "V5").passed
    twice = GOOD.replace("좋겠어요.", "좋겠어요. 운명원 응원해요.")
    v5 = check(run(twice), "V5")
    assert v5.passed and "2번" in v5.message


@pytest.mark.parametrize("text,word", [(GOOD.replace("운명원에서 ", ""), "없습니다"),
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
        "[광고] 연락문제는결국, 서로 기대치 차이라는 댓글에 공감해요. "
        "운명원에서 연애 사주 상담을 받아 보세요."
    )
    result = run(text)
    assert check(result, "V6").passed
    assert result.evidence_quote == "연락 문제는 결국 서로 기대치 차이"


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


# ---------------------------------------------------------------- V7 글이 근거를 담음


def test_v7_pass_found_evidence():
    v7 = check(run(GOOD), "V7")
    assert v7.passed and "연속으로 겹침" in v7.message


def test_v7_pass_given_quote_partly_used():
    text = (
        "[광고] 서로 기대치 차이 이야기에 공감했어요. 운명원에서 연애 "
        "사주 상담을 받아 보셔도 좋겠어요."
    )
    assert check(run(text, quote="연락 문제는 결국 서로 기대치 차이 같아요"), "V7").passed


def test_v7_fail_given_quote_not_in_text():
    text = (
        "[광고] 연애 고민이 많을 때는 혼자 앓기보다 이야기를 나눠 "
        "보세요. 운명원에서 상담받아 보세요."
    )
    v7 = check(run(text, quote="하루에 한 번 연락이면 충분할까요"), "V7")
    assert not v7.passed and "4자 이상" in v7.message


def test_v7_fail_when_no_evidence_found():
    text = "[광고] 오늘도 좋은 하루 보내시고 행복한 일만 가득하시길 바라요. 운명원이 응원합니다."
    result = run(text)
    v7 = check(result, "V7")
    assert not v7.passed and "V6" in v7.message


# ---------------------------------------------------------------- V8 이용 후기 표현 없음


NORMAL_PROMOTER_LINES = [
    "[광고] 하루에 한 번 연락이면 충분할까요라는 말에 공감돼요. 운명원에서 "
    "연애 사주 상담을 받아 보셔도 좋겠어요.",
    "[광고] 하루에 한 번 연락이면 충분할까요, 이 고민에 도움이 됐으면 해요. "
    "운명원은 연애 사주 상담을 하는 곳이에요.",
    "[광고] 연락 빈도 때문에 다투는 장거리 커플 이야기 잘 봤어요. "
    "운명원에서 상담받아 보세요. 응원할게요!",
    "[광고] 연락 문제는 결국 서로 기대치 차이라는 말이 와닿네요. "
    "운명원에서 상담받으실 수 있어요. 참고해 보세요.",
]


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES)
def test_normal_promoter_expressions_pass_v8_v9_v10(text):
    result = run(text)
    for code in ("V8", "V9", "V10"):
        assert check(result, code).passed, (code, check(result, code).message)
    assert result.passed, result.failure_lines()


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


# ---------------------------------------------------------------- V9 소비자인 척 없음


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES[:2])
def test_v9_pass(text):
    assert check(run(text), "V9").passed


@pytest.mark.parametrize(
    "phrase",
    ["나도 한번 보고 싶다", "저도 한번 가봐야겠다", "운명원 예약했어요", "저도 비슷한 고민이 "
                                                "있어요",
     "완전 제 얘기네요", "저도 그랬어요", "제 남친도 그래요", "상담 받아보고 싶네"],
)
def test_v9_fail(phrase):
    v9 = check(run(f"{GOOD} {phrase}"), "V9")
    assert not v9.passed and "소비자인 척" in v9.message


def test_v9_does_not_catch_words_that_only_contain_short_forms():
    # "하나도", "안내", "마저도" 안의 글자는 "나도·내·저도"로 보지 않는다
    text = (
        "[광고] 하루에 한 번 연락이면 충분할까요, 하나도 어렵지 않게 안내 "
        "이야기를 나눠요. 운명원 상담도 있어요."
    )
    assert check(run(text), "V9").passed


# ---------------------------------------------------------------- V10 효능·최상급 표현 없음


@pytest.mark.parametrize("text", NORMAL_PROMOTER_LINES[:2] + [
    "[광고] 하루에 한 번 연락이면 충분할까요? 이용한 분들 이야기도 "
    "참고하세요. 운명원 연애 사주 상담도 있어요.",
])
def test_v10_pass(text):
    assert check(run(text), "V10").passed


@pytest.mark.parametrize(
    "phrase",
    ["100% 맞음", "제일 용한 곳", "최고의 상담", "무조건 "
                                     "해결돼요", "보장해요", "유일한 곳", "족집게예요",
     "유명한 곳이에요", "정확한 풀이", "잘 맞혀요", "효과 있어요", "연애운 1위"],
)
def test_v10_fail(phrase):
    v10 = check(run(f"{GOOD} {phrase}"), "V10")
    assert not v10.passed and "효능·최상급" in v10.message


def test_v10_allows_phrase_written_in_brand_facts():
    facts = FACTS + ["운명원은 연애 사주만 30년째 하는 제일 오래된 상담소다"]
    text = (
        "[광고] 하루에 한 번 연락이면 충분할까요? 운명원은 제일 오래된 "
        "상담소예요. 연애 사주 상담을 받아 보세요."
    )
    assert check(run(text, facts=facts), "V10").passed
    # 같은 낱말이라도 사실 문장과 다른 자리에 쓰면 그대로 걸린다
    other = (
        "[광고] 하루에 한 번 연락이면 충분할까요? 운명원은 제일 용한 "
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
    assert not v11.passed and "비슷합니다" in v11.message and "새로 쓰세요" in v11.message


# ---------------------------------------------------------------- 사람이 고친 글


def test_human_edited_text_goes_through_same_function():
    """AI 초안을 사람이 고쳐도 같은 validate가 같은 기준으로 다시 검사한다."""
    ai_draft = GOOD
    assert run(ai_draft, quote="하루에 한 번 연락이면 충분할까요?").passed
    # 사람이 링크와 후기 표현을 넣으면 같은 함수에서 걸린다
    edited = ai_draft.replace("좋겠어요.", "좋겠어요. 저도 받아봤어요 unmyung.com")
    result = run(edited, quote="하루에 한 번 연락이면 충분할까요?")
    assert {c.code for c in result.failures} == {"V2", "V8"}
    # 다시 고치면 통과
    fixed = edited.replace(" 저도 받아봤어요 unmyung.com", "")
    assert run(fixed, quote="하루에 한 번 연락이면 충분할까요?").passed
    # 근거 없이(사람이 처음부터 쓴 글) 검사해도 같은 결과
    assert run(fixed).passed


def test_emoji_and_english_mixed_text():
    text = (
        "[광고] 하루에 한 번 연락이면 충분할까요 😢 LDR couple 이야기 "
        "공감돼요! 운명원에서 상담받아 보세요 🙏"
    )
    result = run(text)
    assert result.passed, result.failure_lines()
    assert result.evidence_quote == "하루에 한 번 연락이면 충분할까요"


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
