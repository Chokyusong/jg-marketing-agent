"""R2 프로필 로그인 API: 로그인 창 실행 인자(가짜 실행기), 로그인 확인(가짜 확인기),
프로필 사용 중, 게시 중 거절, 창을 닫으면 자동 확인. 실제 크롬·유튜브는 쓰지 않는다."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.browser import login as login_mod
from app.browser.hooks import BrowserHooks
from app.browser.login import HOME_URL, LOGIN_URL, LoginResult
from app.browser.screens import Monitor

CHROME = Path("C:/Fake/Chrome/chrome.exe")
AUTOMATION_FLAGS = ("--remote-debugging", "--enable-automation", "--headless",
                    "--disable-blink-features", "--load-extension")


class FakeProc:
    """크롬 프로세스 흉내. close()를 부르면 사람이 창을 닫은 것."""

    def __init__(self) -> None:
        self._closed = threading.Event()

    def poll(self):
        return 0 if self._closed.is_set() else None

    def wait(self, timeout=None):
        self._closed.wait(timeout)
        return 0

    def close(self) -> None:
        self._closed.set()


class Recorder:
    def __init__(self, results=None):
        self.launches: list[list[str]] = []
        self.procs: list[FakeProc] = []
        self.checked: list[Path] = []
        self.results = list(results or [LoginResult("signed_in", "테스트 채널")])
        self.thread_names: list[str] = []
        self.done = threading.Event()

    def launcher(self, args):
        assert isinstance(args, list)  # 셸 문자열이 아니라 인자 목록
        self.launches.append(list(args))
        proc = FakeProc()
        self.procs.append(proc)
        return proc

    def checker(self, path: Path) -> LoginResult:
        self.checked.append(Path(path))
        self.thread_names.append(threading.current_thread().name)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        self.done.set()
        return result


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def client(make_client, rec):
    hooks = BrowserHooks(
        chrome_finder=lambda: CHROME, playwright_ready=lambda: True, launcher=rec.launcher,
        login_checker=rec.checker, screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)],
    )
    return make_client(key=None, browser_hooks=hooks)


def test_login_opens_plain_chrome_with_profile_folder_and_login_url(client, rec, tmp_path):
    res = client.post("/api/profiles/유튜브1/login")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["login_window_open"] is True
    assert "크롬 창을 닫은 다음 [로그인 확인]" in data["message"]
    args = rec.launches[0]
    assert args[0] == str(CHROME)
    assert f"--user-data-dir={tmp_path / 'profiles' / 'profile-1'}" in args
    assert args[-1] == LOGIN_URL and LOGIN_URL.startswith("https://accounts.google.com/")
    # 2026-11-17 창 위치 자동: 모니터가 하나면 왼쪽 60% 안(③칸이 보이게), 크기도 함께 넘긴다
    assert "--window-position=8,8" in args and "--window-size=1144,900" in args
    for flag in AUTOMATION_FLAGS:
        assert not any(a.startswith(flag) for a in args), flag
    assert (tmp_path / "profiles" / "profile-1").is_dir()
    # 프로그램은 아이디·비밀번호를 받지 않는다(요청 본문 없음, 응답에도 없음)
    assert "password" not in res.text.lower() and "@" not in res.text


def test_popen_launcher_uses_no_shell(monkeypatch):
    from app.browser import chrome

    seen = {}

    def fake_popen(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return FakeProc()

    monkeypatch.setattr(chrome.subprocess, "Popen", fake_popen)
    chrome.popen_launcher([str(CHROME), LOGIN_URL])
    assert isinstance(seen["args"], list) and seen["kwargs"]["shell"] is False


def test_open_youtube_opens_home(client, rec):
    res = client.post("/api/profiles/유튜브2/open")
    assert res.status_code == 200
    assert rec.launches[0][-1] == HOME_URL
    assert "--user-data-dir=" in " ".join(rec.launches[0]) and "profile-2" in rec.launches[0][1]


def test_second_window_for_same_profile_is_refused(client, rec):
    assert client.post("/api/profiles/유튜브1/login").status_code == 200
    res = client.post("/api/profiles/유튜브1/login")
    assert res.status_code == 409 and res.json()["error"]["kind"] == "profile_in_use"
    assert "크롬 창을 닫아 주세요" in res.json()["error"]["action"]
    assert len(rec.launches) == 1


def test_check_reads_and_saves_state(client, rec):
    res = client.post("/api/profiles/유튜브1/check")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["signed_in"] is True and data["channel_name"] == "테스트 채널"
    assert data["login_state"] == "signed_in" and data["checked_at"]
    assert "로그인돼 있습니다 · 테스트 채널" == data["message"]
    assert rec.thread_names == ["jg-browser-worker"]  # Playwright 전용 작업 스레드에서
    # 프로필 화면·아래 줄·③칸이 읽는 곳에 남는다
    items = {p["name"]: p for p in client.get("/api/profiles").json()["items"]}
    assert items["유튜브1"]["signed_in"] is True
    assert items["유튜브1"]["channel_name"] == "테스트 채널"
    assert items["유튜브2"]["signed_in"] is None and items["유튜브2"]["checked_at"] is None
    status = {p["name"]: p for p in client.get("/api/status").json()["browser"]["profiles"]}
    assert status["유튜브1"]["signed_in"] is True and status["유튜브1"]["channel_name"]


def test_check_signed_out_and_unknown(make_client):
    rec = Recorder([LoginResult("signed_out"), LoginResult("unknown", "", login_mod.NOTE_UNKNOWN)])
    hooks = BrowserHooks(chrome_finder=lambda: CHROME, playwright_ready=lambda: True,
                         launcher=rec.launcher, login_checker=rec.checker)
    client = make_client(key=None, browser_hooks=hooks)
    out = client.post("/api/profiles/유튜브1/check").json()
    assert out["signed_in"] is False and "[로그인하기]" in out["message"]
    out = client.post("/api/profiles/유튜브1/check").json()
    assert out["signed_in"] is None and out["login_state"] == "unknown"
    assert "로그인 표시를 찾지 못했습니다" in out["message"]


def test_check_refused_while_posting(client, rec):
    services = client.app.state.services.get()
    services.accounts.busy = lambda: True
    res = client.post("/api/profiles/유튜브1/check")
    assert res.status_code == 409
    assert res.json()["error"]["kind"] == "profile_check_busy"
    assert "게시가 끝난 뒤" in res.json()["error"]["action"]
    assert rec.checked == []


def test_worker_refuses_task_while_a_job_runs(client):
    jobs = client.app.state.services.get().jobs

    class Running:
        finished = False
        id = "x"

    jobs._active = Running()
    from app.errors import AppError

    with pytest.raises(AppError) as exc:
        jobs.run_task(lambda: 1)
    assert str(exc.value.kind) == "profile_check_busy"
    assert jobs.busy() is True and jobs.close_if_idle() is False
    jobs._active = None
    assert jobs.run_task(lambda: 41 + 1) == 42


def test_check_refused_when_profile_in_use(client, rec, monkeypatch):
    monkeypatch.setattr(login_mod, "profile_in_use", lambda _p: True)

    def locked(_p):
        from app.errors import AppError, ErrorKind

        raise AppError(ErrorKind.PROFILE_IN_USE)

    monkeypatch.setattr(login_mod, "require_profile_free", locked)
    res = client.post("/api/profiles/유튜브1/check")
    assert res.status_code == 409 and res.json()["error"]["kind"] == "profile_in_use"
    assert rec.checked == []
    res = client.post("/api/profiles/유튜브1/login")
    assert res.status_code == 409 and rec.launches == []


def test_check_refused_while_own_login_window_is_open(client, rec):
    client.post("/api/profiles/유튜브1/login")
    res = client.post("/api/profiles/유튜브1/check")
    assert res.status_code == 409 and res.json()["error"]["kind"] == "profile_in_use"


def test_closing_login_window_checks_once_by_itself(client, rec):
    client.post("/api/profiles/유튜브1/login")
    assert client.get("/api/profiles").json()["items"][0]["login_window_open"] is True
    rec.procs[0].close()  # 사람이 로그인을 마치고 창을 닫았다
    assert rec.done.wait(10), "창을 닫은 뒤 자동 확인이 돌지 않았다"
    for _ in range(50):
        item = client.get("/api/profiles").json()["items"][0]
        if item["checked_at"]:
            break
        threading.Event().wait(0.1)
    assert item["login_window_open"] is False and item["signed_in"] is True
    assert len(rec.checked) == 1


def test_login_window_survives_settings_save(client, rec):
    client.post("/api/profiles/유튜브1/login")
    client.put("/api/settings", json={"values": {"discover.max_results": 30}})
    item = client.get("/api/profiles").json()["items"][0]
    assert item["login_window_open"] is True  # 서비스를 다시 만들어도 창 목록은 그대로
    rec.procs[0].close()
    assert rec.done.wait(10)


def test_unknown_profile(client):
    res = client.post("/api/profiles/없는이름/login")
    assert res.status_code == 422 and res.json()["error"]["kind"] == "profile_unknown"


def test_no_chrome(make_client, rec):
    hooks = BrowserHooks(chrome_finder=lambda: None, launcher=rec.launcher,
                         login_checker=rec.checker, playwright_ready=lambda: True)
    client = make_client(key=None, browser_hooks=hooks)
    res = client.post("/api/profiles/유튜브1/login")
    assert res.status_code == 503 and res.json()["error"]["kind"] == "chrome_not_found"
    assert client.post("/api/profiles/유튜브1/check").status_code == 503


def test_open_window_only_opens_known_addresses(client):
    accounts = client.app.state.services.get().accounts
    with pytest.raises(ValueError):
        accounts.open_window("유튜브1", url="https://example.com/")
