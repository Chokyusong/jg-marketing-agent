"""e2e: 내 채널 영상 자동 게시 실행기 — 창 없는 크롬과 **가짜 YouTube 페이지**.

실제 YouTube에 접속하지 않는다. 크롬이 `https://www.youtube.com/watch?...`를 요청하면
테스트가 가로채 `tests/fixtures/fake_youtube_watch.html`(지어낸 페이지)을 돌려주고,
그 밖의 요청은 모두 막는다(`prepare_context`). 창을 띄우지 않는다(headless).

- 실행기: 댓글 상자까지 내려 → 한 글자씩 입력 → 「댓글」 → 내 댓글 확인
- 로그인 안 된 프로필, 댓글을 끈 영상, 눌러도 안 달리는 경우
- API 전체: own_video_ids 영상은 youtube_auto로 승인 뒤 게시 완료, 다른 영상은 422
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app import db
from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.sandbox_driver import DriverError
from app.browser.youtube_driver import (
    TEXT_COMMENTS_OFF,
    TEXT_NOT_SIGNED_IN,
    PlaywrightYouTubeDriver,
)
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app

pytestmark = pytest.mark.e2e

OWN = "OWNVIDEO001"
OTHER = "OTHERVID001"
FAKE_PAGE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_youtube_watch.html"
WATCH = "https://www.youtube.com/watch?v="


def fake_youtube(mode: str, seen: list[str]):
    """크롬 요청을 가로챈다: 영상 페이지는 가짜 페이지, 나머지는 모두 막는다."""
    html = FAKE_PAGE.read_text(encoding="utf-8").replace("__MODE__", mode)

    def prepare(ctx) -> None:
        def handle(route) -> None:
            url = route.request.url
            seen.append(url)
            if url.startswith(WATCH):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()

        ctx.route("**/*", handle)

    return prepare


def make_driver(mode: str, seen: list[str], video_id: str = OWN) -> PlaywrightYouTubeDriver:
    driver = PlaywrightYouTubeDriver(
        video_id=video_id, headless=True, window_position=(60, -1060),
        prepare_context=fake_youtube(mode, seen),
    )
    driver.verify_timeout_ms = 1_500
    return driver


def test_driver_types_posts_and_finds_own_comment(tmp_path):
    seen: list[str] = []
    driver = make_driver("signed_in", seen)
    text = "[광고] 가짜 페이지 시험 댓글이에요. 운명원 연애 사주 한번 보고 싶네요."
    try:
        driver.open(tmp_path / "profile", WATCH + OWN)
        driver.type_comment(text, (0, 3), lambda: False)
        assert driver._page.locator("#content-text").count() == 0  # 누르기 전에는 안 달린다
        driver.click_post()
        driver.verify_posted(text)
    finally:
        driver.close()
    assert seen and all(u.startswith(WATCH + OWN) for u in seen)  # 가짜 영상 페이지만 요청
    assert driver.visited and all(u.startswith(WATCH + OWN) for u in driver.visited)


@pytest.mark.parametrize(("mode", "reason"), [
    ("signed_out", TEXT_NOT_SIGNED_IN),
    ("comments_off", TEXT_COMMENTS_OFF),
])
def test_driver_stops_before_typing(tmp_path, mode, reason):
    driver = make_driver(mode, [])
    try:
        with pytest.raises(DriverError) as err:
            driver.open(tmp_path / "profile", WATCH + OWN)
        assert err.value.reason == reason
    finally:
        driver.close()


def test_driver_reports_when_comment_does_not_appear(tmp_path):
    driver = make_driver("no_post", [])
    try:
        driver.open(tmp_path / "profile", WATCH + OWN)
        driver.type_comment("[광고] 달리지 않는 댓글", (0, 0), lambda: False)
        driver.click_post()
        with pytest.raises(DriverError):
            driver.verify_posted("[광고] 달리지 않는 댓글")
    finally:
        driver.close()


# ---------------------------------------------------------------- API 전체


@pytest.fixture
def auto_app(tmp_path, make_config) -> Iterator[tuple[str, httpx.Client, Path, list[str]]]:
    db_path = tmp_path / "e2e.sqlite3"
    config = make_config({
        "own_video_ids": [OWN],
        "browser": {"headless": True, "typing_delay_ms": [0, 3],
                    "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(config, env_path=None, db_path=db_path,
                             environ={"JG_PROFILES_DIR": str(tmp_path / "profiles")})
    seen: list[str] = []

    def youtube_factory(browser_settings, video_id):
        assert browser_settings.headless is True
        return make_driver("signed_in", seen, video_id)

    hooks = BrowserHooks(driver_factory=default_driver_factory,
                         youtube_driver_factory=youtube_factory)
    app = create_app(settings, browser_hooks=hooks)
    server = ServerThread(app, open_listen_socket())
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
    http = httpx.Client(base_url=base, timeout=30, trust_env=False)
    services = app.state.services.get()
    try:
        yield base, http, db_path, seen
    finally:
        services.jobs.shutdown(timeout=15)
        http.close()
        server.stop()


def add_approved_draft(db_path: Path, video_id: str, body: str) -> int:
    now = "2026-11-17T03:00:00+00:00"
    with db.session(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
            "VALUES (?, ?, ?, 'search')", (video_id, f"가짜 영상 {video_id}", now))
        cur = conn.execute(
            "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
            "updated_at, approved_at) VALUES (?, ?, '{}', 1, 'approved', ?, ?, ?)",
            (video_id, body, now, now, now))
        return int(cur.lastrowid)


def wait_job(http: httpx.Client, job_id: str, state: str, timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    job: dict = {}
    while time.monotonic() < deadline:
        job = http.get(f"/api/jobs/{job_id}").json()
        if job["state"] == state or job["finished"]:
            return job
        time.sleep(0.1)
    return job


def test_api_auto_post_on_own_video_after_approval(auto_app):
    _, http, db_path, seen = auto_app
    body = "요즘 운명원 얘기 많이 보이던데 저도 언젠가 연애 사주 한번 보고 싶어요."
    draft_id = add_approved_draft(db_path, OWN, body)
    res = http.post("/api/jobs", json={"video_id": OWN, "draft_id": draft_id,
                                       "target": "youtube_auto"})
    assert res.status_code == 200, res.text
    job = wait_job(http, res.json()["id"], "awaiting_approval")
    assert job["state"] == "awaiting_approval" and job["mode"] == "auto", job
    job = http.post(f"/api/jobs/{job['id']}/approve").json()
    job = wait_job(http, job["id"], "posted")
    assert job["state"] == "posted" and job["verified"] is True, job
    assert job["view_url"] == WATCH + OWN and job["target"] == "youtube"
    assert seen and all(u.startswith(WATCH + OWN) for u in seen)


def test_api_auto_post_refuses_other_videos(auto_app):
    _, http, db_path, seen = auto_app
    draft_id = add_approved_draft(db_path, OTHER, "[광고] 다른 영상 초안이에요. 운명원이 궁금해요.")
    res = http.post("/api/jobs", json={"video_id": OTHER, "draft_id": draft_id,
                                       "target": "youtube_auto"})
    assert res.status_code == 422
    assert res.json()["error"]["kind"] == "auto_post_own_only"
    assert seen == []
