"""프로필 로그인(R2, UI_SPEC 5절): 로그인 창 열기와 로그인 여부 확인.

- **로그인하기**(`open_window`): 그 프로필 폴더로 **일반 크롬**을 유튜브 로그인 주소로 연다.
  자동화 표시 없이, 인자 목록으로, 셸 없이(`chrome.assist_args` · `chrome.popen_launcher`). 사용자가
  직접 구글 계정으로 로그인한다. 프로그램은 아이디·비밀번호를 받거나 저장하거나 입력하지 않는다.
  [유튜브 열기]도 같은 방식으로 유튜브 첫 화면을 연다(로그아웃은 거기서 사람이 한다).
- **로그인 확인**(`check`): 그 프로필로 유튜브 첫 화면을 **창 없이** 열어 로그인 표시
  (`youtube_driver.SELECTORS.signed_in`·`sign_in`)와 채널(계정) 이름을 **읽기만** 한다. 아무것도
  입력하거나 누르지 않는다. Playwright는 작업 서비스의 전용 작업 스레드에서만 돈다(`jobs.run_task`).
  게시 작업 중이면 「게시가 끝난 뒤 확인」.
- 결과(로그인됨/안 됨/모름, 이름, 확인한 때)는 `profile_logins` 표에 남겨
  프로필 화면·아래 줄·③칸에 보인다.
- 로그인 창은 `LoginWindows`가 지켜본다. 사람이 그 크롬을 닫으면 한 번 자동으로 확인한다.
  설정을 저장해 서비스를 다시 만들어도 창 목록은 그대로다(`ServiceHolder`가 하나를 계속 쓴다).
- 같은 프로필을 다른 크롬 창이 쓰는 중이면(`lockfile`) 「그 프로필의 크롬 창을 닫아 주세요」.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.browser.chrome import (
    Launcher,
    assist_args,
    ensure_profile_dir,
    profile_in_use,
    require_profile_free,
)
from app.browser.screens import Monitor, check_window_position
from app.browser.youtube_driver import SELECTORS, YouTubeSelectors
from app.config import BrowserSettings
from app.errors import AppError, ErrorKind
from app.ops.profiles import ProfileService
from app.youtube.quota import Clock, utc_now

log = logging.getLogger("app.browser.login")

HOME_URL = "https://www.youtube.com/"
# 유튜브의 「로그인」 단추가 여는 주소와 같은 모양. 로그인하면 유튜브 첫 화면으로 돌아온다
LOGIN_URL = (
    "https://accounts.google.com/ServiceLogin?service=youtube&passive=true&hl=ko"
    "&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue"
    "%26app%3Ddesktop%26hl%3Dko%26next%3Dhttps%253A%252F%252Fwww.youtube.com%252F"
)
LAUNCH_TIMEOUT_MS = 30_000
PAGE_TIMEOUT_MS = 25_000
SIGN_WAIT_MS = 15_000
LOCK_RELEASE_SECONDS = 6.0  # 사람이 창을 닫은 뒤 크롬이 폴더 잠금을 푸는 데 걸리는 시간
CHECK_TIMEOUT_SECONDS = 90.0

STATE_SIGNED_IN = "signed_in"
STATE_SIGNED_OUT = "signed_out"
STATE_UNKNOWN = "unknown"  # 유튜브 화면에서 로그인 표시를 찾지 못함(화면이 바뀌었거나 막힘)
NOTE_UNKNOWN = "유튜브 화면에서 로그인 표시를 찾지 못했습니다. 잠시 뒤 다시 확인해 주세요."

# 계정 이름을 읽는 스크립트: 유튜브가 계정 메뉴에 쓰는 정보를 같은 주소에서 받아 읽는다
# (GET, 읽기만).
# 못 읽으면 화면의 계정 이름 요소를 본다. 둘 다 없으면 빈 글(로그인됨, 이름 모름)
_NAME_SCRIPT = """async ([endpoint, selector]) => {
  try {
    const res = await fetch(endpoint, { credentials: 'include' });
    const text = await res.text();
    const name = /"accountName"\\s*:\\s*\\{\\s*"simpleText"\\s*:\\s*/.source;
    const m = text.match(new RegExp(name + /"((?:[^"\\\\]|\\\\.)*)"/.source));
    if (m) return JSON.parse('"' + m[1] + '"');
  } catch (e) { /* 이름은 못 읽어도 된다 */ }
  const node = document.querySelector(selector);
  return node ? (node.textContent || '').trim() : '';
}"""


@dataclass(frozen=True)
class LoginResult:
    state: str  # signed_in | signed_out | unknown
    channel: str = ""
    note: str = ""


@dataclass(frozen=True)
class LoginState:
    name: str
    folder: str
    exists: bool  # 프로필 폴더가 있는지
    state: str | None  # 확인한 적 없으면 None
    channel: str
    checked_at: str | None
    note: str
    window_open: bool

    @property
    def signed_in(self) -> bool | None:
        if self.state == STATE_SIGNED_IN:
            return True
        if self.state == STATE_SIGNED_OUT:
            return False
        return None


LoginChecker = Callable[[Path], LoginResult]


def check_login(
    user_data_dir: Path,
    *,
    prepare_context: Callable[[Any], None] | None = None,
    selectors: YouTubeSelectors = SELECTORS,
) -> LoginResult:
    """창 없이 유튜브 첫 화면을 열어 로그인 표시와 계정 이름을 읽는다(아무것도 누르지 않는다).

    작업 스레드에서만 부른다. `prepare_context`는 테스트가 가짜 페이지를 끼우는 자리.
    """
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    if profile_in_use(user_data_dir):
        raise AppError(ErrorKind.PROFILE_IN_USE, detail=f"프로필 폴더 {Path(user_data_dir).name}")
    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(user_data_dir),
                channel="chrome",
                headless=True,  # 창 없이(읽기만)
                args=["--no-first-run", "--no-default-browser-check"],
                timeout=LAUNCH_TIMEOUT_MS,
            )
        except PlaywrightError as exc:
            if profile_in_use(user_data_dir):
                raise AppError(ErrorKind.PROFILE_IN_USE) from None
            first = str(exc).strip().splitlines()[0][:160] if str(exc).strip() else "알 수 없음"
            raise AppError(
                ErrorKind.PROFILE_CHECK_FAILED, detail=f"크롬을 열지 못함: {first}"
            ) from None
        try:
            if prepare_context is not None:
                prepare_context(ctx)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            except PlaywrightError:
                raise AppError(
                    ErrorKind.PROFILE_CHECK_FAILED, detail="유튜브 첫 화면을 열지 못함"
                ) from None
            sel = selectors
            try:
                page.wait_for_selector(
                    f"{sel.signed_in}, {sel.sign_in}", state="attached", timeout=SIGN_WAIT_MS
                )
            except PlaywrightError:
                return LoginResult(STATE_UNKNOWN, "", NOTE_UNKNOWN)
            if page.locator(sel.signed_in).count() == 0:
                return LoginResult(STATE_SIGNED_OUT)
            try:
                name = page.evaluate(_NAME_SCRIPT, [sel.account_endpoint, sel.account_name])
            except PlaywrightError:
                name = ""
            return LoginResult(STATE_SIGNED_IN, " ".join(str(name or "").split())[:100])
        finally:
            try:
                ctx.close()
            except Exception:  # 닫는 중 오류는 결과를 바꾸지 않는다
                pass


def default_checker(user_data_dir: Path) -> LoginResult:
    return check_login(user_data_dir)


class LoginWindows:
    """프로그램이 연 로그인·유튜브 크롬 창(프로필 이름 → 프로세스). 닫히면 `on_closed`를 부른다."""

    def __init__(self) -> None:
        self._procs: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.on_closed: Callable[[str], None] | None = None

    def is_open(self, name: str) -> bool:
        with self._lock:
            proc = self._procs.get(name)
        if proc is None:
            return False
        poll = getattr(proc, "poll", None)
        return poll is None or poll() is None

    def track(self, name: str, proc: Any) -> None:
        with self._lock:
            self._procs[name] = proc
        if not callable(getattr(proc, "wait", None)):
            return  # 지켜볼 수 없는 것(가짜 실행기)
        threading.Thread(
            target=self._watch, args=(name, proc), name=f"jg-login-{name}", daemon=True
        ).start()

    def _watch(self, name: str, proc: Any) -> None:
        try:
            proc.wait()
        except Exception:
            return
        with self._lock:
            if self._procs.get(name) is proc:
                del self._procs[name]
        callback = self.on_closed
        if callback is not None:
            try:
                callback(name)
            except Exception:  # 자동 확인이 실패해도 사람은 [로그인 확인]을 누를 수 있다
                log.info("로그인 창을 닫은 뒤 자동 확인을 하지 못했습니다(%s)", name)


class ProfileAccounts:
    """프로필 로그인 창 열기와 로그인 확인, 확인 결과 저장."""

    def __init__(
        self,
        *,
        db_path: Path,
        profiles: ProfileService,
        browser: BrowserSettings,
        chrome_finder: Callable[[], Path | None],
        run_on_worker: Callable[..., Any],
        busy: Callable[[], bool],
        windows: LoginWindows,
        launcher: Launcher,
        checker: LoginChecker = default_checker,
        playwright_ready: Callable[[], bool] = lambda: True,
        screens: Callable[[], Sequence[Monitor]] | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self.db_path = db_path
        self.profiles = profiles
        self.browser = browser
        self.chrome_finder = chrome_finder
        self.run_on_worker = run_on_worker
        self.busy = busy
        self.windows = windows
        self.launcher = launcher
        self.checker = checker
        self.playwright_ready = playwright_ready
        self.screens = screens
        self.clock = clock

    # ------------------------------------------------------------ 읽기

    def _rows(self) -> dict[str, Any]:
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT profile, state, channel, checked_at, note FROM profile_logins"
            ).fetchall()
        return {r["profile"]: r for r in rows}

    def states(self) -> list[LoginState]:
        rows = self._rows()
        out = []
        for p in self.profiles.list_profiles():
            row = rows.get(p.name)
            out.append(
                LoginState(
                    name=p.name,
                    folder=p.folder,
                    exists=(Path(self.browser.profiles_root) / p.folder).is_dir(),
                    state=row["state"] if row else None,
                    channel=(row["channel"] or "") if row else "",
                    checked_at=row["checked_at"] if row else None,
                    note=(row["note"] or "") if row else "",
                    window_open=self.windows.is_open(p.name),
                )
            )
        return out

    def state_of(self, name: str) -> LoginState:
        self.profiles.get(name)  # 없는 이름이면 profile_unknown
        for s in self.states():
            if s.name == name:
                return s
        raise AppError(ErrorKind.PROFILE_UNKNOWN, detail=f"프로필 {name!r}")

    # ------------------------------------------------------------ 창 열기

    def _position(self) -> tuple[int, int]:
        wanted = self.browser.window_position
        monitors: list[Monitor] = []
        if self.screens is not None:
            try:
                monitors = list(self.screens())
            except Exception:
                monitors = []
        return check_window_position(wanted, monitors).position or wanted

    def open_window(self, name: str, *, url: str = LOGIN_URL) -> LoginState:
        """그 프로필 폴더로 일반 크롬을 연다(로그인 주소 또는 유튜브 첫 화면). 셸 없이 인자 목록."""
        if url not in (LOGIN_URL, HOME_URL):
            raise ValueError("로그인 창은 정해 둔 주소만 연다")
        profile = self.profiles.get(name)
        chrome = self.chrome_finder()
        if chrome is None:
            raise AppError(ErrorKind.CHROME_NOT_FOUND)
        if self.windows.is_open(name):
            raise AppError(ErrorKind.PROFILE_IN_USE, detail="프로그램이 연 창이 아직 열려 있음")
        path = ensure_profile_dir(self.browser.profiles_root, profile.folder)
        require_profile_free(path)
        args = assist_args(chrome, path, url, self._position())
        proc = self.launcher(args)
        self.windows.track(name, proc)
        return self.state_of(name)

    # ------------------------------------------------------------ 확인

    def check(self, name: str, *, wait_release: float = 0.0) -> LoginState:
        """창 없이 로그인 여부와 채널 이름을 읽어 저장한다. 작업 스레드에서 돈다."""
        profile = self.profiles.get(name)
        if self.busy():
            raise AppError(ErrorKind.PROFILE_CHECK_BUSY)
        if self.windows.is_open(name):
            raise AppError(ErrorKind.PROFILE_IN_USE, detail="로그인 창이 아직 열려 있음")
        if not self.playwright_ready():
            raise AppError(ErrorKind.PLAYWRIGHT_MISSING)
        if self.chrome_finder() is None:
            raise AppError(ErrorKind.CHROME_NOT_FOUND)
        path = ensure_profile_dir(self.browser.profiles_root, profile.folder)
        deadline = time.monotonic() + wait_release
        while profile_in_use(path) and time.monotonic() < deadline:
            time.sleep(0.3)
        require_profile_free(path)
        result: LoginResult = self.run_on_worker(
            lambda: self.checker(path), timeout=CHECK_TIMEOUT_SECONDS
        )
        self._save(name, result)
        return self.state_of(name)

    def check_after_close(self, name: str) -> None:
        """로그인 창이 닫힌 뒤 한 번 자동으로 확인한다(실패하면 조용히 넘어간다)."""
        try:
            self.check(name, wait_release=LOCK_RELEASE_SECONDS)
        except AppError as exc:
            log.info("자동 로그인 확인을 건너뜀(%s): %s", name, exc.kind)

    def _save(self, name: str, result: LoginResult) -> None:
        now = self.clock().isoformat()
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO profile_logins(profile, state, channel, checked_at, note) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(profile) DO UPDATE SET state=excluded.state, "
                "channel=excluded.channel, checked_at=excluded.checked_at, note=excluded.note",
                (name, result.state, result.channel, now, result.note),
            )
