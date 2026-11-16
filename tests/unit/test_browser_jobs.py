"""게시 작업 서비스(8단계): 상태 전이 · 승인 없이는 게시 안 함 · 시간 초과 · 취소 · 한 번에 하나 ·
실패하면 mark_failed와 기록 · 성공하면 mark_posted.

브라우저는 띄우지 않는다. 테스트 페이지 실행기(`BrowserDriver`)를 가짜로, assist의 크롬 실행 함수를
가짜로 바꾼다. 네트워크·크롬·Playwright 없이 돈다.
"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app import db
from app.browser import jobs as jobs_mod
from app.browser.jobs import (
    NOTE_UNVERIFIED,
    REASON_APPROVAL_TIMEOUT,
    REASON_CANCELLED,
    REASON_CONFIRM_TIMEOUT,
    REASON_NOT_POSTED,
    REASON_STALE,
    JobService,
    mode_of,
    sandbox_url,
)
from app.browser.sandbox_driver import DriverError, Stopped
from app.config import BrowserSettings
from app.errors import AppError
from app.ops.profiles import ProfileService
from app.ops.rules import PostRules

PROFILES = ("유튜브1", "유튜브2", "유튜브3")
BASE = "http://127.0.0.1:8765"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def vid(n: int) -> str:
    return f"VID{n:08d}"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


class FakeDriver:
    """테스트 페이지 실행기 대신. 부른 순서를 남기고, 정한 단계에서 실패하거나 멈춘다."""

    def __init__(self, *, fail_on: str = "", hold_typing: threading.Event | None = None):
        self.fail_on = fail_on
        self.hold_typing = hold_typing
        self.calls: list[str] = []
        self.typed: list[str] = []
        self.opened: list[tuple[Path, str]] = []
        self.visited: list[str] = []
        self.closed = False
        self.thread_names: set[str] = set()

    def _step(self, name: str) -> None:
        self.calls.append(name)
        self.thread_names.add(threading.current_thread().name)
        if self.fail_on == name:
            raise DriverError(f"가짜 실패: {name}")

    def open(self, user_data_dir: Path, url: str) -> None:
        self.opened.append((user_data_dir, url))
        self.visited.append(url)
        self._step("open")

    def type_comment(self, text, delay_ms, should_stop) -> None:
        self._step("type")
        for ch in text:
            if self.hold_typing is not None:
                while not self.hold_typing.is_set():
                    if should_stop():
                        raise Stopped
                    time.sleep(0.01)
            if should_stop():
                raise Stopped
            self.typed.append(ch)

    def click_post(self) -> None:
        self._step("click")

    def verify_posted(self, text: str) -> None:
        self._step("verify")

    def screenshot(self, path: Path) -> bool:
        self.calls.append("screenshot")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(PNG)
        return True

    def close(self) -> None:
        self.calls.append("close")
        self.closed = True


class FakeProc:
    def __init__(self, args):
        self.args = list(args)
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def path(tmp_db_path):
    db.init_db(tmp_db_path)
    return tmp_db_path


def add_draft(path, video_id: str, *, status: str = "approved") -> tuple[int, str]:
    now = "2026-11-16T03:00:00+00:00"
    body = f"[광고] {video_id} 영상의 첫 장면 이야기에 공감해요. 운명원에 상담해 보세요."
    with db.session(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
            "VALUES (?, ?, ?, 'search')",
            (video_id, f"영상 {video_id}", now),
        )
        cur = conn.execute(
            "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
            "updated_at, approved_at) VALUES (?, ?, '{}', 1, ?, ?, ?, ?)",
            (video_id, body, status, now, now, now),
        )
        return int(cur.lastrowid), body


class Env:
    def __init__(self, path, tmp_path, clock, **kw):
        self.path = path
        self.clock = clock
        self.drivers: list[FakeDriver] = []
        self.procs: list[FakeProc] = []
        self.driver_kw = kw.pop("driver_kw", {})
        limit = kw.pop("limit", 10)
        self.rules = PostRules(path, daily_limit=limit, profiles=PROFILES, clock=clock)
        self.chrome = tmp_path / "chrome.exe"
        self.chrome.write_bytes(b"")
        self.browser = BrowserSettings(
            headless=True,
            window_position=(60, -1060),
            typing_delay_ms=(0, 0),
            profiles_root=tmp_path / "profiles",
            screenshot_dir=tmp_path / "shots",
        )
        defaults = dict(
            db_path=path,
            rules=self.rules,
            profiles=ProfileService(PROFILES, db_path=path),
            browser=self.browser,
            chrome_finder=lambda: self.chrome,
            driver_factory=self._driver,
            launcher=self._launch,
            playwright_ready=lambda: True,
            clock=clock,
            approval_timeout=5.0,
            confirm_timeout=5.0,
        )
        defaults.update(kw)
        self.jobs = JobService(**defaults)

    def _driver(self, settings):
        d = FakeDriver(**self.driver_kw)
        self.drivers.append(d)
        return d

    def _launch(self, args):
        p = FakeProc(args)
        self.procs.append(p)
        return p

    def start(self, n=1, *, target="sandbox", profile=None, **kw):
        draft_id, body = add_draft(self.path, vid(n))
        job_id = self.jobs.start(vid(n), draft_id, profile, target, base_url=BASE, **kw)
        return job_id, draft_id, body

    def post_rows(self):
        with db.session(self.path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM posts ORDER BY id")]

    def run_rows(self):
        with db.session(self.path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY id")]


@pytest.fixture
def env(path, tmp_path, clock):
    made: list[Env] = []

    def _make(**kw) -> Env:
        e = Env(path, tmp_path, clock, **kw)
        made.append(e)
        return e

    yield _make
    for e in made:
        e.jobs.shutdown(timeout=5)


def states(view) -> list[str]:
    out: list[str] = []
    for e in view.events:
        if not out or out[-1] != e.state:
            out.append(e.state)
    return out


# ---------------------------------------------------------------- 성공과 상태 전이


def test_sandbox_success_walks_every_state_and_marks_posted(env):
    e = env()
    job_id, draft_id, body = e.start(1)
    view = e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    assert view.state == "awaiting_approval" and view.waiting_for == "approve"
    assert view.seconds_left is not None and view.step == 3
    e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "posted" and view.finished and view.verified is True
    assert states(view) == [
        "queued", "launching", "typing", "awaiting_approval", "posting", "verifying", "posted"
    ]
    assert view.step == 6
    driver = e.drivers[0]
    assert driver.calls == ["open", "type", "click", "verify", "close"]
    assert "".join(driver.typed) == body  # 한 글자씩 넣은 글이 승인한 초안과 같다
    assert driver.thread_names == {"jg-browser-worker"}  # 전용 작업 스레드에서만
    # 여는 주소는 이 앱의 테스트 페이지뿐
    (profile_path, url), = driver.opened
    assert url.startswith(f"{BASE}/sandbox/watch?v={vid(1)}")
    assert profile_path.name == "profile-1" and profile_path.is_dir()
    # 게시 완료 + 작업 기록 한 줄(같은 결과가 두 줄 생기지 않는다)
    posts = e.post_rows()
    assert [(p["status"], p["video_id"]) for p in posts] == [("posted", vid(1))]
    post_runs = [r for r in e.run_rows() if r["action"] == "post"]
    assert len(post_runs) == 1
    assert post_runs[0]["result"] == "success" and post_runs[0]["job_id"] == job_id
    assert post_runs[0]["comment_text"] == body and post_runs[0]["profile"] == "유튜브1"
    # 상태가 바뀔 때마다 job_events에 남는다
    db_states = [ev.state for ev in e.jobs.events_in_db(job_id)]
    assert db_states[0] == "queued" and db_states[-1] == "posted"
    assert {"launching", "typing", "awaiting_approval", "posting", "verifying"} <= set(db_states)
    assert view.view_url == f"{BASE}/sandbox/watch?v={vid(1)}&profile=%EC%9C%A0%ED%8A%9C%EB%B8%8C1"


def test_no_click_without_approval(env):
    e = env()
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    time.sleep(0.4)  # 기다려도 승인 없이는 게시 단계로 가지 않는다
    view = e.jobs.get(job_id)
    assert view.state == "awaiting_approval"
    assert "click" not in e.drivers[0].calls
    assert e.post_rows()[0]["status"] == "reserved"


def test_approve_is_refused_before_typing_finishes(env):
    hold = threading.Event()
    e = env(driver_kw={"hold_typing": hold})
    job_id, *_ = e.start(1)
    assert e.jobs.wait_for_state(job_id, "typing", 5).state == "typing"
    with pytest.raises(AppError) as exc:
        e.jobs.approve(job_id)
    assert str(exc.value.kind) == "job_wrong_state"
    hold.set()
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    time.sleep(0.2)
    assert "click" not in e.drivers[0].calls  # 앞서 거절된 승인은 남지 않는다
    e.jobs.approve(job_id)
    assert e.jobs.wait(job_id, 5).state == "posted"


def test_approval_timeout_fails_with_screenshot_and_record(env):
    e = env(approval_timeout=0.2)
    job_id, *_ = e.start(1)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_APPROVAL_TIMEOUT
    assert view.step == 3  # 승인 대기 칸에서 실패
    assert "click" not in e.drivers[0].calls and e.drivers[0].closed
    assert view.has_screenshot
    shot = e.jobs.screenshot_path(job_id)
    assert shot.name == f"{job_id}.png" and shot.read_bytes().startswith(b"\x89PNG")
    post = e.post_rows()[0]
    assert post["status"] == "failed" and post["reason"] == REASON_APPROVAL_TIMEOUT
    (run,) = [r for r in e.run_rows() if r["action"] == "post"]
    assert run["result"] == "failure" and run["reason"] == REASON_APPROVAL_TIMEOUT
    assert run["screenshot_path"].endswith(f"{job_id}.png")


def test_approval_timeout_default_is_five_minutes_and_confirm_ten():
    assert jobs_mod.APPROVAL_TIMEOUT_SECONDS == 300
    assert jobs_mod.CONFIRM_TIMEOUT_SECONDS == 600


@pytest.mark.parametrize("step", ["open", "type", "click", "verify"])
def test_driver_failure_marks_failed(env, step):
    e = env(driver_kw={"fail_on": step})
    job_id, *_ = e.start(1)
    if step in ("click", "verify"):
        e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
        e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == f"가짜 실패: {step}"
    assert e.post_rows()[0]["status"] == "failed"
    assert [r["result"] for r in e.run_rows() if r["action"] == "post"] == ["failure"]
    assert view.has_screenshot  # 실패하면 화면 캡처
    assert e.drivers[0].closed
    assert view.step == {"open": 1, "type": 2, "click": 4, "verify": 5}[step]


def test_failed_video_can_be_tried_again(env):
    e = env(driver_kw={"fail_on": "open"})
    job_id, draft_id, _ = e.start(1)
    assert e.jobs.wait(job_id, 5).state == "failed"
    e.driver_kw = {}
    again = e.jobs.start(vid(1), draft_id, None, "sandbox", base_url=BASE)
    e.jobs.wait_for_state(again, "awaiting_approval", 5)
    e.jobs.approve(again)
    assert e.jobs.wait(again, 5).state == "posted"
    assert e.post_rows()[0]["attempts"] == 2


# ---------------------------------------------------------------- 취소

def test_cancel_while_waiting_for_approval(env):
    e = env()
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e.jobs.cancel(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_CANCELLED
    assert "click" not in e.drivers[0].calls and e.drivers[0].closed
    assert e.post_rows()[0]["status"] == "failed"
    with pytest.raises(AppError) as exc:
        e.jobs.cancel(job_id)  # 끝난 작업은 취소할 수 없다
    assert str(exc.value.kind) == "job_wrong_state"


def test_cancel_while_typing_stops_between_letters(env):
    hold = threading.Event()
    e = env(driver_kw={"hold_typing": hold})
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "typing", 5)
    e.jobs.cancel(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_CANCELLED
    assert e.drivers[0].typed == [] and e.drivers[0].closed


# ---------------------------------------------------------------- 한 번에 하나 · 규칙


def test_only_one_job_at_a_time(env):
    e = env()
    first, *_ = e.start(1)
    e.jobs.wait_for_state(first, "awaiting_approval", 5)
    with pytest.raises(AppError) as exc:
        e.start(2)
    assert str(exc.value.kind) == "job_busy" and exc.value.extra["job_id"] == first
    assert len(e.post_rows()) == 1  # 거절된 시작은 예약을 남기지 않는다
    e.jobs.approve(first)
    e.jobs.wait(first, 5)
    second, *_ = e.start(2)  # 끝나면 다음 작업을 받는다
    assert e.jobs.active_id() == second


def test_same_video_twice_is_refused_after_posting(env):
    e = env()
    job_id, draft_id, _ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e.jobs.approve(job_id)
    e.jobs.wait(job_id, 5)
    with pytest.raises(AppError) as exc:
        e.jobs.start(vid(1), draft_id, "유튜브2", "sandbox", base_url=BASE)
    assert str(exc.value.kind) == "already_commented"
    assert len(e.drivers) == 1


def test_daily_limit_blocks_next_job(env):
    e = env(limit=1)
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e.jobs.approve(job_id)
    e.jobs.wait(job_id, 5)
    with pytest.raises(AppError) as exc:
        e.start(2)
    assert str(exc.value.kind) == "daily_limit_reached"


def test_unapproved_draft_is_refused_and_leaves_nothing(env, path):
    e = env()
    draft_id, _ = add_draft(path, vid(1), status="draft")
    with pytest.raises(AppError) as exc:
        e.jobs.start(vid(1), draft_id, None, "sandbox", base_url=BASE)
    assert str(exc.value.kind) == "draft_not_approved"
    assert e.post_rows() == [] and e.drivers == [] and e.jobs.active_id() is None
    with db.session(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM job_events").fetchone()[0] == 0


def test_missing_chrome_or_playwright_is_refused_before_reserving(env):
    e = env(chrome_finder=lambda: None)
    with pytest.raises(AppError) as exc:
        e.start(1)
    assert str(exc.value.kind) == "chrome_not_found"
    e2 = env(playwright_ready=lambda: False)
    with pytest.raises(AppError) as exc:
        e2.start(2)
    assert str(exc.value.kind) == "playwright_missing"
    assert e2.post_rows() == []
    # assist는 Playwright가 없어도 된다(크롬을 열기만 한다)
    job_id, *_ = e2.start(3, target="assist")
    assert e2.jobs.wait_for_state(job_id, "awaiting_confirm", 5).state == "awaiting_confirm"


def test_profile_in_use_is_reported(env, monkeypatch):
    e = env()

    def busy(path):
        raise AppError("profile_in_use", detail=Path(path).name)

    monkeypatch.setattr(jobs_mod, "require_profile_free", busy)
    with pytest.raises(AppError) as exc:
        e.start(1)
    assert str(exc.value.kind) == "profile_in_use"
    assert "크롬 창을 닫아 주세요" in exc.value.action
    assert e.post_rows() == []


def test_profile_choice_and_auto_rotation(env):
    e = env()
    a, *_ = e.start(1, profile="유튜브3")
    assert e.jobs.get(a).profile == "유튜브3" and e.jobs.get(a).folder == "profile-3"
    e.jobs.cancel(a)
    e.jobs.wait(a, 5)
    b, *_ = e.start(2)  # 자동 배정: 안 쓴 프로필이 먼저
    assert e.jobs.get(b).profile == "유튜브1"


def test_unknown_job_and_bad_ids(env):
    e = env()
    for bad in ("nope", "../../etc", ""):
        with pytest.raises(AppError) as exc:
            e.jobs.get(bad)
        assert str(exc.value.kind) == "job_not_found"


# ---------------------------------------------------------------- assist(실제 유튜브): 열기만


def test_assist_only_launches_chrome_with_profile_position_and_url(env):
    def no_driver(settings):
        raise AssertionError("assist에서 테스트 페이지 실행기(Playwright)를 쓰면 안 된다")

    e = env(driver_factory=no_driver)
    job_id, *_ = e.start(1, target="assist")
    view = e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    assert view.mode == "assist" and view.target == "youtube" and view.waiting_for == "confirm"
    (proc,) = e.procs
    folder = e.browser.profiles_root / "profile-1"
    assert proc.args == [
        str(e.chrome),
        f"--user-data-dir={folder}",
        "--window-position=60,-1060",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        f"https://www.youtube.com/watch?v={vid(1)}",
    ]
    assert not any("remote-debugging" in a or "automation" in a for a in proc.args)
    with pytest.raises(AppError) as exc:
        e.jobs.approve(job_id)  # assist에는 자동 게시 승인이 없다
    assert str(exc.value.kind) == "job_wrong_state"


def test_assist_posted_without_key_is_unverified(env):
    e = env(verify_comment=lambda v, t: None)
    job_id, _, body = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.confirm(job_id, True)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "posted" and view.verified is False
    assert view.message.startswith(NOTE_UNVERIFIED)
    (run,) = [r for r in e.run_rows() if r["action"] == "post"]
    assert run["result"] == "success" and run["reason"] == NOTE_UNVERIFIED
    assert run["target"] == "youtube" and run["comment_text"] == body
    assert view.view_url == f"https://www.youtube.com/watch?v={vid(1)}"
    assert e.procs[0].terminated is False  # 사람이 쓰는 크롬은 닫지 않는다


def test_assist_posted_and_found_by_api(env):
    seen = []

    def found(video_id, text):
        seen.append((video_id, text))
        return True

    e = env(verify_comment=found)
    job_id, _, body = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.confirm(job_id, True)
    view = e.jobs.wait(job_id, 5)
    assert view.verified is True and seen == [(vid(1), body)]


def test_assist_verify_error_still_counts_as_posted(env):
    def broken(video_id, text):
        raise AppError("network")

    e = env(verify_comment=broken)
    job_id, *_ = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.confirm(job_id, True)
    assert e.jobs.wait(job_id, 5).verified is False


def test_assist_not_posted(env):
    e = env()
    job_id, *_ = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.confirm(job_id, False)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_NOT_POSTED
    assert not view.has_screenshot  # 실제 유튜브 화면은 찍지 않는다
    assert e.post_rows()[0]["status"] == "failed"


def test_assist_confirm_timeout(env):
    e = env(confirm_timeout=0.2)
    job_id, *_ = e.start(1, target="assist")
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_CONFIRM_TIMEOUT


def test_assist_cancel_closes_the_chrome_we_opened(env):
    e = env()
    job_id, *_ = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.cancel(job_id)
    assert e.jobs.wait(job_id, 5).reason == REASON_CANCELLED
    assert e.procs[0].terminated is True


def test_confirm_is_only_for_assist(env):
    e = env()
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    with pytest.raises(AppError) as exc:
        e.jobs.confirm(job_id, True)
    assert str(exc.value.kind) == "job_wrong_state"


# ---------------------------------------------------------------- 닫기 · 남은 예약


def test_shutdown_cancels_active_job_and_stops_worker(env):
    e = env()
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    assert e.jobs.shutdown(timeout=5) is True
    view = e.jobs.get(job_id)
    assert view.state == "failed" and view.reason == REASON_CANCELLED
    assert e.drivers[0].closed
    assert not [t for t in threading.enumerate() if t is e.jobs._worker and t.is_alive()]
    with pytest.raises(AppError):
        e.start(2)  # 닫은 뒤에는 새 작업을 받지 않는다


def test_shutdown_closes_assist_chrome(env):
    e = env()
    job_id, *_ = e.start(1, target="assist")
    e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    e.jobs.shutdown(timeout=5)
    assert e.procs[0].terminated is True


def test_stale_reservation_is_released(env, path, clock):
    e = env()
    draft_id, _ = add_draft(path, vid(9))
    post_id = e.rules.reserve(vid(9), "sandbox", "유튜브1", draft_id)
    assert e.jobs.recover_stale() == 0  # 방금 한 예약은 그대로
    clock.advance(minutes=16)
    assert e.jobs.recover_stale() == 1
    post = e.rules.get(post_id)
    assert post.status == "failed" and post.reason == REASON_STALE


# ---------------------------------------------------------------- 주소 규칙


def test_mode_names():
    assert mode_of("sandbox") == ("sandbox", "sandbox")
    assert mode_of("assist") == ("assist", "youtube") == mode_of("youtube")
    with pytest.raises(ValueError):
        mode_of("auto")


def test_sandbox_url_is_local_only():
    url = sandbox_url("http://127.0.0.1:8765/", vid(1), "유튜브1", "hide_button")
    assert url.startswith("http://127.0.0.1:8765/sandbox/watch?v=")
    assert url.endswith("&fail=hide_button")
    for bad in ("https://www.youtube.com", "http://example.com:80", "http://testserver"):
        with pytest.raises(ValueError):
            sandbox_url(bad, vid(1), "유튜브1")


def test_job_settings_are_frozen_copies():
    settings = BrowserSettings()
    assert replace(settings, headless=True).headless is True
    assert settings.window_position == (60, -1060)


@pytest.mark.parametrize("fail_on", ["", "click"])
def test_chrome_is_closed_before_the_job_reports_its_end(env, fail_on):
    """끝(게시 완료·실패)을 알리기 전에 크롬을 닫는다. 바로 다시 시작해도 프로필이 풀려 있다."""
    e = env(driver_kw={"fail_on": fail_on})
    job_id, *_ = e.start(1)
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    driver = e.drivers[0]
    seen: list[str] = []
    real_close = driver.close

    def close():
        seen.append(e.jobs.get(job_id).state)
        real_close()

    driver.close = close
    e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == ("failed" if fail_on else "posted")
    assert seen and seen[0] not in ("posted", "failed")


# ---------------------------------------------------------------- 내 채널 영상 자동 게시(auto)


class OwnEnv(Env):
    """auto 작업용: 내 채널 영상은 vid(1)뿐. YouTube 실행기도 가짜(FakeDriver)."""

    def __init__(self, path, tmp_path, clock, **kw):
        self.youtube_calls: list[str] = []
        kw.setdefault("own_video", lambda v: v == vid(1))
        kw.setdefault("youtube_driver_factory", self._youtube_driver)
        super().__init__(path, tmp_path, clock, **kw)

    def _youtube_driver(self, settings, video_id):
        self.youtube_calls.append(video_id)
        return self._driver(settings)


@pytest.fixture
def own_env(path, tmp_path, clock):
    made: list[OwnEnv] = []

    def _make(**kw) -> OwnEnv:
        e = OwnEnv(path, tmp_path, clock, **kw)
        made.append(e)
        return e

    yield _make
    for e in made:
        e.jobs.shutdown(timeout=5)


def test_mode_name_for_own_video_auto_post():
    assert mode_of("youtube_auto") == ("auto", "youtube")


def test_auto_post_on_own_video_types_waits_for_approval_then_posts(own_env):
    e = own_env()
    job_id, _, body = e.start(1, target="youtube_auto")
    view = e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    assert view.mode == "auto" and view.target == "youtube" and view.waiting_for == "approve"
    driver = e.drivers[0]
    assert "click" not in driver.calls  # 승인 전에는 누르지 않는다
    e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "posted" and view.verified is True
    assert states(view) == [
        "queued", "launching", "typing", "awaiting_approval", "posting", "verifying", "posted"
    ]
    assert driver.calls == ["open", "type", "click", "verify", "close"]
    assert "".join(driver.typed) == body
    assert e.youtube_calls == [vid(1)]  # 실행기는 그 영상 하나만 연다
    (_, url), = driver.opened
    assert url == f"https://www.youtube.com/watch?v={vid(1)}" == view.view_url
    assert [(p["status"], p["target"]) for p in e.post_rows()] == [("posted", "youtube")]


def test_auto_post_is_refused_for_other_videos_and_leaves_nothing(own_env):
    e = own_env()
    with pytest.raises(AppError) as err:
        e.start(2, target="youtube_auto")
    assert err.value.kind.value == "auto_post_own_only"
    assert e.post_rows() == [] and e.drivers == [] and e.procs == []


def test_auto_post_is_refused_when_no_own_videos(env):
    e = env()  # own_video 기본값: 내 채널 영상 없음
    with pytest.raises(AppError) as err:
        e.start(1, target="youtube_auto")
    assert err.value.kind.value == "auto_post_own_only"


def test_auto_post_needs_playwright(own_env):
    e = own_env(playwright_ready=lambda: False)
    with pytest.raises(AppError) as err:
        e.start(1, target="youtube_auto")
    assert err.value.kind.value == "playwright_missing"
    assert e.post_rows() == []


def test_auto_post_verify_miss_is_posted_unverified_not_failed(own_env):
    """「댓글」을 누른 뒤에는 못 찾아도 실패로 되돌리지 않는다(다시 달면 두 번 달린다)."""
    e = own_env(driver_kw={"fail_on": "verify"}, verify_comment=lambda v, t: False)
    job_id, *_ = e.start(1, target="youtube_auto")
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "posted" and view.verified is False
    assert view.message.startswith(NOTE_UNVERIFIED)
    assert e.post_rows()[0]["status"] == "posted"
    (run,) = [r for r in e.run_rows() if r["action"] == "post"]
    assert run["result"] == "success" and run["reason"] == NOTE_UNVERIFIED


def test_auto_post_verify_miss_found_by_data_api(own_env):
    e = own_env(driver_kw={"fail_on": "verify"}, verify_comment=lambda v, t: True)
    job_id, *_ = e.start(1, target="youtube_auto")
    e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "posted" and view.verified is True


@pytest.mark.parametrize("step", ["open", "type", "click"])
def test_auto_post_failure_before_posting_marks_failed(own_env, step):
    e = own_env(driver_kw={"fail_on": step})
    job_id, *_ = e.start(1, target="youtube_auto")
    if step == "click":
        e.jobs.wait_for_state(job_id, "awaiting_approval", 5)
        e.jobs.approve(job_id)
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and "가짜 실패" in view.reason
    assert view.has_screenshot is True  # 실패 화면을 이 PC에만 남긴다
    assert e.post_rows()[0]["status"] == "failed"
    assert e.drivers[0].closed


def test_auto_post_approval_timeout_and_cancel(own_env):
    e = own_env(approval_timeout=0.2)
    job_id, *_ = e.start(1, target="youtube_auto")
    view = e.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_APPROVAL_TIMEOUT
    assert "click" not in e.drivers[0].calls

    e2 = own_env()
    draft_id, _ = add_draft(e2.path, vid(1))
    job_id = e2.jobs.start(vid(1), draft_id, None, "youtube_auto", base_url=BASE)
    e2.jobs.wait_for_state(job_id, "awaiting_approval", 5)
    e2.jobs.cancel(job_id)
    view = e2.jobs.wait(job_id, 5)
    assert view.state == "failed" and view.reason == REASON_CANCELLED
    assert "click" not in e2.drivers[0].calls


def test_auto_mode_does_not_change_assist_for_own_video(own_env):
    """내 채널 영상이라도 assist(수동)로 시작하면 크롬을 열기만 한다."""
    e = own_env()
    job_id, *_ = e.start(1, target="assist")
    view = e.jobs.wait_for_state(job_id, "awaiting_confirm", 5)
    assert view.mode == "assist" and e.youtube_calls == [] and len(e.procs) == 1
    e.jobs.cancel(job_id)
    e.jobs.wait(job_id, 5)
