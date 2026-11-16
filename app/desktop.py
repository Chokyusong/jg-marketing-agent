"""대시보드를 자체 창 프로그램으로 실행한다 (PLAYBOOK P단계, 결정 D7: 내장 웹뷰 창).

실행: `.venv\\Scripts\\pythonw.exe -m app.desktop` (더블클릭용 `JG-Marketing-Agent.cmd`)

흐름: 중복 실행 확인 → 빈 포트 고르기 → uvicorn을 스레드로 시작 → `/api/health` 응답 대기
→ 창 열기(주 스레드) → 창이 닫히면 진행 중인 게시 작업을 취소하고 크롬을 닫은 뒤(8단계)
서버를 멈추고 프로세스가 끝난다(남는 크롬·파이썬 프로세스가 없게).
화면과 서버 코드는 그대로 쓴다(`app.main:app`). 기존 API는 바꾸지 않는다.

창 라이브러리: pywebview (확인한 날짜 2026-11-16)
- 패키지 이름 `pywebview`, 설치 `pip install pywebview`. 확인 당시 최신 6.2.1(2026-04-15).
- 라이선스 BSD 3-Clause. Requires-Python >=3.8, 분류에 Python 3.12 있음.
- Windows: pythonnet(.NET Framework 4.6.2 이상)과 Microsoft Edge WebView2 Runtime으로
  Chromium(edgechromium) 렌더러를 쓴다. 런타임이 없으면 낡은 MSHTML(IE)로 내려가므로,
  이 모듈은 그때 창을 열지 않고 WebView2 설치를 안내한다.
- `target=_blank` 링크는 설정 OPEN_EXTERNAL_LINKS_IN_BROWSER(기본 True)로 기본 브라우저에서 열린다.
- 창 위치 x, y를 주지 않으면 화면 가운데에 뜬다.
- 출처: https://pypi.org/project/pywebview/ ,
  https://pywebview.flowrl.com/guide/installation.html ,
  https://pywebview.flowrl.com/guide/web_engine.html , https://pywebview.flowrl.com/api/

창 라이브러리는 창을 여는 함수 안에서 import한다. 그래서 pywebview가 없어도 자동 테스트가 돈다.
테스트는 `run(open_window=..., notify=...)`에 가짜 함수를 넣어 창을 실제로 띄우지 않는다.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn

log = logging.getLogger("app.desktop")

WINDOW_TITLE = "JG Marketing Agent"
WINDOW_SIZE = (1600, 1000)
WINDOW_MIN_SIZE = (1100, 720)
WINDOW_BACKGROUND = "#0A0A0A"  # 화면 배경색(style.css --bg). 불러오는 동안 흰 화면이 번쩍이지 않게
HOST = "127.0.0.1"
INSTANCE_NAME = "Local\\JGMarketingAgent.Desktop"
READY_TIMEOUT_SECONDS = 20.0
STOP_TIMEOUT_SECONDS = 10.0
# 개발·확인용: "x,y"를 주면 그 위치에 창을 띄운다(예: 2번 모니터). 평소에는 비워 두어 가운데에 뜬다.
WINDOW_POS_ENV = "JG_DESKTOP_WINDOW_POS"

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "desktop.log"
LOG_MAX_BYTES = 1_000_000

EXIT_OK = 0
EXIT_ALREADY_RUNNING = 3
EXIT_START_FAILED = 4
EXIT_WINDOW_FAILED = 5

TEXT_ALREADY_RUNNING = (
    "JG Marketing Agent가 이미 실행 중입니다.\n작업 표시줄에서 열려 있는 창을 써 주세요."
)
TEXT_START_FAILED = (
    "프로그램 안쪽 서버를 시작하지 못했습니다.\n"
    "자세한 내용은 data\\desktop.log를 보거나,\n"
    "개발용 scripts\\run.ps1로 실행해 오류를 확인해 주세요."
)
TEXT_NO_WEBVIEW_LIB = (
    "창 라이브러리(pywebview)가 설치되어 있지 않습니다.\n"
    "저장소 폴더에서 다음을 한 번 실행해 주세요.\n"
    ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
)
TEXT_NO_WEBVIEW2 = (
    "Microsoft Edge WebView2 Runtime을 찾지 못했습니다.\n"
    "Microsoft 공식 페이지에서 'WebView2 Runtime'(Evergreen)을 설치한 뒤 다시 실행해 주세요."
)
TEXT_WINDOW_FAILED = "창을 열지 못했습니다.\n자세한 내용은 data\\desktop.log를 봐 주세요."


@dataclass(frozen=True)
class WindowSpec:
    """창 여는 함수에 넘기는 값. 테스트의 가짜 함수도 같은 값을 받는다."""

    url: str
    title: str = WINDOW_TITLE
    width: int = WINDOW_SIZE[0]
    height: int = WINDOW_SIZE[1]
    min_size: tuple[int, int] = WINDOW_MIN_SIZE
    x: int | None = None  # None이면 가운데
    y: int | None = None


class WebViewUnavailable(RuntimeError):
    """창 라이브러리나 WebView2 런타임이 없어 창을 열 수 없다. 사용자에게 보일 문구를 담는다."""


OpenWindow = Callable[[WindowSpec], None]
Notify = Callable[[str], None]


# ---------------------------------------------------------------- 중복 실행 막기


class InstanceLock:
    """한 PC에서 하나만 실행되게 한다.

    Windows는 이름 있는 뮤텍스를 쓴다. 프로세스가 비정상으로 끝나도 운영체제가 풀어 주므로
    남은 잠금 파일 때문에 실행이 막히는 일이 없다. 다른 운영체제는 잠금 파일(flock)로 대신한다.
    """

    def __init__(self, name: str = INSTANCE_NAME) -> None:
        self.name = name
        self._handle: Any = None
        self._file: Any = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def release(self) -> None:
        if self._handle is not None:
            import ctypes

            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
            self._handle = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def _acquire_windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise OSError(error, "CreateMutexW failed")
        if error == 183:  # ERROR_ALREADY_EXISTS: 다른 실행이 잡고 있다
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def _acquire_posix(self) -> bool:  # pragma: no cover - 이 프로젝트는 Windows에서 돈다
        import fcntl
        import tempfile

        safe = "".join(ch if ch.isalnum() else "_" for ch in self.name)
        handle = open(Path(tempfile.gettempdir()) / f"{safe}.lock", "a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def __enter__(self) -> InstanceLock:
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


# ---------------------------------------------------------------- 서버


def open_listen_socket(host: str = HOST) -> socket.socket:
    """비어 있는 포트에 묶인 소켓을 돌려준다.

    운영체제가 고른 포트(0번 요청)를 닫지 않고 그대로 uvicorn에 넘기므로,
    포트를 고른 뒤 서버가 뜨기 전에 다른 프로그램이 가로챌 틈이 없다.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, 0))
    except OSError:
        sock.close()
        raise
    return sock


class ServerThread:
    """uvicorn을 주 스레드가 아닌 스레드에서 돌린다(창 라이브러리가 주 스레드를 차지한다)."""

    def __init__(self, asgi_app: Any, sock: socket.socket) -> None:
        self.sock = sock
        config = uvicorn.Config(asgi_app, log_level="info", use_colors=False, lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self._serve, name="jg-desktop-server", daemon=True)

    def _serve(self) -> None:
        # uvicorn은 시작에 실패하면 sys.exit(3)을 부른다. 스레드 안에서는 기록만 남기고 끝낸다.
        try:
            self.server.run(sockets=[self.sock])
        except SystemExit as exc:
            log.error("server exited during startup (code %s)", exc.code)
        except Exception:
            log.exception("server crashed")

    @property
    def port(self) -> int:
        return int(self.sock.getsockname()[1])

    def start(self) -> None:
        self.thread.start()

    def is_alive(self) -> bool:
        return self.thread.is_alive()

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> bool:
        """서버를 멈춘다. 제시간에 멈췄으면 True."""
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout)
        stopped = not self.thread.is_alive()
        if not stopped:
            self.server.force_exit = True
            self.thread.join(2.0)
            stopped = not self.thread.is_alive()
        try:
            self.sock.close()
        except OSError:
            pass
        return stopped


def wait_until_ready(
    base_url: str,
    *,
    timeout: float = READY_TIMEOUT_SECONDS,
    interval: float = 0.1,
    is_alive: Callable[[], bool] = lambda: True,
) -> bool:
    """`/api/health`가 status=ok로 답할 때까지 기다린다. 서버가 먼저 죽거나 시간이 지나면 False."""
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=1.0, trust_env=False) as client:
        while True:
            try:
                response = client.get(f"{base_url}/api/health")
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return True
            except (httpx.HTTPError, ValueError):
                pass
            if not is_alive() or time.monotonic() >= deadline:
                return False
            time.sleep(interval)


# ---------------------------------------------------------------- 창과 알림 (실제 구현)


def window_position_from_env(
    environ: dict[str, str] | None = None,
) -> tuple[int | None, int | None]:
    """개발·확인용 창 위치. 값이 없거나 잘못되면 (None, None) → 가운데."""
    raw = (environ if environ is not None else os.environ).get(WINDOW_POS_ENV, "").strip()
    if not raw:
        return None, None
    try:
        x_text, y_text = raw.split(",", 1)
        return int(x_text.strip()), int(y_text.strip())
    except ValueError:
        return None, None


def open_webview_window(spec: WindowSpec) -> None:
    """pywebview 창을 열고, 창이 닫힐 때까지 돌아오지 않는다(주 스레드에서 부른다)."""
    try:
        import webview
    except ImportError as exc:
        raise WebViewUnavailable(TEXT_NO_WEBVIEW_LIB) from exc

    if sys.platform == "win32":
        # 렌더러는 이 모듈을 읽을 때 정해진다. WebView2가 없으면 IE(MSHTML)로 내려가 화면이 깨진다.
        from webview.platforms import winforms

        if getattr(winforms, "renderer", "") != "edgechromium":
            raise WebViewUnavailable(TEXT_NO_WEBVIEW2)

    # 창 안의 바깥 링크(target=_blank, 예: "YouTube에서 보기")는 기본 브라우저로 연다.
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.create_window(
        spec.title,
        spec.url,
        width=spec.width,
        height=spec.height,
        x=spec.x,
        y=spec.y,
        min_size=spec.min_size,
        background_color=WINDOW_BACKGROUND,
    )
    webview.start(private_mode=True)


def notify_user(message: str) -> None:
    """콘솔이 없는 실행(pythonw)에서도 보이도록 Windows 메시지 상자로 알린다."""
    log.info("notify: %s", message.replace("\n", " "))
    if sys.platform == "win32":
        import ctypes

        mb_ok, mb_iconinformation, mb_setforeground = 0x0, 0x40, 0x10000
        ctypes.windll.user32.MessageBoxW(
            None, message, WINDOW_TITLE, mb_ok | mb_iconinformation | mb_setforeground
        )
    else:  # pragma: no cover
        print(message, file=sys.stderr)


def focus_existing_window(title: str = WINDOW_TITLE) -> bool:
    """이미 떠 있는 창을 앞으로 가져온다. 찾으면 True."""
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE: 최소화돼 있으면 되살린다
    user32.SetForegroundWindow(hwnd)
    return True


# ---------------------------------------------------------------- 실행


def shutdown_jobs(asgi_app: Any) -> None:
    """창을 닫을 때(8단계): 진행 중인 게시 작업을 취소하고 그 작업의 크롬을 닫는다.

    앱 서비스를 아직 만들지 않았으면 할 일이 없다. 서버를 멈출 때(lifespan)도 한 번 더 하지만,
    서버가 멈추는 시간 제한 안에 끝나도록 먼저 따로 부른다.
    """
    holder = getattr(getattr(asgi_app, "state", None), "services", None)
    stop = getattr(holder, "shutdown_jobs", None)
    if stop is None:
        return
    try:
        stop()
    except Exception:
        log.exception("failed to stop browser jobs")


def run(
    *,
    open_window: OpenWindow,
    notify: Notify,
    asgi_app: Any = None,
    lock: InstanceLock | None = None,
    host: str = HOST,
    ready_timeout: float = READY_TIMEOUT_SECONDS,
    window_pos: tuple[int | None, int | None] = (None, None),
    on_already_running: Callable[[], object] | None = None,
) -> int:
    """프로그램 한 번 실행. 종료 코드를 돌려준다. 테스트는 open_window·notify를 가짜로 넣는다."""
    lock = lock if lock is not None else InstanceLock()
    if not lock.acquire():
        log.info("already running")
        notify(TEXT_ALREADY_RUNNING)
        if on_already_running is not None:
            on_already_running()
        return EXIT_ALREADY_RUNNING

    try:
        try:
            if asgi_app is None:
                from app.main import app as asgi_app
            sock = open_listen_socket(host)
        except Exception:
            log.exception("failed to prepare server")
            notify(TEXT_START_FAILED)
            return EXIT_START_FAILED

        server = ServerThread(asgi_app, sock)
        base_url = f"http://{host}:{server.port}"
        log.info("starting server at %s", base_url)
        server.start()
        try:
            if not wait_until_ready(base_url, timeout=ready_timeout, is_alive=server.is_alive):
                log.error("server did not become ready at %s", base_url)
                notify(TEXT_START_FAILED)
                return EXIT_START_FAILED

            spec = WindowSpec(url=f"{base_url}/", x=window_pos[0], y=window_pos[1])
            try:
                open_window(spec)
            except WebViewUnavailable as exc:
                log.error("webview unavailable: %s", exc)
                notify(str(exc))
                return EXIT_WINDOW_FAILED
            except Exception:
                log.exception("window failed")
                notify(TEXT_WINDOW_FAILED)
                return EXIT_WINDOW_FAILED
            log.info("window closed")
            return EXIT_OK
        finally:
            shutdown_jobs(asgi_app)
            stopped = server.stop()
            log.info("server stopped" if stopped else "server did not stop in time")
    finally:
        lock.release()


def _route_output_to_log() -> None:
    """pythonw는 표준 출력이 없다(None). 서버 기록이 사라지지 않게 data/desktop.log로 보낸다.

    이 기록에는 요청 주소와 오류만 남는다. YouTube 키는 앱이 기록 전에 가린다(AGENTS.md).
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        stream = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> int:
    _route_output_to_log()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return run(
        open_window=open_webview_window,
        notify=notify_user,
        window_pos=window_position_from_env(),
        on_already_running=focus_existing_window,
    )


if __name__ == "__main__":
    sys.exit(main())
