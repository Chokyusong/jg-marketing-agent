"""라우터: GET /api/videos, POST /api/videos/resolve, GET /api/videos/{id}, GET /api/status."""

import pytest
from yt_helpers import YT, add_search_and_videos


def test_list_without_input_uses_default_query(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    client = make_client(mock, key=fake_key)

    res = client.get("/api/videos")
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "연애 고민"
    assert data["max_results"] == 12
    assert (data["order"], data["period"]) == ("date", "week")
    assert data["cached"] is False
    assert [v["video_id"] for v in data["items"]] == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]
    first = data["items"][0]
    assert first["title"] == "썸 타다 끝나는 이유 3가지"
    assert first["channel_title"] == "테스트 관계심리"
    assert first["published_at"] == "2026-11-16T01:00:00Z"
    assert first["thumbnail_url"].startswith("https://i.ytimg.com/")
    assert first["url"] == "https://www.youtube.com/watch?v=AAAAAAAAAA1"
    assert first["source"] == "search"
    assert data["quota"] == {"used_today": 101, "daily_limit": 10000}

    search = mock.requests[0].url.params
    assert search["q"] == "연애 고민"
    assert search["maxResults"] == "12"
    assert search["publishedAfter"] == "2026-11-09T03:00:00Z"  # 고정 시계 − 7일


def test_list_with_filters(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    client = make_client(mock, key=fake_key)
    params = {"q": "이별", "order": "viewCount", "period": "any", "max_results": 20}
    res = client.get("/api/videos", params=params)
    assert res.status_code == 200
    params = mock.requests[0].url.params
    assert (params["q"], params["order"], params["maxResults"]) == ("이별", "viewCount", "20")
    assert "publishedAfter" not in params


@pytest.mark.parametrize(
    "params",
    [{"order": "rating"}, {"period": "year"}, {"max_results": 0}, {"max_results": 51},
     {"q": "x" * 101}],
)
def test_list_rejects_bad_filters(make_client, fake_key, params):
    assert make_client(key=fake_key).get("/api/videos", params=params).status_code == 422


def test_same_search_within_ten_minutes_uses_saved_result(
    mock_http, fixture_json, fake_key, make_client, clock
):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    client = make_client(mock, key=fake_key)

    assert client.get("/api/videos").json()["cached"] is False
    assert len(mock.requests) == 2

    clock.advance(minutes=9)
    again = client.get("/api/videos").json()
    assert again["cached"] is True
    assert len(again["items"]) == 3
    assert len(mock.requests) == 2  # YouTube를 다시 부르지 않았다
    assert again["quota"]["used_today"] == 101

    clock.advance(minutes=1)
    assert client.get("/api/videos").json()["cached"] is False
    assert len(mock.requests) == 4
    assert client.get("/api/status").json()["youtube"]["quota"]["used_today"] == 202


def test_empty_search_result(mock_http, fake_key, make_client):
    mock = mock_http().add("GET", f"{YT}/search", json={"items": []})
    data = make_client(mock, key=fake_key).get("/api/videos").json()
    assert data["items"] == []
    assert len(mock.requests) == 1  # 영상이 없으면 상세 호출을 하지 않는다


def test_resolve_link(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http().add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    client = make_client(mock, key=fake_key)
    res = client.post("/api/videos/resolve", json={"url": "https://youtu.be/BBBBBBBBBB2?t=30"})
    assert res.status_code == 200
    item = res.json()["item"]
    assert item["video_id"] == "BBBBBBBBBB2"
    assert item["source"] == "link"
    assert item["view_count"] == 15320
    assert mock.requests[0].url.params["id"] == "BBBBBBBBBB2"


def test_resolve_invalid_link_does_not_call_youtube(mock_http, fake_key, make_client):
    mock = mock_http()
    res = make_client(mock, key=fake_key).post(
        "/api/videos/resolve", json={"url": "https://vimeo.com/1234"}
    )
    assert res.status_code == 422
    assert res.json()["error"]["kind"] == "invalid_url"
    assert mock.requests == []


def test_resolve_requires_url(make_client, fake_key):
    assert make_client(key=fake_key).post("/api/videos/resolve", json={}).status_code == 422


def test_get_video_detail_uses_saved_row_then_refreshes(
    mock_http, fixture_json, fake_key, make_client, clock
):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    client = make_client(mock, key=fake_key)
    client.get("/api/videos")
    assert len(mock.requests) == 2

    res = client.get("/api/videos/BBBBBBBBBB2")
    assert res.status_code == 200
    item = res.json()["item"]
    assert item["description"].startswith("시청자 사연")
    assert item["source"] == "search"
    assert len(mock.requests) == 2  # 10분 안이면 저장된 값을 쓴다

    clock.advance(minutes=11)
    assert client.get("/api/videos/BBBBBBBBBB2").json()["item"]["source"] == "search"
    assert len(mock.requests) == 3


def test_get_video_not_found(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http().add("GET", f"{YT}/videos", json=fixture_json("youtube/videos_empty.json"))
    res = make_client(mock, key=fake_key).get("/api/videos/ZZZZZZZZZZ9")
    assert res.status_code == 404
    assert res.json()["error"]["kind"] == "video_not_found"


def test_get_video_bad_id(make_client, fake_key):
    res = make_client(key=fake_key).get("/api/videos/not-an-id")
    assert res.status_code == 422
    assert res.json()["error"]["kind"] == "invalid_url"


@pytest.mark.parametrize(
    ("status", "fixture", "http_status", "kind"),
    [
        (400, "error_key_invalid.json", 502, "key_rejected"),
        (403, "error_quota.json", 429, "quota_exceeded"),
    ],
)
def test_youtube_errors_become_json(
    mock_http, fixture_json, fake_key, make_client, status, fixture, http_status, kind
):
    mock = mock_http().add(
        "GET", f"{YT}/search", status_code=status, json=fixture_json(f"youtube/{fixture}")
    )
    res = make_client(mock, key=fake_key).get("/api/videos")
    assert res.status_code == http_status
    error = res.json()["error"]
    assert error["kind"] == kind
    assert error["message"] and error["action"]


def test_missing_key_message(make_client, clean_env):
    res = make_client(key=None).get("/api/videos")
    assert res.status_code == 503
    error = res.json()["error"]
    assert error["kind"] == "missing_key"
    assert "YOUTUBE_API_KEY" in error["action"]


def test_status_reports_key_presence_only(make_client, fake_key, clean_env):
    on = make_client(key=fake_key).get("/api/status")
    assert on.status_code == 200
    assert on.json() == {
        "youtube": {"key_configured": True, "quota": {"used_today": 0, "daily_limit": 10000}}
    }
    off = make_client(key=None).get("/api/status").json()
    assert off["youtube"]["key_configured"] is False


def test_list_accepts_relevance_order(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    res = make_client(mock, key=fake_key).get("/api/videos", params={"order": "relevance"})
    assert res.status_code == 200
    assert mock.requests[0].url.params["order"] == "relevance"
