"""e2e: 실제 게시 실행기(R3, 어떤 영상이든) — 창 없는 크롬과 **가짜 YouTube 페이지**.

실제 YouTube에 접속하지 않는다. 크롬이 `https://www.youtube.com/watch?...`를 요청하면
테스트가 가로채 `tests/fixtures/fake_youtube_watch.html`(지어낸 페이지)을 돌려주고,
그 밖의 요청은 모두 막는다(`prepare_context`). 창을 띄우지 않는다(headless).

- 실행기: 댓글 상자까지 내려 → 한 글자씩 입력 → 「댓글」 → 내 댓글 확인
- 실패: 로그인 안 된 프로필, 댓글을 막은 영상, 요소 없음(어느 요소인지 사유에), 페이지 이탈,
  눌러도 안 달리는 경우
- 화면 요소 점검(`youtube_check.inspect_page`)이 가짜 페이지에서 읽기만 하는지
- API 전체: 아무 영상 ID로 youtube(옛 이름 assist·youtube_auto 포함) → 바로 게시 완료
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from r1_support import WATCH, fake_youtube_driver

from app import db
from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.sandbox_driver import DriverError
from app.browser.youtube_check import (
    ABSENT_OK,
    FOUND,
    LOGIN_SIGNED_IN,
    LOGIN_SIGNED_OUT,
    NEEDS_CLICK,
    NOT_APPLICABLE,
    format_table,
    inspect_page,
)
from app.browser.youtube_driver import (
    CODE_SIGNED_OUT,
    TEXT_COMMENTS_OFF,
    TEXT_LEFT_PAGE,
    TEXT_NOT_SIGNED_IN,
    PlaywrightYouTubeDriver,
    missing_text,
)
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app

pytestmark = pytest.mark.e2e

VID = "ANYVIDEO001"  # 아무 영상(내 채널 영상 목록 같은 것은 없다)
OTHER = "OTHERVID001"


def make_driver(mode: str, seen: list[str], video_id: str = VID) -> PlaywrightYouTubeDriver:
    return fake_youtube_driver(mode, seen, video_id)


def test_driver_types_posts_and_finds_own_comment(tmp_path):
    seen: list[str] = []
    driver = make_driver("signed_in", seen)
    text = "[광고] 가짜 페이지 시험 댓글이에요. 운명원 연애 사주 한번 보고 싶네요."
    try:
        driver.open(tmp_path / "profile", WATCH + VID)
        driver.type_comment(text, (0, 3), lambda: False)
        assert driver._page.locator("#content-text").count() == 0  # 누르기 전에는 안 달린다
        driver.click_post()
        driver.verify_posted(text)
    finally:
        driver.close()
    assert seen and all(u.startswith(WATCH + VID) for u in seen)  # 가짜 영상 페이지만 요청
    assert driver.visited and all(u.startswith(WATCH + VID) for u in driver.visited)


@pytest.mark.parametrize(("mode", "reason", "code"), [
    ("signed_out", TEXT_NOT_SIGNED_IN, CODE_SIGNED_OUT),
    ("comments_off", TEXT_COMMENTS_OFF, "comments_off"),
    ("leave", TEXT_LEFT_PAGE, ""),
])
def test_driver_stops_before_typing(tmp_path, mode, reason, code):
    driver = make_driver(mode, [])
    try:
        with pytest.raises(DriverError) as err:
            driver.open(tmp_path / "profile", WATCH + VID)
        assert err.value.reason == reason
        assert err.value.code == code
        assert err.value.screenshot is True
    finally:
        driver.close()


def test_driver_names_the_missing_element(tmp_path):
    driver = make_driver("no_submit", [])
    try:
        driver.open(tmp_path / "profile", WATCH + VID)
        driver.type_comment("[광고] 단추가 없는 페이지", (0, 0), lambda: False)
        with pytest.raises(DriverError) as err:
            driver.click_post()
        assert err.value.reason == missing_text("submit")
        assert "「댓글」 게시 단추" in err.value.reason
        assert "ytd-commentbox #submit-button" in err.value.reason
        shot = tmp_path / "shot.png"
        assert driver.screenshot(shot) and shot.read_bytes().startswith(b"\x89PNG")
    finally:
        driver.close()


def test_driver_reports_when_comment_does_not_appear(tmp_path):
    driver = make_driver("no_post", [])
    try:
        driver.open(tmp_path / "profile", WATCH + VID)
        driver.type_comment("[광고] 달리지 않는 댓글", (0, 0), lambda: False)
        driver.click_post()
        with pytest.raises(DriverError):
            driver.verify_posted("[광고] 달리지 않는 댓글")
    finally:
        driver.close()


# ---------------------------------------------------------------- 화면 요소 점검(읽기만)


def _inspect(tmp_path, mode: str):
    seen: list[str] = []
    driver = make_driver(mode, seen)
    try:
        driver._launch(tmp_path / "profile")
        driver.prepare_context(driver._ctx)
        page = driver._page
        clicks: list[str] = []
        page.expose_function("jgClicked", lambda: clicks.append("x"))
        page.add_init_script(
            "document.addEventListener('click', () => window.jgClicked(), true);"
            "document.addEventListener('keydown', () => window.jgClicked(), true);"
        )
        page.goto(WATCH + VID, wait_until="domcontentloaded")
        check = inspect_page(page, VID, pause_ms=200)
        typed = page.locator("#contenteditable-root").count() and page.locator(
            "#contenteditable-root"
        ).first.inner_text()
        return check, clicks, typed, seen
    finally:
        driver.close()


def test_page_check_signed_out_reads_only(tmp_path):
    check, clicks, typed, seen = _inspect(tmp_path, "signed_out")
    assert clicks == [] and not typed  # 누르지도 입력하지도 않는다
    assert check.login == LOGIN_SIGNED_OUT and not check.left_page
    assert check.row("sign_in").result == FOUND
    assert check.row("comments").result == FOUND
    assert check.row("placeholder").result == FOUND
    assert check.row("comments_off").result == ABSENT_OK
    assert check.row("signed_in").result == NOT_APPLICABLE
    # 가짜 페이지는 글 칸을 미리 숨겨 그려 둔다(실제 유튜브는 눌러야 생긴다)
    assert check.row("editor").result in (FOUND, NEEDS_CLICK)
    table = format_table(check)
    assert "「로그인」 단추" in table and "a[href*=\"ServiceLogin\"]" in table
    assert all(u.startswith(WATCH + VID) for u in seen)


def test_page_check_signed_in_and_comments_off(tmp_path):
    check, clicks, _, _ = _inspect(tmp_path, "signed_in")
    assert clicks == [] and check.login == LOGIN_SIGNED_IN
    assert check.row("signed_in").result == FOUND
    off, clicks, _, _ = _inspect(tmp_path / "off", "comments_off")
    assert clicks == []
    assert off.row("comments_off").result == FOUND
    assert off.row("placeholder").result == NOT_APPLICABLE


# ---------------------------------------------------------------- API 전체


@pytest.fixture
def live_app(tmp_path, make_config) -> Iterator[tuple]:
    db_path = tmp_path / "e2e.sqlite3"
    config = make_config({
        "browser": {"headless": True, "typing_delay_ms": [0, 3],
                    "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(config, env_path=None, db_path=db_path,
                             environ={"JG_PROFILES_DIR": str(tmp_path / "profiles")})
    assert settings.default_target == "youtube" and settings.confirm_before_post is False
    seen: list[str] = []
    modes = {"mode": "signed_in"}

    def youtube_factory(browser_settings, video_id):
        assert browser_settings.headless is True
        return make_driver(modes["mode"], seen, video_id)

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
        yield base, http, db_path, seen, modes
    finally:
        services.jobs.shutdown(timeout=15)
        http.close()
        server.stop()


def add_approved_draft(db_path: Path, video_id: str, body: str, disclosed: bool = True) -> int:
    now = "2026-11-17T03:00:00+00:00"
    with db.session(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
            "VALUES (?, ?, ?, 'search')", (video_id, f"가짜 영상 {video_id}", now))
        cur = conn.execute(
            "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
            "updated_at, approved_at, disclosed) VALUES (?, ?, '{}', 1, 'approved', ?, ?, ?, ?)",
            (video_id, body, now, now, now, int(disclosed)))
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


@pytest.mark.parametrize("target", ["youtube", "assist", "youtube_auto"])
def test_api_real_posting_on_any_video(live_app, target):
    _, http, db_path, seen, _ = live_app
    body = "[광고] 요즘 운명원 연애 사주 잘 본다던데 저도 언젠가 한번 가 보고 싶어요."
    draft_id = add_approved_draft(db_path, VID, body)
    res = http.post("/api/jobs", json={"video_id": VID, "draft_id": draft_id, "target": target})
    assert res.status_code == 200, res.text
    job = wait_job(http, res.json()["id"], "posted")
    assert job["state"] == "posted" and job["verified"] is True, job
    assert job["mode"] == "youtube" and job["target"] == "youtube"
    assert "awaiting_approval" not in [e["state"] for e in job["events"]]  # 한 번에 끝까지
    assert job["view_url"] == WATCH + VID
    assert seen and all(u.startswith(WATCH + VID) for u in seen)


def test_api_real_posting_without_label_and_signed_out_profile(live_app):
    _, http, db_path, seen, modes = live_app
    body = "요즘 운명원 연애 사주 잘 본다던데 저도 언젠가 한번 가 보고 싶어요."
    draft_id = add_approved_draft(db_path, VID, body, disclosed=False)
    job = http.post("/api/jobs", json={"video_id": VID, "draft_id": draft_id,
                                       "target": "youtube", "profile": "유튜브1"}).json()
    job = wait_job(http, job["id"], "posted")
    assert job["state"] == "posted" and job["disclosed"] is False
    rec = next(r for r in http.get("/api/records").json()["items"] if r["action"] == "post")
    assert rec["disclosed"] is False
    # 로그인 안 된 프로필: 실행기가 보고 실패 + 프로필 로그인 상태를 고쳐 둔다
    modes["mode"] = "signed_out"
    other = add_approved_draft(db_path, OTHER, "[광고] " + body)
    job = http.post("/api/jobs", json={"video_id": OTHER, "draft_id": other,
                                       "target": "youtube", "profile": "유튜브2"}).json()
    job = wait_job(http, job["id"], "failed")
    assert job["state"] == "failed" and job["reason"] == TEXT_NOT_SIGNED_IN
    assert job["has_screenshot"] is True
    # 바로 다시 그 프로필로 하면 시작 전에 막는다(「로그인하기」 안내)
    res = http.post("/api/jobs", json={"video_id": OTHER, "draft_id": other,
                                       "target": "youtube", "profile": "유튜브2"})
    assert res.status_code == 409 and res.json()["error"]["kind"] == "profile_not_signed_in"
