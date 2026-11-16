"""YouTube 클라이언트: 저장해 둔 응답으로 검색·상세·댓글과 오류 6종."""

from datetime import UTC, datetime

import httpx
import pytest

from app.errors import AppError, ErrorKind
from app.youtube.client import YouTubeClient, classify_error, parse_duration

YT = "/youtube/v3"


def make_client(mock, key, units=None):
    on_units = units.append if units is not None else None
    return YouTubeClient(key, transport=mock.transport, on_units=on_units)


# ---------------------------------------------------------------- 정상 응답


def test_search_sends_expected_params_and_returns_ids(mock_http, fixture_json, fake_key):
    mock = mock_http().add("GET", f"{YT}/search", json=fixture_json("youtube/search.json"))
    units: list[int] = []
    client = make_client(mock, fake_key, units)
    after = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
    ids = client.search_video_ids("연애 고민", max_results=12, order="date", published_after=after)

    assert ids == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]
    params = mock.requests[0].url.params
    assert params["q"] == "연애 고민"
    assert params["type"] == "video"
    assert params["order"] == "date"
    assert params["maxResults"] == "12"
    assert params["regionCode"] == "KR"
    assert params["relevanceLanguage"] == "ko"
    assert params["publishedAfter"] == "2026-11-09T03:00:00Z"
    assert params["key"] == fake_key
    assert units == [100]


def test_search_without_period_omits_published_after(mock_http, fixture_json, fake_key):
    mock = mock_http().add("GET", f"{YT}/search", json=fixture_json("youtube/search.json"))
    make_client(mock, fake_key).search_video_ids("연애", max_results=99)
    params = mock.requests[0].url.params
    assert "publishedAfter" not in params
    assert params["maxResults"] == "50"  # API 한도로 자른다


def test_get_videos_parses_details_and_keeps_order(mock_http, fixture_json, fake_key):
    mock = mock_http().add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    units: list[int] = []
    videos = make_client(mock, fake_key, units).get_videos(
        ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3", "ZZZZZZZZZZ9"]
    )
    assert [v.video_id for v in videos] == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]
    a, b, c = videos
    assert b.title == "장거리 연애 1년차, 연락 문제로 자주 싸워요"
    assert b.channel_title == "테스트 연애상담 채널"
    assert b.published_at == "2026-11-15T09:30:00Z"
    assert b.thumbnail_url.endswith("/mqdefault.jpg")
    assert b.duration_seconds == 12 * 60 + 5
    assert (b.view_count, b.like_count, b.comment_count) == (15320, 410, 88)
    assert a.duration_seconds == 3723 and a.like_count is None  # 좋아요 숨김
    assert a.thumbnail_url.endswith("/hqdefault.jpg")
    assert c.thumbnail_url == "" and c.duration_seconds == 45
    assert mock.requests[0].url.params["part"] == "snippet,statistics,contentDetails"
    assert units == [1]


def test_get_videos_chunks_by_fifty(mock_http, fake_key):
    mock = mock_http().add("GET", f"{YT}/videos", json={"items": []})
    units: list[int] = []
    ids = [f"{i:011d}" for i in range(120)]
    assert make_client(mock, fake_key, units).get_videos(ids) == []
    assert len(mock.requests) == 3
    assert units == [1, 1, 1]


def test_get_top_comments(mock_http, fixture_json, fake_key):
    mock = mock_http().add(
        "GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json")
    )
    comments = make_client(mock, fake_key).get_top_comments("BBBBBBBBBB2")
    assert [c.text for c in comments] == [
        "저도 하루에 한 번 연락으로 싸운 적 있어요",
        "연락 문제는 결국 서로 기대치 차이 같아요",
    ]
    assert comments[0].like_count == 152
    assert not hasattr(comments[0], "author")  # 작성자 정보는 남기지 않는다
    params = mock.requests[0].url.params
    assert params["order"] == "relevance"
    assert params["maxResults"] == "20"
    assert params["videoId"] == "BBBBBBBBBB2"


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("PT45S", 45), ("PT12M5S", 725), ("PT1H2M3S", 3723), ("P1DT1S", 86401), ("P0D", None),
     ("", None), (None, None), ("bad", None)],
)
def test_parse_duration(value, seconds):
    assert parse_duration(value) == seconds


# ---------------------------------------------------------------- 오류 6종


def test_missing_key_raises_before_any_request(mock_http):
    mock = mock_http()
    with pytest.raises(AppError) as info:
        make_client(mock, None).search_video_ids("연애", max_results=5)
    assert info.value.kind is ErrorKind.MISSING_KEY
    assert mock.requests == []


@pytest.mark.parametrize(
    ("endpoint", "status", "fixture", "kind"),
    [
        ("search", 400, "error_key_invalid.json", ErrorKind.KEY_REJECTED),
        ("search", 403, "error_quota.json", ErrorKind.QUOTA_EXCEEDED),
        ("commentThreads", 403, "error_comments_disabled.json", ErrorKind.COMMENTS_DISABLED),
        ("commentThreads", 404, "error_video_not_found.json", ErrorKind.VIDEO_NOT_FOUND),
    ],
)
def test_api_errors_are_classified(mock_http, fixture_json, fake_key, endpoint, status,
                                   fixture, kind):
    mock = mock_http().add("GET", f"{YT}/{endpoint}", status_code=status,
                           json=fixture_json(f"youtube/{fixture}"))
    client = make_client(mock, fake_key)
    with pytest.raises(AppError) as info:
        if endpoint == "search":
            client.search_video_ids("연애", max_results=5)
        else:
            client.get_top_comments("BBBBBBBBBB2")
    assert info.value.kind is kind
    assert f"HTTP {status}" in info.value.detail
    assert fake_key not in str(info.value) + info.value.detail


def test_video_not_found_when_videos_list_is_empty(mock_http, fixture_json, fake_key):
    mock = mock_http().add("GET", f"{YT}/videos", json=fixture_json("youtube/videos_empty.json"))
    with pytest.raises(AppError) as info:
        make_client(mock, fake_key).get_video("ZZZZZZZZZZ9")
    assert info.value.kind is ErrorKind.VIDEO_NOT_FOUND


@pytest.mark.parametrize(
    "exc",
    [httpx.ConnectError("연결 거부"), httpx.ReadTimeout("느림"), httpx.RemoteProtocolError("끊김")],
)
def test_network_errors(mock_http, fake_key, exc):
    mock = mock_http().add("GET", f"{YT}/search", exc=exc)
    units: list[int] = []
    with pytest.raises(AppError) as info:
        make_client(mock, fake_key, units).search_video_ids("연애", max_results=5)
    assert info.value.kind is ErrorKind.NETWORK
    assert info.value.__cause__ is None  # 원래 예외(요청 주소 포함)를 이어 붙이지 않는다
    assert units == []  # 응답을 못 받으면 단위를 세지 않는다


def test_unknown_error_and_non_json(mock_http, fake_key):
    mock = mock_http()
    mock.add("GET", f"{YT}/search", status_code=500, text="<html>server error</html>")
    mock.add("GET", f"{YT}/videos", status_code=200, text="not json")
    client = make_client(mock, fake_key)
    with pytest.raises(AppError) as info:
        client.search_video_ids("연애", max_results=5)
    assert info.value.kind is ErrorKind.YOUTUBE_ERROR
    with pytest.raises(AppError) as info:
        client.get_videos(["AAAAAAAAAA1"])
    assert info.value.kind is ErrorKind.YOUTUBE_ERROR


@pytest.mark.parametrize(
    ("status", "reason", "kind"),
    [
        (403, "dailyLimitExceeded", ErrorKind.QUOTA_EXCEEDED),
        (429, "rateLimitExceeded", ErrorKind.QUOTA_EXCEEDED),
        (400, "keyInvalid", ErrorKind.KEY_REJECTED),
        (403, "accessNotConfigured", ErrorKind.KEY_REJECTED),
        (403, "ipRefererBlocked", ErrorKind.KEY_REJECTED),
        (404, "", ErrorKind.VIDEO_NOT_FOUND),
        (403, "forbidden", ErrorKind.YOUTUBE_ERROR),
        (503, "backendError", ErrorKind.YOUTUBE_ERROR),
    ],
)
def test_classify_error_reasons(status, reason, kind):
    body = {"error": {"code": status, "message": "x", "errors": [{"reason": reason}]}}
    assert classify_error(status, body) is kind


def test_repr_hides_key(fake_key, mock_http):
    client = make_client(mock_http(), fake_key)
    assert fake_key not in repr(client)
