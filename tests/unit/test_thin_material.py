"""자료가 얇은 영상(2026-11-18).

해시태그 낱말은 핵심 말·댓글 재료가 아니다. 자막이 없으면 인기 댓글을 먼저 쓴다.
"""

from __future__ import annotations

import pytest

from app.analysis import analyzer as A
from app.analysis import style as S
from app.analysis.analyzer import Evidence
from app.analysis.context import NO_TRANSCRIPT_NOTE
from app.analysis.validator import strip_hashtags
from app.llm import prompts as P

# 실제 영상에서 「인팁특징」이 핵심 말로 뽑혀 댓글에 들어갔다(설명란 해시태그)
CONTEXT = (
    "INFP 연애 특징 5가지 #인팁특징 #연애\n"
    "인팁이 좋아하는 사람 앞에서 하는 행동 #인팁특징 #MBTI연애\n"
    "좋아하는 사람한테는 오히려 연락을 못 하겠어요\n"
    "저도 인팁인데 연애만 하면 혼자 상상을 너무 많이 해요"
)


def test_strip_hashtags_removes_tags_only():
    assert strip_hashtags("연애 특징 #인팁특징 #연애 끝") == "연애 특징 끝"
    assert strip_hashtags("＃전각태그 남김말") == "남김말"
    assert strip_hashtags("태그 없음") == "태그 없음"


def test_hashtag_only_word_is_not_a_key_phrase():
    raw = ["인팁특징", "#인팁특징", "혼자 상상", "연락을 못"]
    kept, dropped = A.check_key_phrases(raw, CONTEXT)
    assert "인팁특징" not in kept and "혼자 상상" in kept and "연락을 못" in kept
    assert "인팁특징" in dropped


def test_word_also_in_plain_text_stays_a_key_phrase():
    # 해시태그로도 있지만 글에도 그대로 있는 말은 쓸 수 있다
    kept, _ = A.check_key_phrases(["INFP 연애"], CONTEXT + "\nINFP 연애는 늘 어렵다 #INFP")
    assert kept == ["INFP 연애"]


def test_fallback_key_phrases_do_not_come_from_hashtags():
    class _Video:
        title = "인팁 연애 특징 #인팁특징 #MBTI연애"
        description = "#인팁특징 #연애상담 #짝사랑"

    class _Stored:
        video = _Video()

    class _Ctx:
        video = _Stored()

    phrases = A.fallback_key_phrases(_Ctx(), CONTEXT + "\n#연애상담 #짝사랑")
    assert not {"인팁특징", "MBTI연애", "연애상담", "짝사랑"} & set(phrases)


def test_evidence_that_is_only_hashtags_is_dropped():
    assert A.hashtag_only("#인팁특징 #MBTI연애")
    assert not A.hashtag_only("연락을 못 하겠어요 #연애")


@pytest.mark.parametrize("prefer, first", [(False, "title"), (True, "comment")])
def test_pick_evidence_prefers_comments_without_transcript(prefer, first):
    ev = [Evidence("INFP 연애 특징 5가지", "title"),
          Evidence("좋아하는 사람한테는 오히려 연락을 못 하겠어요", "comment")]
    assert A.pick_evidence(ev, prefer_comments=prefer).source == first


def test_no_transcript_note_puts_comments_first_and_skips_hashtags():
    assert "연애 고민을 말하는 댓글 > 제목 > 설명" in NO_TRANSCRIPT_NOTE
    assert "해시태그" in NO_TRANSCRIPT_NOTE


def test_s13_hashtag_word_in_the_draft_is_rewritten():
    body = "[광고] 인팁특징 얘기 보니 혼자 상상 많이 하는 게 딱 저네요. 요즘 운명원이 연애사주를 " \
        "잘 본다고 하던데 저도 한번 가 보려고요."
    issues = S.style_issues(body, brand="운명원", disclosure="[광고]", key_phrases=["혼자 상상"],
                            context=CONTEXT)
    assert any(i.startswith("S13") for i in issues), issues
    ok = body.replace("인팁특징 얘기 보니 ", "")
    assert not any(i.startswith("S13") for i in S.style_issues(
        ok, brand="운명원", disclosure="[광고]", key_phrases=["혼자 상상"], context=CONTEXT))


def test_prompts_say_hashtag_words_are_not_material():
    _, analysis_user = P.analysis_messages("자료")
    assert "해시태그(#…) 낱말은 핵심 말이 아니다" in analysis_user
    thin = P.draft_user(analysis={"concern": "c"}, quote="q", source="comment", min_body=35,
                        max_body=115, thin=True)
    assert "**자막이 없는 영상**" in thin and "인기 댓글" in thin
    assert "제목 낱말을 되풀이하지" in thin
    plain = P.draft_user(analysis={"concern": "c"}, quote="q", source="comment", min_body=35,
                         max_body=115)
    assert "자막이 없는 영상" not in plain
    assert "해시태그(#…) 낱말" in P.draft_system(brand="운명원", disclosure="[광고]", facts=())


# ---------------------------------------------------------- 자료 상태 세 가지(2026-11-18 덧붙임)

from app.analysis.context import (  # noqa: E402
    MATERIAL_COMMENT_MIN,
    MATERIAL_DESCRIPTION_MIN,
    material_state,
)

LONG_DESC = "좋아하는 사람 앞에서 하는 행동을 다섯 가지로 정리했습니다. 공감되면 댓글 남겨 주세요"
GOOD_COMMENTS = ["저도 좋아하는 사람 앞에서는 연락을 못 해요", "이거 완전 제 얘기네요 ㅠㅠ 공감",
                 "연애만 하면 혼자 상상을 너무 많이 해요"]


def test_material_yes_when_there_is_a_transcript():
    assert material_state(has_transcript=True, description="", comments=[]) == "yes"


def test_material_no_when_description_or_comments_are_there():
    assert len(LONG_DESC) >= MATERIAL_DESCRIPTION_MIN
    assert material_state(has_transcript=False, description=LONG_DESC, comments=[]) == "no"
    assert material_state(has_transcript=False, description="", comments=GOOD_COMMENTS) == "no"


def test_material_thin_when_only_the_title_is_left():
    assert material_state(has_transcript=False, description="", comments=[]) == "thin"
    # 해시태그·주소만 있는 설명, 「ㅋㅋ」 같은 짧은 댓글은 재료로 치지 않는다
    tags = "#인팁특징 #연애 #MBTI연애 https://example.com/link www.example.com"
    short = ["ㅋㅋㅋ", "👍", "공감해요"] * 5
    assert material_state(has_transcript=False, description=tags, comments=short) == "thin"
    # 쓸 만한 댓글이 문턱(3개)보다 적으면 자료 부족, 문턱이면 자막 없음
    few = GOOD_COMMENTS[: MATERIAL_COMMENT_MIN - 1]
    assert material_state(has_transcript=False, description="짧은 설명", comments=few) == "thin"
    assert material_state(has_transcript=False, description="짧은 설명",
                          comments=GOOD_COMMENTS[:MATERIAL_COMMENT_MIN]) == "no"
