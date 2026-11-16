"""P단계: 자체 창 프로그램(app/desktop.py).

창은 실제로 띄우지 않는다. 창 여는 함수와 알림 함수만 가짜로 바꾸고,
서버 시작·포트 고르기·준비 대기·종료·중복 실행 감지는 진짜로 돌려 본다.
"""

from __future__ import annotations

import ast
import socket
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app import desktop
from app.config import load_settings
from app.desktop import (
    EXIT_ALREADY_RUNNING,
    EXIT_OK,
    EXIT_START_FAILED,
    EXIT_WINDOW_FAILED,
    TEXT_ALREADY_RUNNING,
    TEXT_NO_WEBVIEW2,
    TEXT_NO_WEBVIEW_LIB,
    TEXT_START_FAILED,
    TEXT_WINDOW_FAILED,
    InstanceLock,
    WebViewUnavailable,
    WindowSpec,
)
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def unique_lock() -> InstanceLock:
    return InstanceLock(f"Local\\JGMarketingAgent.Test.{uuid.uuid4().hex}")


def port_accepts(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def server_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "jg-desktop-server"]


def tiny_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def real_app(tmp_db_path, make_config, clean_env):
    """실제 대시보드 앱(임시 DB, 키 없음)."""
    settings = load_settings(make_config(), env_path=None, db_path=tmp_db_path, environ={})
    return create_app(settings)


class FakeWindow:
    """창 대신 서버를 불러 보고 바로 '닫힌다'."""

    def __init__(self, action=None) -> None:
        self.specs: list[WindowSpec] = []
        self.action = action

    def __call__(self, spec: WindowSpec) -> None:
        self.specs.append(spec)
        if self.action is not None:
            self.action(spec)


# ---------------------------------------------------------------- 포트와 준비 대기


def test_listen_socket_gets_free_local_port():
    first = desktop.open_listen_socket()
    second = desktop.open_listen_socket()
    try:
        host, port = first.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
        assert second.getsockname()[1] != port
    finally:
        first.close()
        second.close()


def test_wait_until_ready_times_out_when_nothing_answers():
    sock = desktop.open_listen_socket()  # 묶었지만 듣지 않는 포트
    try:
        started = time.monotonic()
        ready = desktop.wait_until_ready(
            f"http://127.0.0.1:{sock.getsockname()[1]}", timeout=0.3, interval=0.05
        )
        assert ready is False
        assert time.monotonic() - started < 5
    finally:
        sock.close()


def test_wait_until_ready_stops_early_when_server_died():
    sock = desktop.open_listen_socket()
    try:
        started = time.monotonic()
        ready = desktop.wait_until_ready(
            f"http://127.0.0.1:{sock.getsockname()[1]}", timeout=30, is_alive=lambda: False
        )
        assert ready is False
        assert time.monotonic() - started < 5
    finally:
        sock.close()


# ---------------------------------------------------------------- 정상 실행과 종료


def test_run_opens_window_after_server_is_ready_and_stops_on_close(real_app):
    seen: dict[str, object] = {}

    def look_around(spec: WindowSpec) -> None:
        # 창이 열릴 때는 이미 서버가 답해야 한다(빈 화면 방지).
        with httpx.Client(trust_env=False, timeout=5) as client:
            seen["health"] = client.get(spec.url + "api/health").json()
            page = client.get(spec.url)
            seen["page_status"] = page.status_code
            seen["page_has_title"] = "<html" in page.text.lower()
        seen["port"] = int(spec.url.rsplit(":", 1)[1].strip("/"))

    window = FakeWindow(look_around)
    notes: list[str] = []
    code = desktop.run(
        open_window=window, notify=notes.append, asgi_app=real_app, lock=unique_lock()
    )

    assert code == EXIT_OK
    assert notes == []
    assert seen["health"] == {"status": "ok", "app": "JG Marketing AI Agent", "stage": 1}
    assert seen["page_status"] == 200
    assert seen["page_has_title"] is True

    spec = window.specs[0]
    assert spec.title == "JG Marketing Agent"
    assert (spec.width, spec.height) == (1600, 1000)
    assert spec.min_size == (1100, 720)
    assert (spec.x, spec.y) == (None, None)  # 기본은 화면 가운데
    assert spec.url.startswith("http://127.0.0.1:")

    # 창을 닫으면 서버가 멈추고 포트도 닫힌다.
    assert server_threads() == []
    assert port_accepts(int(seen["port"])) is False


def test_lock_is_released_after_window_closes():
    lock = unique_lock()
    code = desktop.run(
        open_window=FakeWindow(), notify=lambda _: None, asgi_app=tiny_app(), lock=lock
    )
    assert code == EXIT_OK
    again = InstanceLock(lock.name)
    try:
        assert again.acquire() is True
    finally:
        again.release()


def test_window_position_is_passed_through():
    window = FakeWindow()
    desktop.run(
        open_window=window,
        notify=lambda _: None,
        asgi_app=tiny_app(),
        lock=unique_lock(),
        window_pos=(-1860, 60),
    )
    assert (window.specs[0].x, window.specs[0].y) == (-1860, 60)


# ---------------------------------------------------------------- 중복 실행


def test_second_run_is_refused_while_first_window_is_open():
    name = f"Local\\JGMarketingAgent.Test.{uuid.uuid4().hex}"
    window_open = threading.Event()
    close_window = threading.Event()

    def hold_open(_: WindowSpec) -> None:
        window_open.set()
        assert close_window.wait(10)

    results: dict[str, int] = {}
    first = threading.Thread(
        target=lambda: results.setdefault(
            "first",
            desktop.run(
                open_window=FakeWindow(hold_open),
                notify=lambda _: None,
                asgi_app=tiny_app(),
                lock=InstanceLock(name),
            ),
        )
    )
    first.start()
    try:
        assert window_open.wait(10)

        second_window = FakeWindow()
        notes: list[str] = []
        focused: list[bool] = []
        code = desktop.run(
            open_window=second_window,
            notify=notes.append,
            asgi_app=tiny_app(),
            lock=InstanceLock(name),
            on_already_running=lambda: focused.append(True),
        )
        assert code == EXIT_ALREADY_RUNNING
        assert notes == [TEXT_ALREADY_RUNNING]
        assert second_window.specs == []  # 새 창을 열지 않는다
        assert focused == [True]  # 이미 열린 창을 앞으로
    finally:
        close_window.set()
        first.join(15)
    assert results["first"] == EXIT_OK


def test_lock_allows_one_holder_at_a_time():
    name = f"Local\\JGMarketingAgent.Test.{uuid.uuid4().hex}"
    with InstanceLock(name) as first:
        assert first.acquire() is True
        assert InstanceLock(name).acquire() is False
    with InstanceLock(name) as again:
        assert again.acquire() is True


# ---------------------------------------------------------------- 실패할 때


def test_server_start_failure_is_reported_without_window():
    @asynccontextmanager
    async def broken_lifespan(_: FastAPI):
        raise RuntimeError("startup broke")
        yield  # pragma: no cover

    window = FakeWindow()
    notes: list[str] = []
    lock = unique_lock()
    code = desktop.run(
        open_window=window,
        notify=notes.append,
        asgi_app=FastAPI(lifespan=broken_lifespan),
        lock=lock,
        ready_timeout=5,
    )
    assert code == EXIT_START_FAILED
    assert notes == [TEXT_START_FAILED]
    assert window.specs == []
    assert server_threads() == []
    again = InstanceLock(lock.name)
    assert again.acquire() is True
    again.release()


def test_window_error_still_stops_server_and_releases_lock():
    ports: list[int] = []

    def explode(spec: WindowSpec) -> None:
        ports.append(int(spec.url.rsplit(":", 1)[1].strip("/")))
        raise RuntimeError("window broke")

    notes: list[str] = []
    lock = unique_lock()
    code = desktop.run(open_window=explode, notify=notes.append, asgi_app=tiny_app(), lock=lock)
    assert code == EXIT_WINDOW_FAILED
    assert notes == [TEXT_WINDOW_FAILED]
    assert server_threads() == []
    assert port_accepts(ports[0]) is False
    again = InstanceLock(lock.name)
    assert again.acquire() is True
    again.release()


def test_missing_webview2_shows_install_hint():
    def no_runtime(_: WindowSpec) -> None:
        raise WebViewUnavailable(TEXT_NO_WEBVIEW2)

    notes: list[str] = []
    code = desktop.run(
        open_window=no_runtime, notify=notes.append, asgi_app=tiny_app(), lock=unique_lock()
    )
    assert code == EXIT_WINDOW_FAILED
    assert notes == [TEXT_NO_WEBVIEW2]
    assert "WebView2" in TEXT_NO_WEBVIEW2


def test_missing_window_library_raises_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview → ImportError
    with pytest.raises(WebViewUnavailable) as info:
        desktop.open_webview_window(WindowSpec(url="http://127.0.0.1:1/"))
    assert str(info.value) == TEXT_NO_WEBVIEW_LIB
    assert "pip install -r requirements.txt" in TEXT_NO_WEBVIEW_LIB


# ---------------------------------------------------------------- 모듈 모양


def test_window_library_is_not_imported_at_module_level():
    tree = ast.parse((ROOT / "app" / "desktop.py").read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    assert "webview" not in top_level


def test_main_uses_real_window_and_message_box(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr(desktop, "run", lambda **kwargs: captured.update(kwargs) or 0)
    monkeypatch.setenv(desktop.WINDOW_POS_ENV, "")
    assert desktop.main() == 0
    assert captured["open_window"] is desktop.open_webview_window
    assert captured["notify"] is desktop.notify_user
    assert captured["on_already_running"] is desktop.focus_existing_window
    assert captured["window_pos"] == (None, None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", (None, None)),
        ("-1860,60", (-1860, 60)),
        (" 60 , -1060 ", (60, -1060)),
        ("left", (None, None)),
        ("1,2,3", (None, None)),
    ],
)
def test_window_position_from_env(raw, expected):
    assert desktop.window_position_from_env({desktop.WINDOW_POS_ENV: raw}) == expected


def test_pythonw_output_goes_to_log_file(monkeypatch, tmp_path):
    log_path = tmp_path / "data" / "desktop.log"
    monkeypatch.setattr(desktop, "LOG_PATH", log_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    desktop._route_output_to_log()
    try:
        print("hello from pythonw")
        sys.stdout.flush()
    finally:
        stream = sys.stdout
    stream.close()
    assert "hello from pythonw" in log_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 더블클릭 실행 파일


def test_launcher_is_ascii_and_starts_pythonw_without_console():
    raw = (ROOT / "JG-Marketing-Agent.cmd").read_bytes()
    raw.decode("ascii")  # .cmd는 ASCII
    text = raw.decode("ascii")
    assert 'start "" ".venv\\Scripts\\pythonw.exe" -m app.desktop' in text
    assert 'if not exist ".venv\\Scripts\\pythonw.exe"' in text
    assert "pip install -r requirements.txt" in text  # .venv가 없으면 준비 방법 안내


def test_window_library_is_a_runtime_requirement():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("pywebview") for line in lines)
