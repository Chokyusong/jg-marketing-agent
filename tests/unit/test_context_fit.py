"""맥락 글 만들기(순수 함수): prompt_text 길이 맞추기와 search_text.

규칙(PLAYBOOK 3단계): 설명 1,500자, 댓글 200자 × 20개, 자막이 남은 한도를 넘으면
앞 절반 + 뒤 절반을 남기고 가운데를 `…(중략)…`으로. 결과는 항상 한도 이하.
"""

from dataclasses import replace

import pytest

from app.analysis.context import (
    COMMENT_LIMIT,
    DESCRIPTION_LIMIT,
    MIDDLE_CUT,
    VideoContext,
    fit_prompt,
    search_text,
)
from app.youtube.client import Comment, Video
from app.youtube.service import StoredVideo


def make_context(
    *,
    transcript: str = "",
    description: str = "하루에 한 번 연락하는 커플, 괜찮을까요?",
    comments: list[str] | None = None,
    disabled: bool = False,
) -> VideoContext:
    video = Video(
        video_id="BBBBBBBBBB2",
        title="연락 문제로 싸우는 커플",
        channel_id="UC1",
        channel_title="테스트 관계심리",
        description=description,
        published_at="2026-11-15T09:00:00Z",
        thumbnail_url="",
        duration_seconds=600,
        view_count=100,
        like_count=1,
        comment_count=2,
    )
    comment_list = tuple(Comment(text=t, like_count=0, published_at="") for t in (comments or []))
    has_transcript = bool(transcript)
    return VideoContext(
        video=StoredVideo(video=video, source="search", fetched_at="2026-11-16T03:00:00+00:00"),
        body=transcript or f"{video.title}\n{description}",
        body_source="transcript" if has_transcript else "title_description",
        transcript_source="manual" if has_transcript else "none",
        transcript_text=transcript,
        comments=comment_list,
        comments_disabled=disabled,
        built_at="2026-11-16T03:00:00+00:00",
    )


# ---------------------------------------------------------------- 짧음 · 딱 맞음 · 넘침


def test_short_context_is_not_cut():
    ctx = make_context(transcript="0:01 연락은 하루에 한 번이면 충분할까요", comments=["공감해요"])
    fitted = fit_prompt(ctx, 6000)
    assert not fitted.truncated and not fitted.transcript_truncated
    text = fitted.text
    assert "[제목] 연락 문제로 싸우는 커플" in text
    assert "[채널] 테스트 관계심리" in text
    assert "[설명]\n하루에 한 번 연락하는 커플, 괜찮을까요?" in text
    assert "[자막 · 붙여 넣은 자막]\n0:01 연락은 하루에 한 번이면 충분할까요" in text
    assert "[인기 댓글 1개]\n- 공감해요" in text
    assert MIDDLE_CUT not in text


def test_exact_fit_is_not_cut():
    ctx = make_context(transcript="가" * 3000, comments=["댓글"] * 5)
    full = fit_prompt(ctx, 1_000_000).text
    fitted = fit_prompt(ctx, len(full))
    assert fitted.text == full
    assert not fitted.truncated


def test_one_over_keeps_head_and_tail():
    transcript = "앞" * 1500 + "가운데" * 100 + "뒤" * 1500
    ctx = make_context(transcript=transcript)
    full = fit_prompt(ctx, 1_000_000).text
    fitted = fit_prompt(ctx, len(full) - 1)
    assert fitted.truncated and fitted.transcript_truncated
    assert len(fitted.text) <= len(full) - 1
    assert MIDDLE_CUT in fitted.text


@pytest.mark.parametrize("max_chars", [6000, 3000, 1200])
def test_long_transcript_keeps_front_and_back_halves(max_chars):
    transcript = "0:01 처음 장면 " + "중간 이야기 " * 3000 + "9:59 마지막 장면"
    ctx = make_context(transcript=transcript, comments=["공감해요"] * 3)
    fitted = fit_prompt(ctx, max_chars)
    assert len(fitted.text) <= max_chars
    assert fitted.transcript_truncated
    assert "0:01 처음 장면" in fitted.text  # 앞부분
    assert "9:59 마지막 장면" in fitted.text  # 뒷부분
    assert fitted.text.count(MIDDLE_CUT) == 1

    kept = fitted.text.split("[자막 · 붙여 넣은 자막]\n", 1)[1].split("\n[인기 댓글", 1)[0]
    head, tail = kept.split(MIDDLE_CUT)
    assert abs(len(head) - len(tail)) <= 1  # 앞 절반 + 뒤 절반
    assert transcript.startswith(head) and transcript.endswith(tail)


def test_default_limit_comes_from_settings(make_config, tmp_db_path, clean_env):
    from app.config import load_settings

    settings = load_settings(make_config(), env_path=None, db_path=tmp_db_path, environ={})
    assert settings.context_chars == 6000
    custom = load_settings(
        make_config({"llm": {"context_chars": 4000}}), env_path=None, db_path=tmp_db_path,
        environ={},
    )
    assert custom.context_chars == 4000


# ---------------------------------------------------------------- 설명 · 댓글 한도


def test_description_is_cut_to_1500():
    ctx = make_context(description="설" * 4000)
    fitted = fit_prompt(ctx, 1_000_000)
    desc = fitted.text.split("[설명]\n", 1)[1].split("\n[자막]", 1)[0]
    assert len(desc) == DESCRIPTION_LIMIT
    assert desc.endswith("…")
    assert fitted.truncated and not fitted.transcript_truncated


def test_comments_are_cut_to_200_each_and_20_total():
    long_comment = "댓" * 500
    ctx = make_context(comments=[long_comment] + [f"댓글 {i}" for i in range(1, 25)])
    fitted = fit_prompt(ctx, 1_000_000)
    lines = [line for line in fitted.text.split("\n") if line.startswith("- ")]
    assert len(lines) == 20
    assert len(lines[0]) == 2 + COMMENT_LIMIT and lines[0].endswith("…")
    assert "[인기 댓글 20개]" in fitted.text
    assert "- 댓글 19" in fitted.text
    assert "- 댓글 20" not in fitted.text  # 21번째(댓글 20)부터는 빠진다
    assert fitted.truncated


def test_comment_newlines_become_one_line():
    ctx = make_context(comments=["첫 줄\n\n둘째   줄"])
    assert "- 첫 줄 둘째 줄" in fit_prompt(ctx, 6000).text


def test_tiny_limit_drops_comments_then_shortens_description():
    ctx = make_context(description="설" * 1000, comments=["댓" * 150] * 20, transcript="자막" * 50)
    for limit in (2000, 800, 300, 60, 5):
        fitted = fit_prompt(ctx, limit)
        assert len(fitted.text) <= limit
        assert fitted.truncated


# ---------------------------------------------------------------- 자막 없음 · 댓글 막힘


def test_no_transcript_uses_title_and_description():
    ctx = make_context(comments=["공감해요"])
    text = fit_prompt(ctx, 6000).text
    assert "[자막] 없음 · 제목과 설명으로 대신" in text
    assert "[설명]\n하루에 한 번 연락하는 커플" in text


def test_comments_disabled_and_empty_are_labelled():
    assert "[인기 댓글] 댓글이 막힌 영상" in fit_prompt(make_context(disabled=True), 6000).text
    assert "[인기 댓글] 없음" in fit_prompt(make_context(), 6000).text


def test_empty_description_is_labelled():
    assert "[설명]\n(설명 없음)" in fit_prompt(make_context(description=""), 6000).text


# ---------------------------------------------------------------- search_text


def test_search_text_is_not_cut():
    transcript = "자막 " * 5000
    ctx = make_context(
        transcript=transcript.strip(), description="설" * 4000, comments=["댓" * 500] * 25
    )
    text = search_text(ctx)
    assert "연락 문제로 싸우는 커플" in text
    assert "설" * 4000 in text
    assert transcript.strip() in text
    assert text.count("댓" * 500) == 25
    assert MIDDLE_CUT not in text


def test_search_text_skips_empty_parts():
    ctx = replace(make_context(description=""), comments=())
    assert search_text(ctx) == "연락 문제로 싸우는 커플"
