"""e2e: 게시 뒤 크롬 창 열어 두기(2026-11-18 대표) — 창 없는 크롬과 **가짜 YouTube 페이지**.

실제 YouTube에 접속하지 않는다(`r1_support.fake_youtube`가 영상 주소를 가짜 페이지로 바꾸고 그 밖의
요청은 막는다). 창을 띄우지 않는다(headless — 주 모니터에 아무것도 뜨지 않는다).

- 실행기: 게시 뒤 `show_comment`가 내 댓글을 화면 안으로 내린다 · `wait_closed`가 닫힘을 안다
- 작업 전체(API): 게시 완료가 바로 보이고 창은 열린 채 → 같은 프로필로 다음 게시를 시작하면 앞 창을
  먼저 닫아(프로필 폴더가 풀림) 다음 게시가 된다 · 시간이 다 되면 닫힘 · 사람이 닫음 · 프로그램 종료
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from r1_support import WATCH, fake_youtube_driver

from app import db
from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app

pytestmark = pytest.mark.e2e

VID = "KEEPVIDEO01"
OTHER = "KEEPVIDEO02"
BODY = "[광고] 가짜 페이지에서 창을 열어 두는 시험 댓글이에요. 운명원 연애 사주 한번 보고 싶네요."
# 내 댓글이 지금 화면(viewport) 안에 다 보이는지
IN_VIEW = """(text) => {
  const norm = (s) => (s || '').split(/\\s+/).filter(Boolean).join(' ');
  const node = [...document.querySelectorAll('ytd-comments#comments #content-text')]
    .find((n) => norm(n.textContent) === norm(text));
  if (!node) return 'missing';
  const r = node.getBoundingClientRect();
  return r.top >= 0 && r.bottom <= window.innerHeight ? 'in_view' : 'out_of_view';
}"""


def test_driver_scrolls_my_comment_into_view_and_sees_the_window_close(tmp_path):
    driver = fake_youtube_driver("signed_in", [], VID)
    try:
        driver.open(tmp_path / "profile", WATCH + VID)
        driver.type_comment(BODY, (0, 2), lambda: False)
        driver.click_post()
        driver.verify_posted(BODY)
        driver._page.evaluate("window.scrollTo(0, 0)")  # 맨 위로(댓글이 화면 밖)
        assert driver._page.evaluate(IN_VIEW, BODY) == "out_of_view"
        assert driver.show_comment(BODY) is True
        assert driver._page.evaluate(IN_VIEW, BODY) == "in_view"
        assert driver._page.evaluate("window.scrollY") > 0
        assert driver.show_comment("이 페이지에 없는 글") is False
        assert driver.wait_closed(0.1) is False  # 아직 열려 있다
        driver._ctx.close()  # 사람이 창을 닫은 것처럼(크롬 창 전체)
        assert driver.wait_closed(0.1) is True
    finally:
        driver.close()
    assert driver.wait_closed(0.1) is True  # 닫은 뒤에도 안전하게 「닫힘」


# ---------------------------------------------------------------- 작업 전체(API)


@pytest.fixture
def keep_app(tmp_path, make_config) -> Iterator[dict]:
    db_path = tmp_path / "e2e.sqlite3"
    state: dict = {"drivers": [], "human": threading.Event(), "in_view": [], "seconds": 60}

    def make(seconds):
        config = make_config({
            "browser": {"headless": True, "typing_delay_ms": [0, 3],
                        "screenshot_dir": str(tmp_path / "shots")},
            "posting": {"keep_window_seconds": seconds},
        })
        return load_settings(config, env_path=None, db_path=db_path,
                             environ={"JG_PROFILES_DIR": str(tmp_path / "profiles")})

    def youtube_factory(browser_settings, video_id):
        assert browser_settings.headless is True  # 창을 띄우지 않는다
        driver = fake_youtube_driver("signed_in", [], video_id)
        show, wait_closed = driver.show_comment, driver.wait_closed

        def probe_show(text):  # 작업 스레드에서: 내린 뒤 정말 화면 안인지 적어 둔다
            ok = show(text)
            state["in_view"].append(driver._page.evaluate(IN_VIEW, text))
            return ok

        def probe_wait(seconds):  # 「사람이 닫음」: 작업 스레드에서 크롬 창 전체를 닫는다
            if state["human"].is_set() and driver._ctx is not None:
                driver._ctx.close()
            return wait_closed(seconds)

        driver.show_comment, driver.wait_closed = probe_show, probe_wait
        state["drivers"].append(driver)
        return driver

    servers: list = []

    def start(seconds: int):
        settings = make(seconds)
        hooks = BrowserHooks(driver_factory=default_driver_factory,
                             youtube_driver_factory=youtube_factory)
        app = create_app(settings, browser_hooks=hooks)
        server = ServerThread(app, open_listen_socket())
        server.start()
        base = f"http://127.0.0.1:{server.port}"
        assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
        http = httpx.Client(base_url=base, timeout=30, trust_env=False)
        services = app.state.services.get()
        servers.append((server, http, services))
        return http, services

    state["start"] = start
    state["db"] = db_path
    try:
        yield state
    finally:
        for server, http, services in servers:
            services.jobs.shutdown(timeout=15)
            http.close()
            server.stop()


def add_approved_draft(db_path: Path, video_id: str) -> int:
    now = "2026-11-18T03:00:00+00:00"
    with db.session(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
            "VALUES (?, ?, ?, 'search')", (video_id, f"가짜 영상 {video_id}", now))
        cur = conn.execute(
            "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
            "updated_at, approved_at, disclosed) VALUES (?, ?, '{}', 1, 'approved', ?, ?, ?, 1)",
            (video_id, BODY, now, now, now))
        return int(cur.lastrowid)


def post(http: httpx.Client, db_path: Path, video_id: str) -> dict:
    draft_id = add_approved_draft(db_path, video_id)
    res = http.post("/api/jobs", json={"video_id": video_id, "draft_id": draft_id,
                                       "target": "youtube", "profile": "유튜브1"})
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        job = http.get(f"/api/jobs/{job_id}").json()
        if job["finished"]:
            return job
        time.sleep(0.1)
    raise AssertionError("게시 작업이 끝나지 않았다")


def until(check, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def messages(job: dict) -> list[str]:
    return [e["message"] for e in job["events"]]


def test_window_stays_with_my_comment_and_the_next_post_closes_it(keep_app):
    http, services = keep_app["start"](60)
    job = post(http, keep_app["db"], VID)
    assert job["state"] == "posted" and job["verified"] is True and job["window_open"] is True
    assert keep_app["in_view"] == ["in_view"]  # 내 댓글이 화면 안에 떠 있다
    first = keep_app["drivers"][0]
    assert first._ctx is not None  # 크롬이 열린 채
    assert services.jobs.busy() is False  # 「진행 중」이 아니다
    # 같은 프로필로 다음 게시: 앞 창을 먼저 닫아 프로필 폴더를 풀어야 크롬이 다시 열린다
    nxt = post(http, keep_app["db"], OTHER)
    assert nxt["state"] == "posted", nxt
    assert first._ctx is None  # 앞 창은 닫혔다
    old = http.get(f"/api/jobs/{job['id']}").json()
    assert old["window_open"] is False
    assert "크롬 창을 닫았습니다(다음 일을 시작함)" in messages(old)


def test_window_closes_when_the_time_runs_out(keep_app):
    http, _ = keep_app["start"](1)
    job = post(http, keep_app["db"], VID)
    assert job["window_open"] is True
    assert until(lambda: http.get(f"/api/jobs/{job['id']}").json()["window_open"] is False)
    assert keep_app["drivers"][0]._ctx is None
    assert "크롬 창을 닫았습니다(열어 둔 시간이 다 됨)" in messages(
        http.get(f"/api/jobs/{job['id']}").json())


def test_window_closed_by_the_person(keep_app):
    http, _ = keep_app["start"](60)
    job = post(http, keep_app["db"], VID)
    assert job["window_open"] is True
    keep_app["human"].set()
    assert until(lambda: http.get(f"/api/jobs/{job['id']}").json()["window_open"] is False)
    assert keep_app["drivers"][0]._ctx is None  # Playwright도 마저 닫았다
    assert "크롬 창을 닫았습니다(사람이 닫음)" in messages(
        http.get(f"/api/jobs/{job['id']}").json())


def test_window_closes_when_the_program_exits(keep_app):
    http, services = keep_app["start"](60)
    job = post(http, keep_app["db"], VID)
    assert job["window_open"] is True
    assert services.jobs.shutdown(timeout=15) is True  # 프로그램 창을 닫을 때와 같은 길
    assert keep_app["drivers"][0]._ctx is None
    assert "크롬 창을 닫았습니다(프로그램을 닫음)" in messages(
        http.get(f"/api/jobs/{job['id']}").json())
