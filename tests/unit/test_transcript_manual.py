"""붙여 넣은 자막: 정리 규칙, 길이 한도, 저장·읽기·지우기, 자막 출처 설정(D1 기본: manual만)."""

import pytest

from app import db
from app.errors import AppError, ErrorKind
from app.transcript.base import Transcript, check_provider_setting
from app.transcript.manual import (
    MAX_TRANSCRIPT_CHARS,
    ManualTranscriptProvider,
    clean_transcript,
    prepare_transcript,
)

# ---------------------------------------------------------------- 정리


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  안녕하세요  ", "안녕하세요"),
        ("연락이   너무\t\t없어요", "연락이 너무 없어요"),
        ("첫 줄\r\n둘째 줄\r셋째 줄", "첫 줄\n둘째 줄\n셋째 줄"),
        ("가\n\n\n\n나", "가\n\n나"),  # 빈 줄은 최대 한 줄
        ("가\n   \n \n나", "가\n\n나"),  # 공백만 있는 줄도 빈 줄
        ("  앞 공백 \n 뒤 공백  ", "앞 공백\n뒤 공백"),
        ("전각　공백과 nbsp", "전각 공백과 nbsp"),
        ("폭​없는﻿글자", "폭없는글자"),
    ],
)
def test_clean_transcript(raw, expected):
    assert clean_transcript(raw) == expected


def test_clean_keeps_timestamps():
    raw = "0:01\n오늘은 연락 문제를 얘기해 볼게요\n1:23\n하루에 한 번이면 충분할까요\n1:02:03\n끝"
    assert clean_transcript(raw) == raw  # 시간 표시는 장면 언급의 근거라 지우지 않는다


def test_clean_normalizes_to_nfc():
    decomposed = "가"  # ㄱ + ㅏ (풀어 쓴 한글)
    assert clean_transcript(decomposed) == "가"


@pytest.mark.parametrize("raw", ["", "   ", "\n\n\t\n", "​"])
def test_empty_transcript_is_rejected(raw):
    with pytest.raises(AppError) as info:
        prepare_transcript(raw)
    assert info.value.kind is ErrorKind.TRANSCRIPT_EMPTY
    assert info.value.http_status == 422


def test_length_limit_is_after_cleaning():
    exact = "가" * MAX_TRANSCRIPT_CHARS
    assert prepare_transcript(exact) == exact
    # 공백을 줄이면 한도 안으로 들어오는 글은 받는다
    assert len(prepare_transcript(("가" + " " * 5) * 3000)) == 2 * 3000 - 1
    with pytest.raises(AppError) as info:
        prepare_transcript(exact + "나")
    assert info.value.kind is ErrorKind.TRANSCRIPT_TOO_LONG
    assert "20,001자" in info.value.detail


# ---------------------------------------------------------------- 저장


@pytest.fixture
def provider(tmp_db_path):
    db.init_db(tmp_db_path)
    with db.session(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO videos(video_id, title, fetched_at, source) "
            "VALUES ('AAAAAAAAAA1', '제목', 'now', 'search')"
        )
    return ManualTranscriptProvider(tmp_db_path)


def test_save_fetch_clear(provider):
    assert provider.fetch("AAAAAAAAAA1") is None
    saved = provider.save("AAAAAAAAAA1", "  0:01  연락   문제  \n\n\n1:23 끝 ")
    assert saved == Transcript(text="0:01 연락 문제\n\n1:23 끝", source="manual", language=None)
    assert provider.fetch("AAAAAAAAAA1") == saved

    assert provider.save("AAAAAAAAAA1", "고친 자막").text == "고친 자막"  # 덮어쓴다
    assert provider.fetch("AAAAAAAAAA1").text == "고친 자막"

    assert provider.clear("AAAAAAAAAA1") is True
    assert provider.fetch("AAAAAAAAAA1") is None
    assert provider.clear("AAAAAAAAAA1") is False  # 두 번째는 지울 것이 없다


def test_save_rejects_bad_text_without_writing(provider):
    with pytest.raises(AppError):
        provider.save("AAAAAAAAAA1", "   ")
    assert provider.fetch("AAAAAAAAAA1") is None


def test_save_keeps_other_context_columns(provider, tmp_db_path):
    with db.session(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO video_context(video_id, comments_json, built_at) "
            "VALUES ('AAAAAAAAAA1', '[{\"text\": \"댓글\", \"like_count\": 1, "
            "\"published_at\": \"\"}]', '2026-11-16T03:00:00+00:00')"
        )
    provider.save("AAAAAAAAAA1", "자막")
    provider.clear("AAAAAAAAAA1")
    with db.session(tmp_db_path) as conn:
        row = conn.execute("SELECT * FROM video_context").fetchone()
    assert "댓글" in row["comments_json"]
    assert row["built_at"] == "2026-11-16T03:00:00+00:00"
    assert (row["transcript_source"], row["transcript_text"]) == ("none", "")


# ---------------------------------------------------------------- 자막 출처 설정


def test_manual_provider_setting_is_allowed():
    check_provider_setting("manual")


@pytest.mark.parametrize("value", ["unofficial", "youtube_dl", ""])
def test_other_provider_settings_raise_clear_error(value):
    with pytest.raises(AppError) as info:
        check_provider_setting(value)
    assert info.value.kind is ErrorKind.TRANSCRIPT_PROVIDER_OFF
    assert "켜져 있지 않습니다" in info.value.message
    assert "manual" in info.value.action


def test_unofficial_module_is_not_built():
    # D1 기본값(수동 붙여넣기만): 비공식 조회 모듈을 만들지 않는다.
    import importlib.util

    assert importlib.util.find_spec("app.transcript.unofficial") is None
