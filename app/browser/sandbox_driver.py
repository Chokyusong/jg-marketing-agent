"""테스트 페이지(sandbox) 자동 실행기 — Playwright 동기 API (8단계, DESIGN 6.3).

**이 모듈은 이 앱의 `/sandbox/` 주소만 연다.** 실제 유튜브 주소를 넘기면 열기 전에 거절하고,
페이지가 바깥 주소를 불러오려 해도 경로 가로채기(`context.route`)가 막는다. 실제 유튜브 화면의
요소를 찾거나 누르는 코드는 여기에 없다.

Playwright는 스레드에 안전하지 않다(공식 문서 "Playwright's API is not thread-safe").
그래서 이 객체는 작업 서비스의 **전용 작업 스레드 하나에서만** 만들고 쓰고 닫는다
(`app/browser/jobs.py`).

Playwright(Apache-2.0) 사용법 출처(확인 2026-11-16, playwright 1.65.2):
- https://playwright.dev/python/docs/api/class-browsertype —
  `launch_persistent_context(user_data_dir, channel="chrome", headless=..., args=[...],
  no_viewport=...)`. "browsers do not allow launching
  multiple instances with the same User Data Directory"
- https://playwright.dev/python/docs/library — 동기 API, 스레드 주의,
  `time.sleep` 대신 `wait_for_timeout`
- https://playwright.dev/python/docs/browsers — `channel="chrome"`은 설치된 Google Chrome을 쓴다
  (브라우저를 내려받지 않는다)
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.browser.chrome import profile_in_use, window_arg

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")
SANDBOX_PATH = "/sandbox/"
LAUNCH_TIMEOUT_MS = 30_000
STEP_TIMEOUT_MS = 10_000
CLICK_TIMEOUT_MS = 5_000
VERIFY_TIMEOUT_MS = 15_000
log = logging.getLogger("app.browser.sandbox_driver")
HEADED_WINDOW_SIZE = "--window-size=1280,900"  # 크기를 정하지 못했을 때(예전 고정값)

TEXT_PROFILE_IN_USE = "그 프로필의 크롬 창이 이미 열려 있습니다. 그 프로필의 크롬 창을 닫아 주세요."


class DriverError(Exception):
    """사용자에게 보일 실패 사유를 담는다. `screenshot`이 참이면 화면 캡처를 남긴다.

    `code`(R3)는 작업 서비스가 알아볼 실패 종류(예: `signed_out` — 로그인 안 됨을 기록에 남긴다).
    """

    def __init__(self, reason: str, *, screenshot: bool = True, code: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.screenshot = screenshot
        self.code = code


class Stopped(Exception):  # noqa: N818 - 실패가 아니라 취소
    """입력 중에 작업이 취소됐다."""


def is_sandbox_url(url: str) -> bool:
    """이 앱(로컬 주소)의 `/sandbox/` 주소인지. 실제 유튜브 주소는 거짓."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "http" and host in LOCAL_HOSTS and parts.path.startswith(SANDBOX_PATH)


def is_local_url(url: str) -> bool:
    """페이지가 불러와도 되는 주소: 이 앱(로컬) 주소와 빈 페이지만."""
    if url.startswith(("about:", "data:", "blob:")):
        return True
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "ws") and (parts.hostname or "").lower() in LOCAL_HOSTS


def require_sandbox_url(url: str) -> str:
    if not is_sandbox_url(url):
        raise ValueError(f"테스트 페이지 주소가 아니라 열지 않습니다: {url!r}")
    return url


class BrowserDriver(Protocol):
    visited: list[str]

    def open(self, user_data_dir: Path, url: str) -> None: ...
    def type_comment(
        self, text: str, delay_ms: tuple[int, int], should_stop: Callable[[], bool]
    ) -> None: ...
    def click_post(self) -> None: ...
    def verify_posted(self, text: str) -> None: ...
    def screenshot(self, path: Path) -> bool: ...
    def close(self) -> None: ...


class PlaywrightSandboxDriver:
    """설치된 크롬을 프로필 폴더로 열어 테스트 페이지에서 입력·게시·확인한다."""

    guard_requests = True  # 바깥 주소 요청을 모두 막는다(`_guard`)

    def __init__(
        self,
        *,
        headless: bool,
        window_position: tuple[int, int] | None,
        rng: random.Random | None = None,
        window_size: tuple[int, int] | None = None,
        window_target: Any = None,
    ) -> None:
        self.headless = headless
        self.window_position = window_position
        # 2026-11-17 창 위치 자동: 모니터 작업 영역에 맞춘 크기와, 연 뒤 확인할 목표(placement)
        self.window_size = window_size
        self.window_target = window_target
        self.window_check = ""  # 연 뒤 확인 결과(ok · fit · move · fit_other · other · 빈 값)
        self.window_note = ""  # 사람에게 알릴 한 줄(바로잡지 못했을 때)
        self.rng = rng or random.Random()
        self.visited: list[str] = []  # 페이지가 실제로 간 주소(테스트가 sandbox뿐인지 확인한다)
        self.blocked: list[str] = []  # 막은 바깥 요청
        self._pw: Any = None
        self._ctx: Any = None
        self._page: Any = None

    # ------------------------------------------------------------ 열기

    def launch_args(self) -> list[str]:
        args = [window_arg(self.window_position)] if self.window_position is not None else []
        args += ["--no-first-run", "--no-default-browser-check"]
        if not self.headless:
            size = self.window_size
            args.append(f"--window-size={int(size[0])},{int(size[1])}" if size
                        else HEADED_WINDOW_SIZE)
        return args

    def open(self, user_data_dir: Path, url: str) -> None:
        require_sandbox_url(url)  # 실제 유튜브 주소는 여기서 끝난다
        from playwright.sync_api import Error as PlaywrightError

        self._launch(user_data_dir)
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            self._page.wait_for_selector("#comment-input", state="visible")
        except PlaywrightError:
            raise DriverError("연습 페이지를 열지 못했습니다(댓글 상자가 보이지 않음).") from None

    def _launch(self, user_data_dir: Path) -> None:
        """프로필 폴더로 크롬을 열고 주소 가로채기(`_guard`)와 방문 기록을 건다."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        if profile_in_use(user_data_dir):
            raise DriverError(TEXT_PROFILE_IN_USE, screenshot=False)
        self._pw = sync_playwright().start()
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(
                str(user_data_dir),
                channel="chrome",
                headless=self.headless,
                args=self.launch_args(),
                no_viewport=not self.headless,
                timeout=LAUNCH_TIMEOUT_MS,
            )
        except PlaywrightError as exc:
            if profile_in_use(user_data_dir):
                raise DriverError(TEXT_PROFILE_IN_USE, screenshot=False) from None
            first = str(exc).strip().splitlines()[0][:160] if str(exc).strip() else "알 수 없음"
            raise DriverError(f"크롬을 열지 못했습니다: {first}", screenshot=False) from None
        self._ctx.set_default_timeout(STEP_TIMEOUT_MS)
        if self.guard_requests:
            self._ctx.route("**/*", self._guard)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self._page.on("framenavigated", self._on_navigated)
        if not self.headless and self.window_target is not None:
            self._check_window()

    def _check_window(self) -> None:
        """창을 연 뒤 실제 위치를 크롬에게 묻고 정한 모니터 작업 영역 밖이면 바로잡는다.

        화면 배율이 섞이면 넘긴 좌표와 실제 위치가 어긋날 수 있다(app/browser/placement.py 머리말).
        위치는 페이지의 `screenX`·`outerWidth`·`screen.avail*`(모두 크롬 DIP)로 읽고, 바로잡기는
        DevTools `Browser.getWindowForTarget` → `Browser.setWindowBounds`. 실패해도 게시는 계속한다.
        """
        from app.browser.placement import LANDED_SCRIPT, correct_window, landed_from

        try:
            cdp = self._ctx.new_cdp_session(self._page)
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
        except Exception:
            log.info("크롬 창 위치를 확인하지 못했습니다(DevTools 연결 없음)")
            return
        tried_move = False
        for _ in range(3):
            try:
                landed = landed_from(self._page.evaluate(LANDED_SCRIPT))
            except Exception:
                return
            if landed is None:
                return
            bounds, why = correct_window(landed, self.window_target, tried_move=tried_move)
            self.window_check = why
            if why == "other":
                self.window_note = "크롬 창을 고른 모니터로 옮기지 못했습니다(지금 화면 안에 있음)"
            if bounds is None:
                return
            if why == "move":
                tried_move = True
            if why == "fit_other":
                self.window_note = "크롬 창을 고른 모니터로 옮기지 못해 지금 화면 안에 맞췄습니다"
            left, top, width, height = bounds
            try:
                cdp.send("Browser.setWindowBounds",
                         {"windowId": window_id, "bounds": {"windowState": "normal"}})
                cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {
                    "left": int(left), "top": int(top),
                    "width": int(width), "height": int(height)}})
                self._page.wait_for_timeout(200)
            except Exception:
                return
            if why == "fit_other":
                return

    def _guard(self, route: Any) -> None:
        url = route.request.url
        if is_local_url(url):
            route.continue_()
        else:
            self.blocked.append(url)
            route.abort()

    def _on_navigated(self, frame: Any) -> None:
        if frame == self._page.main_frame:
            self.visited.append(frame.url)

    # ------------------------------------------------------------ 입력·게시·확인

    def type_comment(
        self, text: str, delay_ms: tuple[int, int], should_stop: Callable[[], bool]
    ) -> None:
        """댓글 상자를 누르고 한 글자씩 입력한다. 글자마다 `delay_ms` 사이 무작위로 기다린다."""
        from playwright.sync_api import Error as PlaywrightError

        page = self._page
        lo, hi = delay_ms
        try:
            page.click("#comment-input")
            for ch in text:
                if should_stop():
                    raise Stopped
                page.keyboard.type(ch)
                page.wait_for_timeout(self.rng.randint(lo, hi))
            typed = page.input_value("#comment-input")
        except PlaywrightError:
            raise DriverError("연습 페이지 댓글 상자에 입력하지 못했습니다.") from None
        if typed != text:
            raise DriverError(
                "연습 페이지 댓글 상자에 들어간 글이 [댓글 달기]를 누른 초안과 다릅니다."
            )

    def click_post(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        try:
            self._page.locator("#comment-submit").click(timeout=CLICK_TIMEOUT_MS)
        except PlaywrightError:
            raise DriverError(
                "연습 페이지에서 찾지 못한 요소: 「댓글」 게시 단추(요소 이름 #comment-submit)."
            ) from None

    def verify_posted(self, text: str) -> None:
        """페이지의 댓글 목록에서 내 댓글 글을 찾는다. 페이지가 저장을 거절하면 그 사유로 실패."""
        from playwright.sync_api import Error as PlaywrightError

        script = """(text) => {
          if (document.body.dataset.state === 'error') return 'error';
          const found = [...document.querySelectorAll('#comment-list .c-body')]
            .some((n) => n.textContent === text);
          return found ? 'ok' : false;
        }"""
        try:
            handle = self._page.wait_for_function(script, arg=text, timeout=VERIFY_TIMEOUT_MS)
            result = handle.json_value()
        except PlaywrightError:
            raise DriverError("게시한 댓글을 연습 페이지에서 찾지 못했습니다(시간 초과).") from None
        if result == "error":
            message = self._page.text_content("#post-status") or ""
            raise DriverError(f"연습 페이지가 게시를 거절했습니다: {message.strip()}")

    # ------------------------------------------------------------ 게시 뒤 열어 둔 창(2026-11-18)

    comment_selector = "#comment-list .c-body"  # 달린 댓글의 글(유튜브 실행기는 자기 것을 쓴다)

    def _comment_selector(self) -> str:
        return self.comment_selector

    def show_comment(self, text: str) -> bool:
        """방금 단 내 댓글을 화면 가운데로 내린다(읽기·스크롤만, 아무것도 누르지 않는다).

        찾아서 내렸으면 True. 공백 차이는 무시한다."""
        script = """([selector, text]) => {
          const norm = (s) => (s || '').split(/\\s+/).filter(Boolean).join(' ');
          const want = norm(text);
          const node = [...document.querySelectorAll(selector)]
            .find((n) => norm(n.textContent) === want);
          if (!node) return false;
          node.scrollIntoView({ block: 'center', inline: 'nearest' });
          return true;
        }"""
        if self._page is None:
            return False
        try:
            return bool(self._page.evaluate(script, [self._comment_selector(), text]))
        except Exception:
            return False

    def wait_closed(self, seconds: float) -> bool:
        """최대 `seconds`초 기다리며 사람이 창을 닫았는지 본다(닫혔으면 True).

        기다리는 동안 Playwright가 창·페이지 닫힘 소식을 받는다(동기 API는 부를 때만 받는다)."""
        page = self._page
        if page is None:
            return True
        try:
            if page.is_closed():
                return True
            page.wait_for_timeout(max(1, int(seconds * 1000)))
            return page.is_closed()
        except Exception:  # 창(크롬)이 닫혀 페이지를 쓸 수 없다
            return True

    # ------------------------------------------------------------ 마무리

    def screenshot(self, path: Path) -> bool:
        if self._page is None:
            return False
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._page.screenshot(path=str(path), full_page=True)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """크롬과 Playwright를 닫는다. 남는 프로세스가 없게 오류가 나도 끝까지 한다."""
        ctx, pw = self._ctx, self._pw
        self._ctx = self._pw = self._page = None
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass
