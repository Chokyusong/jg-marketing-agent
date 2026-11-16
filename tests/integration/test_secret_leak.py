"""API 키가 오류 문구·로그·응답(`GET /api/status` 포함)·화면에 실리지 않는다."""

import logging

import httpx
import pytest
from yt_helpers import YT, add_search_and_videos

from app.youtube.client import YouTubeClient


def _assert_no_key(text: str, key: str) -> None:
    assert key not in text
    assert key[4:] not in text  # 앞부분만 가린 경우도 잡는다


@pytest.fixture
def debug_logs(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def test_status_response_has_no_key(make_client, fake_key):
    res = make_client(key=fake_key).get("/api/status")
    _assert_no_key(res.text, fake_key)
    _assert_no_key(str(res.headers), fake_key)


def test_dashboard_page_has_no_key(make_client, fake_key):
    _assert_no_key(make_client(key=fake_key).get("/").text, fake_key)


@pytest.mark.parametrize(
    ("status", "fixture"),
    [
        (400, "error_key_invalid.json"),
        (403, "error_quota.json"),
        (404, "error_video_not_found.json"),
    ],
)
def test_error_responses_and_logs_have_no_key(
    mock_http, fixture_json, fake_key, make_client, debug_logs, status, fixture
):
    mock = mock_http()
    mock.add("GET", f"{YT}/search", status_code=status, json=fixture_json(f"youtube/{fixture}"))
    mock.add("GET", f"{YT}/videos", status_code=status, json=fixture_json(f"youtube/{fixture}"))
    client = make_client(mock, key=fake_key)
    texts = [
        client.get("/api/videos").text,
        client.post("/api/videos/resolve", json={"url": "https://youtu.be/AAAAAAAAAA1"}).text,
        client.get("/api/videos/BBBBBBBBBB2").text,
    ]
    for text in texts:
        _assert_no_key(text, fake_key)
    assert mock.requests, "가짜 YouTube가 실제로 불렸어야 한다"
    _assert_no_key(debug_logs.text, fake_key)


def test_error_body_echoing_key_is_redacted(mock_http, fake_key, make_client, debug_logs):
    # YouTube 오류 메시지에 키나 요청 주소가 섞여 와도 가린다.
    body = {
        "error": {
            "code": 400,
            "message": f"bad request for https://www.googleapis.com/youtube/v3/search?key={fake_key}",
            "errors": [{"reason": "badRequest", "message": f"key {fake_key} rejected"}],
        }
    }
    mock = mock_http().add("GET", f"{YT}/search", status_code=400, json=body)
    res = make_client(mock, key=fake_key).get("/api/videos")
    assert res.status_code >= 400
    _assert_no_key(res.text, fake_key)
    _assert_no_key(debug_logs.text, fake_key)


def test_success_logs_have_no_key(mock_http, fixture_json, fake_key, make_client, debug_logs):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    res = make_client(mock, key=fake_key).get("/api/videos")
    assert res.status_code == 200
    _assert_no_key(res.text, fake_key)
    # 요청 주소에는 키가 실려 갔지만(공식 방식) 로그에는 가려져 있어야 한다.
    assert mock.requests[0].url.params["key"] == fake_key
    assert "HTTP Request" in debug_logs.text  # httpx가 주소를 남기는 줄이 실제로 있었다
    _assert_no_key(debug_logs.text, fake_key)


def test_network_error_message_has_no_key(mock_http, fake_key, debug_logs):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed {request.url}", request=request)

    mock = mock_http().add("GET", f"{YT}/search", handler=boom)
    client = YouTubeClient(fake_key, transport=mock.transport)
    with pytest.raises(Exception) as info:
        client.search_video_ids("연애", max_results=1)
    _assert_no_key(str(info.value), fake_key)
    _assert_no_key(info.value.detail, fake_key)
    _assert_no_key(debug_logs.text, fake_key)
