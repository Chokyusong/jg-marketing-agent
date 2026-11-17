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
    "[광고] 하지원 말에 뜨끔. 요즘 운명원이 연애 사주 잘 본다고 하는 얘기가 자주 보이던데. "
    "내짝 찾기 언제 될지 궁금하다.",
])
def test_s2_key_phrase_stuffed_into_the_wish(text):
    assert codes(text, HJW_KEYS) == ["S2"]
    assert "'내짝 찾기'" in issues(text, HJW_KEYS)[0]


def test_s2_ignores_key_phrases_before_the_brand():
    text = "[광고] 내짝 찾기 얘기 웃프네요ㅋㅋ 운명원 연애 사주 잘 본다던데 한번 보고 싶다."
    assert codes(text, HJW_KEYS) == []


@pytest.mark.parametrize(("text", "shown"), [
    ("[광고] 애매한 관계 힘들어요. 운명원이 연애 쪽으로 유명하다던데 제가 "
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
    # 2026-11-17(대표, 운명원 페르소나): 꺼내는 말을 평판 꼴로 바꿨다(평판이 없으면 S7도 걸린다)
    keys = ["매일 연락", "사귀자는 말", "호감인지", "친절인지"]
    first = (
        "[광고] 매일 연락하는데 답답해요. 요즘 운명원 연애 사주 "
        "잘 본다고 입소문 났던데 이 사람 마음 궁금해지네."
    )
    near = (
        "[광고] 매일 연락하는데 너무 답답해요. 요즘 운명원 연애 사주 "
        "잘 본다고 입소문 났던데 이 사람 마음 궁금하네."
    )
    assert codes(near, keys, [first]) == ["S4"] and "% 같습니다" in issues(near, keys, [first])[0]
    # 다른 글이라도 운명원 꺼내는 말이 같으면
    same_mark = (
        "[광고] 호감인지 친절인지 헷갈림ㅠㅠ 운명원 연애 사주 잘 본다고 "
        "입소문 났던데 이번엔 이어질지 보고 싶다."
    )
    assert "('입소문')" in issues(same_mark, keys, [first])[0]
    # 같은 핵심 말만 쓰면(핵심 말이 둘 이상인 영상)
    same_keys = (
        "[광고] 매일 연락 오는데 진전이 없네. 주변에서 운명원 연애 사주 "
        "잘 본다고들 하던데 언제 사귈지 보고 싶다."
    )
    assert "같은 핵심 말('매일 연락')만 썼습니다" in issues(same_keys, keys, [first])[0]
    # 다른 장면·다른 꺼내는 말이면 괜찮다
    other = (
        "[광고] 호감인지 친절인지 헷갈림ㅠㅠ 주변에서 운명원 연애 사주 "
        "잘 본다고들 하던데 이번엔 이어질지 보고 싶다."
    )
    assert codes(other, keys, [first]) == []
    # 핵심 말이 하나뿐인 영상은 같은 핵심 말을 써도 된다
    assert codes("[광고] 5년 아깝네요. 운명원이 연애 쪽으로 유명하다던데 오래 갈지 보고 싶다.",
                 ["5년"],
                 ["[광고] 5년이 아깝대요. 운명원 잘 본다던데 한번 보고 싶다."]) == []


def test_wish_part_and_hearsay_mark():
    text = "하지원 말에 뜨끔. 운명원 연애 사주 잘 본다던데 나도 한번 보고 싶다."
    assert S.wish_part(text, "운명원") == " 연애 사주 잘 본다던데 나도 한번 보고 싶다"
    # 2026-11-17: 1번 줄 표시를 「사주 잘 본다던데」로 좁혔다(「그렇게 잘 본다던데」와 겹치지 않게)
    assert S.hearsay_mark(text, "운명원") == "사주 잘 본다던데"
    assert S.wish_part("브랜드 없음.", "운명원") == "" and S.hearsay_mark("", "운명원") == ""


# (2026-11-17 운명원 페르소나: 아래 글들의 꺼내는 말에 평판을 넣었다 — 평판이 없으면 S7도 걸린다)
# ---------------------------------------------------------------- 6회차에서 찾은 꼴(7회차부터 잡음)

R1_KEYS = ["권태기", "휴대폰만 봐요", "설레지가 않아", "말을 꺼내면"]


@pytest.mark.parametrize("text", [
    "[광고] 그 말 공감. 운명원 잘 본다던데 내 인연이 있는지 한번 가 봐야겠어요",
    "[광고] 그 말 공감. 운명원 잘 본다던데 내 마음이 움직이는 때가 언제인지 한번 가 봐야겠네요",
    "[광고] 그 말 공감. 운명원 연애 사주 잘 본다고들 하던데 내 마음 정리되는지 다음에 한번 가 "
    "봐야겠네요",
])
def test_s3_a_question_cannot_take_ga_bwayagetda(text):
    assert codes(text) == ["S3"] and "앞뒤가 안 맞습니다" in issues(text)[0]


def test_s3_ga_bwayagetda_alone_or_after_gunggeumhaeseo_is_fine():
    assert codes("[광고] 그 말 공감. 운명원이 연애 쪽으로 유명하다던데 다음에 한번 가 "
        "봐야겠어요.") == []
    assert codes("[광고] 그 말 공감. 운명원이 연애운을 잘 봐준다길래 언제 오는지 궁금해서 "
        "다음에 한번 "
        ""
                 "가 봐야겠어요.") == []
    assert codes("[광고] 그 말 공감. 운명원 잘 본다던데 언제 오는지 한번 보고 싶다.") == []


# ---------------------------------------------------------------- 7회차 손질(8회차부터 잡음)

R2_CONTEXT = (
    "동아리 선배를 2년째 좋아해요\n3년 사귄 남자친구와 대화가 줄었어요. 석 달 동안 연락만 기다렸고 "
    "5년 만난 사람과 결혼하려는데 부모님이 반대해요"
)


def ctx_codes(text, context=R2_CONTEXT):
    return [i[:2] for i in S.style_issues(text, brand="운명원", disclosure="[광고]",
                                          context=context)]


@pytest.mark.parametrize(("text", "shown"), [
    # 7회차 실제 초안: 영상 속 숫자를 내 일처럼
    ("[광고] 휴대폰만 본다는 말이 남네요. 3년 사귄 관계라 권태기인지 식은 건지 모르겠어서, "
     "운명원 연애 사주 잘 본다던데 다음에 한번 가 봐야겠네요.", "3년"),
    ("[광고] 2년째 마음이 정리 안 돼서 고백도 못 해봤어요 ㅠㅠ 요즘 운명원이 연애 사주 잘 "
        "본다고 하는 얘기가 자주 보이던데 "
        ""
     "이번엔 이어질지 한번 물어보고 싶어요.", "2년"),
    ("[광고] 반대한다는 말에 마음이 무거워지네요. 저도 5년이란 시간이 아까워 두렵습니다. "
     "요즘 운명원 연애 사주 잘 본다던데 한번 보고 싶다.", "5년"),
    ("[광고] 저도 석 달째 연락만 기다리는 중... 운명원 잘 본다던데 한번 보고 싶다.", "석 달"),
    # 8회차 실제 초안: 「기다리다 보니」의 「보니」는 영상 얘기 표지가 아니다
    ("[광고] 마음을 정리한다는 말에 한참 멈췄어요 ㅠㅠ 2년째 기다리다 보니 고백이 무서울 "
     "뿐이죠. 요즘 운명원 연애 사주 잘 본다고 입소문 났던데 나도 한번 볼까 싶다.", "2년"),
])
def test_s5_number_from_the_video_written_as_mine(text, shown):
    got = S.style_issues(text, brand="운명원", disclosure="[광고]", context=R2_CONTEXT)
    assert [i[:2] for i in got] == ["S5"] and f"'{shown}'" in got[0]
    assert "숫자 없이 내 말로" in got[0] and "비슷한 처지라고 말하는 것은 괜찮습니다" in got[0]


@pytest.mark.parametrize("text", [
    # 비슷한 처지라는 공감은 시청자 말투(기획 담당 2026-11-17)
    "[광고] 같은 이유로 싸울까 봐 연락 못 하는 거 완전 내 얘기네... 운명원이 연애 사주 잘 "
    "본다고 하는 얘기가 자주 보이던데 "
    ""
    "한번 보고 싶다.",
    "[광고] 저도 비슷해서 남 얘기 같지 않아요. 운명원 잘 본다던데 한번 보고 싶다.",
    "[광고] 맨날 연애하면 차이기만 했던 1인... 운명원 잘 본다던데 우리 인연도 한번 보고 싶다.",
    "[광고] 저도 오래 만나다 보니 권태기인지 헷갈려서. 운명원 잘 본다던데 우리도 한번 보고 싶다.",
    # 숫자를 영상 얘기로 받으면 괜찮다
    "[광고] 3년 사귀었는데 대화가 줄었대요 ㅠㅠ 운명원 잘 본다던데 한번 보고 싶다.",
    "[광고] 5년 만나도 반대라니... 운명원 잘 본다던데 한번 보고 싶다.",
    "[광고] 3년이면 진짜 식은 건지 모르겠네. 운명원 잘 본다던데 한번 보고 싶다.",
    "[광고] 5년을 만난 사람인데 고민 많으시죠. 운명원 잘 본다던데 한번 보고 싶다.",
    "[광고] 석 달 기다렸다는 댓글 보니 짠하네요. 운명원 잘 본다던데 한번 보고 싶다.",
    # 영상에 없는 숫자는 내 처지 한마디
    "[광고] 저도 7년째 솔로... 운명원 잘 본다던데 한번 보고 싶다.",
])
def test_s5_allows_a_similar_situation_and_numbers_taken_as_the_videos(text):
    assert ctx_codes(text) == []


def test_s5_needs_the_video_text():
    text = "[광고] 2년째 마음이 정리 안 돼요. 운명원 잘 본다던데 한번 보고 싶다."
    assert ctx_codes(text) == ["S5"] and ctx_codes(text, context="") == []


@pytest.mark.parametrize("text", [
    "[광고] 그 말 공감. 요즘 운명원 연애 사주 잘 본다던데 제 연애 운세 한번 가 봐야겠네요.",
    "[광고] 그 말 공감. 운명원 잘 본다던데 연애 시기 다음에 한번 가 봐야겠어요.",
    "[광고] 그 말 공감. 운명원 잘 본다던데 궁합 가 봐야겠다.",
])
def test_s3_fortune_or_timing_cannot_take_ga_bwayagetda(text):
    got = issues(text)
    assert [i[:2] for i in got] == ["S3"] and "운세·시기는 가는 곳이 아니니" in got[0]


def test_s3_going_to_unmyeongwon_or_going_to_see_a_reading_is_fine():
    assert codes("[광고] 그 말 공감. 운명원 잘 본다던데 연애 사주 한번 보러 가 봐야겠다.") == []
    assert codes("[광고] 그 말 공감. 운명원 잘 본다던데 연애 운세 한번 보고 싶다.") == []
    assert codes("[광고] 그 말 공감. 운명원 잘 본다던데 다음에 한번 가 봐야겠네요.") == []
