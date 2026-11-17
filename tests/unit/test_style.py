"""다듬기 검사(app/analysis/style.py, C1 다듬기) — 대표가 본 5회차 초안의 어색한 꼴."""

import pytest

from app.analysis import style as S

HJW_KEYS = ["하지원", "남자 관계", "결혼 필요성", "내짝 찾기"]


def issues(text, keys=(), earlier=()):
    return S.style_issues(text, brand="운명원", disclosure="[광고]", key_phrases=keys,
                          earlier=earlier)


def codes(text, keys=(), earlier=()):
    return [i[:2] for i in issues(text, keys, earlier)]


def test_clean_draft_has_no_issues():
    text = ("[광고] 하지원도 결혼 생각 없다니 괜히 안심되네ㅋㅋ 운명원 연애 사주 잘 본다던데 "
            "나도 언제 짝 만나는지 한번 보고 싶다.")
    assert issues(text, HJW_KEYS) == []


def test_s1_over_110_characters():
    base = "[광고] 하지원 얘기 공감돼요. 운명원 연애 사주 잘 본다던데 한번 보고 싶다."
    text = base + "ㅋ" * (111 - len(base))
    assert len(text) == 111 and codes(text) == ["S1"]
    assert "②" in issues(text)[0] and "빼도 됩니다" in issues(text)[0]
    assert codes(text[:-1]) == []  # 110자는 괜찮다


@pytest.mark.parametrize("text", [
    # 5회차 하지원 초안 두 개
    "[광고] 남자 관계를 좋아하지 않는다는 말에 고개가 끄덕여지네요. 운명원 연애 사주 잘 본다던데 "
    "내짝 찾기 언제 되는지 궁금해지네요.",
    "[광고] 결혼 생각 없다는 말에 뜨끔. 운명원 연애 사주 잘 "
    "본다던데 내짝 찾기 시기가 궁금해지네요.",
    # 바람이 다음 문장에 있어도 본다
    "[광고] 하지원 말에 뜨끔. 요즘 운명원 얘기 자주 보이던데. 내짝 찾기 언제 될지 궁금하다.",
])
def test_s2_key_phrase_stuffed_into_the_wish(text):
    assert codes(text, HJW_KEYS) == ["S2"]
    assert "'내짝 찾기'" in issues(text, HJW_KEYS)[0]


def test_s2_ignores_key_phrases_before_the_brand():
    text = "[광고] 내짝 찾기 얘기 웃프네요ㅋㅋ 운명원 연애 사주 잘 본다던데 한번 보고 싶다."
    assert codes(text, HJW_KEYS) == []


@pytest.mark.parametrize(("text", "shown"), [
    ("[광고] 애매한 관계 힘들어요. 운명원 많이들 본다던데 제가 "
     "사귀자는 말을 못 듣는 이유여쭤보고 싶네요.",
     "이유여쭤보"),
    ("[광고] 결혼 필요성 없었네라는 말에 뜨끔했어요. 운명원 잘 본다던데 한번 보고 싶다.",
     "없었네라는 말"),
    ("[광고] 그 말 공감. 운명원 잘 본다던데 한번물어보고 싶다.", "한번물어보"),
])
def test_s3_glued_words_and_ne_raneun(text, shown):
    assert codes(text) == ["S3"] and shown in issues(text)[0]


def test_s3_allows_real_compounds_and_quoted_speech():
    assert codes("[광고] 그 말 공감. 운명원 잘 본다던데 되물어보고 싶다.") == []
    assert codes("[광고] '없었네'라는 말에 뜨끔. 운명원 잘 본다던데 한번 보고 싶다.") == []


def test_s4_same_video_drafts_must_differ():
    keys = ["매일 연락", "사귀자는 말", "호감인지", "친절인지"]
    first = (
        "[광고] 매일 연락하는데 답답해요. 요즘 운명원 얘기 자주 "
        "보이던데 이 사람 마음 궁금해지네."
    )
    near = (
        "[광고] 매일 연락하는데 너무 답답해요. 요즘 운명원 얘기 "
        "자주 보이던데 이 사람 마음 궁금하네."
    )
    assert codes(near, keys, [first]) == ["S4"] and "% 같습니다" in issues(near, keys, [first])[0]
    # 다른 글이라도 운명원 꺼내는 말이 같으면
    same_mark = (
        "[광고] 호감인지 친절인지 헷갈림ㅠㅠ 운명원 얘기 자주 "
        "보이던데 이번엔 이어질지 보고 싶다."
    )
    assert "('보이던데')" in issues(same_mark, keys, [first])[0]
    # 같은 핵심 말만 쓰면(핵심 말이 둘 이상인 영상)
    same_keys = (
        "[광고] 매일 연락 오는데 진전이 없네. 주변에서 운명원 얘기 "
        "종종 하던데 언제 사귈지 보고 싶다."
    )
    assert "같은 핵심 말('매일 연락')만 썼습니다" in issues(same_keys, keys, [first])[0]
    # 다른 장면·다른 꺼내는 말이면 괜찮다
    other = (
        "[광고] 호감인지 친절인지 헷갈림ㅠㅠ 주변에서 운명원 얘기 "
        "종종 하던데 이번엔 이어질지 보고 싶다."
    )
    assert codes(other, keys, [first]) == []
    # 핵심 말이 하나뿐인 영상은 같은 핵심 말을 써도 된다
    assert codes("[광고] 5년 아깝네요. 주변에서 운명원 얘기 종종 하던데 오래 갈지 보고 싶다.",
                 ["5년"], ["[광고] 5년이 아깝대요. 운명원 잘 본다던데 한번 보고 싶다."]) == []


def test_wish_part_and_hearsay_mark():
    text = "하지원 말에 뜨끔. 운명원 연애 사주 잘 본다던데 나도 한번 보고 싶다."
    assert S.wish_part(text, "운명원") == " 연애 사주 잘 본다던데 나도 한번 보고 싶다"
    assert S.hearsay_mark(text, "운명원") == "잘 본다던데"
    assert S.wish_part("브랜드 없음.", "운명원") == "" and S.hearsay_mark("", "운명원") == ""
