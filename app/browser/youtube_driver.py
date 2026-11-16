"""내 채널 영상 자동 게시 실행기 — 실제 YouTube 영상 페이지(Playwright 동기 API).

`config.yaml`의 `own_video_ids`에 넣은 **내 채널 영상 하나만** 연다. 실행기를 만들 때 영상 ID를
정하고, `open()`은 그 영상의 `https://www.youtube.com/watch?v=<ID>` 주소가 아니면 열기 전에
거절한다. 페이지가 다른 곳으로 옮겨 가면(다른 영상·바깥 사이트) 다음 단계에서 멈춘다.

순서는 테스트 페이지 실행기와 같다: 프로필로 크롬 열기 → 댓글 상자까지 내리기 →
한 글자씩 입력 → (작업 서비스가 사람의 [게시 승인]을 기다림) → 「댓글」 누르기 → 내 댓글 찾기.

- 프로필이 YouTube에 로그인돼 있지 않으면 입력하지 않고 멈춘다.
- 화면 요소 이름은 `SELECTORS` 한곳에 모았다. YouTube 화면이 바뀌면 여기만 고친다.
  자동 테스트는 같은 이름을 쓴 가짜 페이지(`tests/fixtures/fake_youtube_watch.html`)를
  `prepare_context`로 끼워 넣어 돈다(실제 YouTube에 접속하지 않는다).
- Playwright는 스레드에 안전하지 않으므로 작업 서비스의 전용 작업 스레드에서만 만들고 쓴다.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.browser.sandbox_driver import DriverError, PlaywrightSandboxDriver, Stopped
from app.youtube.url_parser import is_video_id

WATCH_HOST = "www.youtube.com"
# 페이지가 머물러도 되는 곳: 그 영상 페이지, 쿠키 동의·로그인 화면
STAY_HOSTS = ("consent.youtube.com", "accounts.google.com", "accounts.youtube.com")
SIGN_IN_WAIT_MS = 15_000
FIND_BOX_TRIES = 25
SCROLL_PX = 800
SCROLL_PAUSE_MS = 800

TEXT_NOT_SIGNED_IN = (
    "이 프로필이 YouTube에 로그인돼 있지 않습니다. 그 프로필로 크롬을 열어 "
    "Google 계정에 로그인한 뒤 다시 시도해 주세요."
)
TEXT_COMMENTS_OFF = "이 영상은 댓글을 쓸 수 없게 돼 있습니다. YouTube Studio에서 댓글을 켜 주세요."
TEXT_NO_BOX = "YouTube 댓글 상자를 찾지 못했습니다(페이지를 내려도 보이지 않음)."
TEXT_LEFT_PAGE = "YouTube 페이지가 다른 곳으로 옮겨 가 멈췄습니다."


@dataclass(frozen=True)
class YouTubeSelectors:
    signed_in: str = "#avatar-btn"  # 로그인했을 때 오른쪽 위 내 사진
    sign_in: str = 'a[href*="ServiceLogin"]'  # 로그인 안 했을 때 「로그인」
    comments: str = "ytd-comments#comments"
    comments_off: str = "ytd-comments#comments ytd-message-renderer"  # 「댓글이 사용 중지됨」
    placeholder: str = "#simplebox-placeholder"  # 「댓글 추가...」
    editor: str = "ytd-commentbox #contenteditable-root"
    submit: str = "ytd-commentbox #submit-button"
    comment_text: str = "ytd-comments#comments #content-text"
    # R2 로그인 확인(읽기만): 계정 이름. 유튜브가 계정 메뉴에 쓰는 정보 주소(같은 사이트, GET)와,
    # 그것을 못 읽을 때 볼 화면 요소(계정 메뉴가 그려져 있을 때만 있다)
    account_endpoint: str = "/getAccountSwitcherEndpoint"
    account_name: str = "#account-name"


SELECTORS = YouTubeSelectors()


def is_watch_url_for(url: str, video_id: str) -> bool:
    """`https://www.youtube.com/watch?v=<video_id>`인지(다른 매개변수가 있어도 v가 같으면 참)."""
    if not is_video_id(video_id):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https" or (parts.hostname or "").lower() != WATCH_HOST:
        return False
    if parts.path != "/watch":
        return False
    return parse_qs(parts.query).get("v") == [video_id]


def may_stay(url: str, video_id: str) -> bool:
    """페이지가 머물러도 되는 주소인지(그 영상 페이지, 동의·로그인 화면, 빈 페이지)."""
    if url.startswith("about:"):
        return True
    if is_watch_url_for(url, video_id):
        return True
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in STAY_HOSTS


def normalize(text: str) -> str:
    return " ".join((text or "").split())


class PlaywrightYouTubeDriver(PlaywrightSandboxDriver):
    """내 채널 영상 한 편의 YouTube 페이지에서 입력·게시·확인한다."""

    guard_requests = False  # YouTube 페이지는 여러 주소에서 내용을 받는다. 대신 머무는 곳을 본다
    verify_timeout_ms = 15_000  # 「댓글」을 누른 뒤 내 댓글이 보이기를 기다리는 시간

    def __init__(
        self,
        *,
        video_id: str,
        headless: bool,
        window_position: tuple[int, int],
        rng: random.Random | None = None,
        prepare_context: Callable[[Any], None] | None = None,
        selectors: YouTubeSelectors = SELECTORS,
    ) -> None:
        if not is_video_id(video_id):
            raise ValueError(f"영상 ID 형식이 아닙니다: {video_id!r}")
        super().__init__(headless=headless, window_position=window_position, rng=rng)
        self.video_id = video_id
        self.prepare_context = prepare_context  # 테스트: 가짜 페이지를 끼워 넣는 자리
        self.sel = selectors
        self.left_page = ""  # 머물면 안 되는 곳으로 옮겨 간 주소

    # ------------------------------------------------------------ 열기

    def open(self, user_data_dir: Path, url: str) -> None:
        if not is_watch_url_for(url, self.video_id):
            raise ValueError(f"내 채널 영상 주소가 아니라 열지 않습니다: {url!r}")
        from playwright.sync_api import Error as PlaywrightError

        self._launch(user_data_dir)
        if self.prepare_context is not None:
            self.prepare_context(self._ctx)
        try:
            self._page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError:
            raise DriverError("YouTube 영상 페이지를 열지 못했습니다.", screenshot=False) from None
        self._require_signed_in()
        self._find_comment_box()

    def _on_navigated(self, frame: Any) -> None:
        super()._on_navigated(frame)
        if frame == self._page.main_frame and not may_stay(frame.url, self.video_id):
            self.left_page = frame.url

    def _check_page(self) -> None:
        if self.left_page:
            raise DriverError(TEXT_LEFT_PAGE)

    def _require_signed_in(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        sel = self.sel
        try:
            self._page.wait_for_selector(
                f"{sel.signed_in}, {sel.sign_in}", state="attached", timeout=SIGN_IN_WAIT_MS
            )
        except PlaywrightError:
            return  # 둘 다 못 찾으면(화면이 바뀐 경우) 댓글 상자에서 다시 본다
        if self._page.locator(sel.signed_in).count() == 0:
            raise DriverError(TEXT_NOT_SIGNED_IN, screenshot=False)

    def _find_comment_box(self) -> None:
        """댓글은 아래로 내려야 불러온다. 「댓글 추가...」가 보일 때까지 조금씩 내린다."""
        from playwright.sync_api import Error as PlaywrightError

        page, sel = self._page, self.sel
        try:
            for _ in range(FIND_BOX_TRIES):
                self._check_page()
                if page.locator(sel.placeholder).first.is_visible():
                    return
                if page.locator(sel.comments_off).count() > 0:
                    raise DriverError(TEXT_COMMENTS_OFF)
                signed_out = page.locator(sel.sign_in).count() > 0
                if signed_out and page.locator(sel.signed_in).count() == 0:
                    raise DriverError(TEXT_NOT_SIGNED_IN, screenshot=False)
                page.mouse.wheel(0, SCROLL_PX)
                page.wait_for_timeout(SCROLL_PAUSE_MS)
        except PlaywrightError:
            raise DriverError(TEXT_NO_BOX) from None
        raise DriverError(TEXT_NO_BOX)

    # ------------------------------------------------------------ 입력·게시·확인

    def type_comment(
        self, text: str, delay_ms: tuple[int, int], should_stop: Callable[[], bool]
    ) -> None:
        """「댓글 추가...」를 눌러 상자를 열고 한 글자씩 입력한다."""
        from playwright.sync_api import Error as PlaywrightError

        page, sel = self._page, self.sel
        lo, hi = delay_ms
        self._check_page()
        try:
            page.locator(sel.placeholder).first.click()
            editor = page.locator(sel.editor).first
            editor.wait_for(state="visible")
            editor.click()
            for ch in text:
                if should_stop():
                    raise Stopped
                page.keyboard.type(ch)
                page.wait_for_timeout(self.rng.randint(lo, hi))
            typed = editor.inner_text()
        except PlaywrightError:
            raise DriverError("YouTube 댓글 상자에 입력하지 못했습니다.") from None
        if normalize(typed) != normalize(text):
            raise DriverError("YouTube 댓글 상자에 들어간 글이 승인한 초안과 다릅니다.")

    def click_post(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        self._check_page()
        try:
            self._page.locator(self.sel.submit).first.click(timeout=5_000)
        except PlaywrightError:
            raise DriverError("YouTube 「댓글」 단추를 찾지 못했거나 누르지 못했습니다.") from None

    def verify_posted(self, text: str) -> None:
        """댓글 목록에서 방금 단 글을 찾는다(공백 차이는 무시)."""
        from playwright.sync_api import Error as PlaywrightError

        script = """([selector, text]) => {
          const norm = (s) => (s || '').split(/\\s+/).filter(Boolean).join(' ');
          const want = norm(text);
          return [...document.querySelectorAll(selector)].some((n) => norm(n.textContent) === want);
        }"""
        try:
            self._page.wait_for_function(
                script, arg=[self.sel.comment_text, text], timeout=self.verify_timeout_ms
            )
        except PlaywrightError:
            raise DriverError("게시한 댓글을 YouTube 페이지에서 찾지 못했습니다.") from None
