"""R4 뜨기 직전 영상(가점, 초안까지만): 가짜 YouTube 응답으로만(실제 접속 없음).

- 경계값: 조회수 999·1,000·5,000·5,001, 시간당 149·150, 올린 지 1분(0.1시간으로 본다)
- 시간당 조회수가 큰 순서, 쇼츠 빼기
- 검색 조건(publishedAfter = 지금 − 34시간, 최신순, 50개, 검색어)
- 같은 요청 10분 저장(할당량 기록 101 → 그대로), 10분 뒤 새로
- 게시 작업 거절(실제 게시·연습 모드 모두), 링크로 다시 불러오면 평소처럼 게시
- 화면 문구(목록 줄, 결과 없음, ③ 막힘 이유)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import test_jobs_api
from test_drafts_api import VID
from test_jobs_api import wait_state
from yt_helpers import YT

from app.config import RisingSettings
from app.youtube.rising import MIN_HOURS, hours_since, is_rising, views_per_hour

setup = test_jobs_api.setup  # 게시 작업 테스트의 준비(가짜 실행기·가짜 LLM)를 그대로 쓴다
setup_overrides = test_jobs_api.setup_overrides

NOW = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)  # tests/integration의 고정 시계와 같은 때
RULE = RisingSettings()


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def video_item(vid: str, views: int | None, hours_ago: float, duration: str = "PT10M") -> dict:
    """지어낸 영상 하나(실제 영상의 제목·설명이 아니다)."""
    return {
        "id": vid,
        "snippet": {
            "title": f"지어낸 연애 영상 {vid}",
            "channelId": "UCfakechannel00000000000",
            "channelTitle": "지어낸 채널",
            "description": "지어낸 설명",
            "publishedAt": iso(NOW - timedelta(hours=hours_ago)),
            "thumbnails": {},
        },
        "statistics": {} if views is None else {"viewCount": str(views)},
        "contentDetails": {"duration": duration},
    }


# (영상 ID, 조회수, 올린 지 몇 시간)
CASES = [
    ("RISE0000999", 999, 1.0),  # 조회수 999 → 빠짐
    ("RISE0001000", 1000, 2.0),  # 1,000 → 들어감(시간당 500)
    ("RISE0005000", 5000, 20.0),  # 5,000 → 들어감(시간당 250)
    ("RISE0005001", 5001, 20.0),  # 5,001 → 빠짐
    ("RISE0000149", 1490, 10.0),  # 시간당 149 → 빠짐
    ("RISE0000150", 1500, 10.0),  # 시간당 150 → 들어감
    ("RISE00001MN", 1200, 1 / 60),  # 올린 지 1분 → 0.1시간으로 보아 시간당 12,000
    ("RISENOVIEWS", None, 1.0),  # 조회수 비공개 → 빠짐
]


def add_rising(mock, items=None):
    items = items if items is not None else [video_item(v, n, h) for v, n, h in CASES]
    search = {"items": [{"id": {"kind": "youtube#video", "videoId": i["id"]}} for i in items]}
    mock.add("GET", f"{YT}/search", json=search)
    mock.add("GET", f"{YT}/videos", json={"items": items})
    return mock


def searches(mock):
    return [r for r in mock.requests if r.url.path == f"{YT}/search"]


@pytest.fixture
def client_mock(mock_http, fake_key, make_client):
    mock = add_rising(mock_http())
    return make_client(mock, key=fake_key), mock


# ---------------------------------------------------------------- 계산(순수 함수)


def test_hours_since_floor_is_six_minutes():
    assert hours_since(iso(NOW - timedelta(minutes=1)), NOW) == MIN_HOURS == 0.1
    assert hours_since(iso(NOW - timedelta(minutes=5)), NOW) == 0.1
    assert hours_since(iso(NOW - timedelta(minutes=12)), NOW) == pytest.approx(0.2)
    assert hours_since("", NOW) is None and hours_since("엉망", NOW) is None


@pytest.mark.parametrize(("views", "hours", "ok"), [
    (999, 1, False), (1000, 1, True), (5000, 20, True), (5001, 20, False),
    (1490, 10, False), (1500, 10, True), (None, 1, False),
])
def test_boundaries(views, hours, ok):
    per_hour = views_per_hour(views, iso(NOW - timedelta(hours=hours)), NOW)
    assert is_rising(views, per_hour, RULE) is ok


def test_rule_numbers_come_from_settings():
    strict = RisingSettings(min_views=2000, max_views=3000, min_views_per_hour=400)
    assert is_rising(2500, 500.0, strict) and not is_rising(1500, 500.0, strict)
    assert not is_rising(2500, 399.0, strict)


# ---------------------------------------------------------------- API


def test_rising_list_filters_and_sorts(client_mock):
    client, mock = client_mock
    res = client.get("/api/videos/rising")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["mode"] == "rising" and data["cached"] is False
    ids = [i["video_id"] for i in data["items"]]
    assert ids == ["RISE00001MN", "RISE0001000", "RISE0005000", "RISE0000150"]  # 시간당 큰 순서
    rates = [i["views_per_hour"] for i in data["items"]]
    assert rates == [12000.0, 500.0, 250.0, 150.0]
    assert all(i["rising"] is True and i["source"] == "rising" for i in data["items"])
    assert data["checked"] == len(CASES)
    assert data["rising"] == {"query": "연애", "min_views": 1000, "max_views": 5000,
                              "min_views_per_hour": 150, "window_hours": 34}
    # 검색 조건: 34시간 안, 최신순, 50개, 검색어 연애
    params = searches(mock)[0].url.params
    assert params["q"] == "연애" and params["order"] == "date" and params["maxResults"] == "50"
    assert params["publishedAfter"] == iso(NOW - timedelta(hours=34))
    assert "key=" not in res.text
    # 할당량: 검색 100 + 상세 1
    assert data["quota"]["used_today"] == 101


def test_same_request_cached_for_ten_minutes(client_mock, clock):
    client, mock = client_mock
    first = client.get("/api/videos/rising").json()
    again = client.get("/api/videos/rising").json()
    assert again["cached"] is True
    assert [i["video_id"] for i in again["items"]] == [i["video_id"] for i in first["items"]]
    assert [i["views_per_hour"] for i in again["items"]] == [i["views_per_hour"]
                                                            for i in first["items"]]
    assert len(searches(mock)) == 1 and again["quota"]["used_today"] == 101
    clock.advance(minutes=11)
    late = client.get("/api/videos/rising").json()
    assert late["cached"] is False and len(searches(mock)) == 2


def test_shorts_follow_the_checkbox(mock_http, fake_key, make_client):
    items = [video_item("RISESHORT01", 2000, 2.0, "PT45S"), video_item("RISELONG001", 2000, 2.0)]
    mock = add_rising(mock_http(), items)
    client = make_client(mock, key=fake_key)
    kept = client.get("/api/videos/rising?exclude_shorts=true").json()
    assert [i["video_id"] for i in kept["items"]] == ["RISELONG001"]
    assert kept["shorts_excluded"] == 1
    both = client.get("/api/videos/rising?exclude_shorts=false").json()
    assert {i["video_id"] for i in both["items"]} == {"RISESHORT01", "RISELONG001"}


def test_no_matches_is_empty_list(mock_http, fake_key, make_client):
    mock = add_rising(mock_http(), [video_item("RISE0000999", 999, 1.0)])
    data = make_client(mock, key=fake_key).get("/api/videos/rising").json()
    assert data["items"] == [] and data["checked"] == 1


def test_settings_change_rule(mock_http, fake_key, make_client):
    mock = add_rising(mock_http())
    client = make_client(mock, key=fake_key, overrides={
        "rising": {"query": "이별", "min_views": 1000, "max_views": 5000,
                   "min_views_per_hour": 300},
    })
    data = client.get("/api/videos/rising").json()
    assert [i["video_id"] for i in data["items"]] == ["RISE00001MN", "RISE0001000"]
    assert searches(mock)[0].url.params["q"] == "이별"


def test_missing_key_is_clear_error(mock_http, make_client):
    res = make_client(add_rising(mock_http()), key=None).get("/api/videos/rising")
    assert res.status_code >= 400 and res.json()["error"]["kind"] == "missing_key"


# ---------------------------------------------------------------- 초안까지만: 게시 거절


def test_job_refused_for_rising_video_then_allowed_after_reload(setup):
    client, services, approve_one, drivers, _, _ = setup
    d = approve_one()
    services.videos.mark_source([VID], "rising")  # 뜨기 직전 목록에서 고른 영상
    for target in ("youtube", "sandbox"):
        body = {"video_id": VID, "draft_id": d["id"], "target": target}
        res = client.post("/api/jobs", json=body)
        assert res.status_code == 409, res.text
        error = res.json()["error"]
        assert error["kind"] == "rising_draft_only"
        assert error["message"] == "뜨기 직전 영상은 초안까지만 만듭니다."
        assert "다시 불러와" in error["action"]
    assert drivers == []  # 크롬을 열지 않았다
    from app import db

    with db.session(services.settings.db_path) as conn:  # 게시 예약도 남기지 않는다
        assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0
    # 같은 영상을 링크로 다시 불러오면 평소처럼 게시할 수 있다
    item = client.post("/api/videos/resolve", json={"url": f"https://youtu.be/{VID}"}).json()["item"]
    assert item["source"] == "link"
    res = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "sandbox"})
    assert res.status_code == 200, res.text
    assert wait_state(client, res.json()["id"], "posted")["state"] == "posted"


def test_normal_search_resets_rising_source(setup):
    client, services, approve_one, _, _, _ = setup
    approve_one()  # 안에서 GET /api/videos(검색)를 한 번 부른다
    services.videos.mark_source([VID], "rising")
    data = client.get("/api/videos").json()  # 10분 저장한 검색 결과여도
    assert data["cached"] is True
    assert {i["video_id"]: i["source"] for i in data["items"]}[VID] == "search"
    assert services.videos.source_of(VID) == "search"


# ---------------------------------------------------------------- 화면 문구


def test_screen_words(make_client):
    client = make_client(key=None)
    discover = client.get("/static/js/discover.js").text
    assert "지금 조건에 맞는 영상이 없습니다(${risingRuleText(state.meta.rule)})" in discover
    rule_text = "조회수 ${n(rule.min_views)}~${n(rule.max_views)} · "
    assert rule_text + "시간당 ${n(rule.min_views_per_hour)}회 이상" in discover
    assert "시간당 ${Math.round(value).toLocaleString('ko-KR')}회" in discover
    assert "'뜨기 직전'" in discover and "초안까지만" in discover
    job = client.get("/static/js/job.js").text
    assert "if (video.source === 'rising') return RISING_ONLY;" in job
    assert "뜨기 직전 영상은 초안까지만 만듭니다." in job
    api = client.get("/static/js/api.js").text
    assert "/api/videos/rising" in api
