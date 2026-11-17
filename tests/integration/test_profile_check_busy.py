"""로그인 확인이 겹칠 때(로그인 확인 문구 고침, 2026-11-17).

대표가 본 일: 로그인 창을 닫자 서버가 저절로 확인을 돌리는 동안 [로그인 확인]을 누르니
게시 작업이 없는데도 「게시 중이라 …」가 떴다.

- 저절로 도는 확인 중에는 `GET /api/profiles`가 `login_checking`·`login_checking_auto`를 알려 준다.
- 같은 프로필의 [로그인 확인]은 오류 대신 그 결과를 기다려 돌려준다(확인은 한 번만 돈다).
- 다른 프로필의 [로그인 확인]은 앞의 확인이 끝나기를 기다렸다가 돈다.
- 「게시 중」 문구는 게시 작업이 정말 돌 때만. 다른 확인 중·프로그램을 닫는 중은 다른 문구.
- 가짜 실행기·가짜 확인기만 쓴다(실제 크롬·유튜브 없음).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.browser.hooks import BrowserHooks
from app.browser.login import LoginResult
from app.browser.screens import Monitor
from app.errors import AppError

CHROME = Path("C:/Fake/Chrome/chrome.exe")


class FakeProc:
    def __init__(self) -> None:
        self._closed = threading.Event()

    def poll(self):
        return 0 if self._closed.is_set() else None

    def wait(self, timeout=None):
        self._closed.wait(timeout)
        return 0

    def close(self) -> None:
        self._closed.set()


class GatedChecker:
    """확인기 흉내. `gate`가 열릴 때까지 멈춰 있다(확인이 오래 걸리는 상황)."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.started = threading.Event()
        self.calls: list[str] = []
        self.procs: list[FakeProc] = []

    def launcher(self, args):
        proc = FakeProc()
        self.procs.append(proc)
        return proc

    def checker(self, path: Path) -> LoginResult:
        self.calls.append(Path(path).name)
        self.started.set()
        assert self.gate.wait(10), "시험이 확인기를 풀어 주지 않았다"
        return LoginResult("signed_in", f"채널 {Path(path).name}")


@pytest.fixture
def gated():
    g = GatedChecker()
    yield g
    g.gate.set()


@pytest.fixture
def client(make_client, gated):
    hooks = BrowserHooks(
        chrome_finder=lambda: CHROME, playwright_ready=lambda: True, launcher=gated.launcher,
        login_checker=gated.checker, screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)],
    )
    return make_client(key=None, browser_hooks=hooks)


def items(client) -> dict:
    return {p["name"]: p for p in client.get("/api/profiles").json()["items"]}


def start_auto_check(client, gated) -> None:
    """[로그인하기] → 사람이 창을 닫음 → 서버가 저절로 확인을 시작(확인기에서 멈춤)."""
    assert client.post("/api/profiles/유튜브1/login").status_code == 200
    gated.procs[0].close()
    assert gated.started.wait(10), "창을 닫은 뒤 자동 확인이 시작되지 않았다"


def post_in_thread(client, url: str) -> tuple[threading.Thread, dict]:
    out: dict = {}

    def run() -> None:
        res = client.post(url)
        out["status"] = res.status_code
        out["body"] = res.json()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, out


def test_auto_check_is_shown_while_it_runs(client, gated):
    start_auto_check(client, gated)
    one = items(client)["유튜브1"]
    assert one["login_checking"] is True and one["login_checking_auto"] is True
    assert one["login_window_open"] is False
    assert items(client)["유튜브2"]["login_checking"] is False
    browser = client.get("/api/status").json()["browser"]["profiles"][0]
    assert browser["login_checking"] is True  # 아래 줄·③칸이 읽는 곳에도
    gated.gate.set()
    for _ in range(100):
        one = items(client)["유튜브1"]
        if not one["login_checking"]:
            break
        threading.Event().wait(0.05)
    assert one["login_checking"] is False and one["login_checking_auto"] is False
    assert one["signed_in"] is True


def test_check_during_auto_check_waits_for_its_result(client, gated):
    start_auto_check(client, gated)
    t, out = post_in_thread(client, "/api/profiles/유튜브1/check")
    t.join(0.5)
    assert t.is_alive(), "오류로 바로 끝나지 않고 앞의 확인을 기다려야 한다"
    gated.gate.set()
    t.join(10)
    assert out["status"] == 200, out
    body = out["body"]
    assert body["signed_in"] is True and "로그인돼 있습니다" in body["message"]
    assert "게시" not in body["message"]
    assert gated.calls == ["profile-1"]  # 확인은 한 번만 돌았다


def test_other_profile_check_waits_then_runs(client, gated):
    start_auto_check(client, gated)
    t, out = post_in_thread(client, "/api/profiles/유튜브2/check")
    t.join(0.5)
    assert t.is_alive()
    gated.gate.set()
    t.join(10)
    assert out["status"] == 200, out
    assert out["body"]["name"] == "유튜브2" and out["body"]["signed_in"] is True
    assert gated.calls == ["profile-1", "profile-2"]


def test_busy_wording_when_another_check_holds_the_worker(client):
    services = client.app.state.services.get()
    jobs = services.jobs
    jobs._task = object()  # 다른 곳에서 시작한 짧은 일이 작업 스레드를 쓰는 중
    try:
        with pytest.raises(AppError) as exc:
            jobs.run_task(lambda: 1)
        assert str(exc.value.kind) == "profile_check_busy"
        assert "게시" not in exc.value.message and "로그인 확인" in exc.value.message
        res = client.post("/api/profiles/유튜브1/check")
        assert res.status_code == 409
        err = res.json()["error"]
        assert err["kind"] == "profile_check_busy"
        assert "게시" not in err["message"] + err["action"]
    finally:
        jobs._task = None


def test_posting_job_keeps_the_posting_wording(client, gated):
    jobs = client.app.state.services.get().jobs

    class Running:
        finished = False
        id = "x"

    jobs._active = Running()
    try:
        res = client.post("/api/profiles/유튜브1/check")
        assert res.status_code == 409
        err = res.json()["error"]
        assert err["kind"] == "profile_check_busy"
        assert err["message"] == "게시 중이라 지금은 로그인을 확인할 수 없습니다."
        assert "게시가 끝난 뒤" in err["action"]
        assert gated.calls == []
    finally:
        jobs._active = None


def test_closing_program_has_its_own_wording(client):
    jobs = client.app.state.services.get().jobs
    jobs._closed = True
    try:
        with pytest.raises(AppError) as exc:
            jobs.run_task(lambda: 1)
        assert str(exc.value.kind) == "profile_check_busy"
        assert "닫는 중" in exc.value.message and "게시" not in exc.value.message
    finally:
        jobs._closed = False
