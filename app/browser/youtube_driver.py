"""실제 게시 실행기 — 실제 YouTube 영상 페이지(Playwright 동기 API, R3).

**이번 작업의 그 영상 하나만** 연다. 실행기를 만들 때 영상 ID를 정하고, `open()`은 그 영상의
`https://www.youtube.com/watch?v=<ID>` 주소가 아니면 열기 전에 거절한다. 페이지가 다른 곳으로
옮겨 가면(다른 영상·바깥 사이트) 다음 단계에서 멈춘다. 어떤 영상이든 되지만(R3, 내 채널 영상 구분
없음), 사람이 [댓글 달기]를 누른 그 댓글·그 영상에서만 돈다(작업 서비스 `app/browser/jobs.py`).

순서는 연습 페이지 실행기와 같다: 프로필로 크롬 열기 → 로그인 표시 확인 → 댓글 영역까지 내리기 →
「댓글 추가...」 누르기 → 한 글자씩 입력 → (게시 직전 확인을 켰으면 사람의 [게시]를 기다림) →
「댓글」 누르기 → 내 댓글 찾기.

- 프로필이 YouTube에 로그인돼 있지 않으면 입력하지 않고 멈춘다(`DriverError.code == "signed_out"`).
- 화면 요소 이름은 `SELECTORS` 한곳에 모았다. 글자(「댓글 추가...」 등)가 아니라 언어와 상관없는
  요소 이름(id·태그)으로 잡으므로 한국어 화면에서도 영어 화면에서도 같다. YouTube 화면이 바뀌면
  여기만 고친다. 못 찾으면 **어느 요소를 못 찾았는지**(`missing_text`)를 실패 사유에 적는다.
  실제 화면에서 잡히는지는 `scripts/check_youtube_page.py`(읽기만)로 본다.
- 자동 테스트는 같은 이름을 쓴 가짜 페이지(`tests/fixtures/fake_youtube_watch.html`)를
  `prepare_context`로 끼워 넣어 돈다(실제 YouTube에 접속하지 않는다).
- Playwright는 스레드에 안전하지 않으므로 작업 서비스의 전용 작업 스레드에서만 만들고 쓴다.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, fields
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
CLICK_TIMEOUT_MS = 5_000

CODE_SIGNED_OUT = "signed_out"
CODE_COMMENTS_OFF = "comments_off"
CODE_MISSING = "missing"

TEXT_NOT_SIGNED_IN = (
    "이 프로필이 유튜브에 로그인돼 있지 않습니다. 프로필 화면에서 [로그인하기]를 눌러 "
    "로그인한 뒤 다시 시도해 주세요."
)
TEXT_COMMENTS_OFF = "이 영상은 댓글을 쓸 수 없게 막혀 있습니다. 다른 영상을 골라 주세요."
TEXT_LEFT_PAGE = "유튜브 페이지가 이번 영상이 아닌 다른 곳으로 옮겨 가 멈췄습니다."
TEXT_OPEN_FAILED = "유튜브 영상 페이지를 열지 못했습니다. 인터넷 연결을 확인해 주세요."
TEXT_TYPE_FAILED = "유튜브 글 입력 칸에 입력하지 못했습니다."
TEXT_TYPED_DIFFERENT = "유튜브 글 입력 칸에 들어간 글이 [댓글 달기]를 누른 초안과 다릅니다."
TEXT_CLICK_FAILED = "유튜브 「댓글」 게시 단추를 누르지 못했습니다."
TEXT_NOT_FOUND_AFTER_POST = "게시한 댓글을 유튜브 페이지에서 찾지 못했습니다."


@dataclass(frozen=True)
class YouTubeSelectors:
    signed_in: str = "#avatar-btn"  # 로그인했을 때 오른쪽 위 내 사진
    sign_in: str = 'a[href*="ServiceLogin"]'  # 로그인 안 했을 때 「로그인」
    comments: str = "ytd-comments#comments"  # 댓글 영역(아래로 내려야 불러온다)
    comments_off: str = "ytd-comments#comments ytd-message-renderer"  # 「댓글이 사용 중지됨」
    placeholder: str = "#simplebox-placeholder"  # 「댓글 추가...」
    editor: str = "ytd-commentbox #contenteditable-root"  # 「댓글 추가...」를 누르면 나오는 글 칸
    submit: str = "ytd-commentbox #submit-button"  # 「댓글」 게시 단추
    comment_text: str = "ytd-comments#comments #content-text"  # 달린 댓글의 글
    # R2 로그인 확인(읽기만): 계정 이름. 유튜브가 계정 메뉴에 쓰는 정보 주소(같은 사이트, GET)와,
    # 그것을 못 읽을 때 볼 화면 요소(계정 메뉴가 그려져 있을 때만 있다)
    account_endpoint: str = "/getAccountSwitcherEndpoint"
    account_name: str = "#account-name"


SELECTORS = YouTubeSelectors()

# 요소마다 사람이 읽는 이름(실패 사유와 점검 도구의 표에 쓴다)
LABELS: dict[str, str] = {
    "signed_in": "로그인 표시(오른쪽 위 내 사진)",
    "sign_in": "「로그인」 단추",
    "comments": "댓글 영역",
    "comments_off": "「댓글 사용 중지」 안내",
    "placeholder": "댓글 입력 자리(「댓글 추가...」)",
    "editor": "글 입력 칸",
    "submit": "「댓글」 게시 단추",
    "comment_text": "달린 댓글의 글",
    "account_endpoint": "계정 정보 주소",
    "account_name": "계정 이름",
}
assert set(LABELS) == {f.name for f in fields(YouTubeSelectors)}


def missing_text(key: str, selectors: YouTubeSelectors = SELECTORS) -> str:
    """「어느 요소를 못 찾았는지」를 담은 실패 사유."""
    return (
        f"유튜브 화면에서 찾지 못한 요소: {LABELS[key]}(요소 이름 {getattr(selectors, key)}). "
        "유튜브 화면이 바뀌었을 수 있습니다. 화면 캡처를 확인해 주세요."
    )


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
    """영상 한 편의 YouTube 페이지에서 입력·게시·확인한다(그 영상 주소만)."""

    guard_requests = False  # YouTube 페이지는 여러 주소에서 내용을 받는다. 대신 머무는 곳을 본다
    verify_timeout_ms = 15_000  # 「댓글」을 누른 뒤 내 댓글이 보이기를 기다리는 시간

    def __init__(
        self,
        *,
        video_id: str,
        headless: bool,
        window_position: tuple[int, int] | None,
        rng: random.Random | None = None,
        prepare_context: Callable[[Any], None] | None = None,
        selectors: YouTubeSelectors = SELECTORS,
        window_size: tuple[int, int] | None = None,
        window_target: Any = None,
    ) -> None:
        if not is_video_id(video_id):
            raise ValueError(f"영상 ID 형식이 아닙니다: {video_id!r}")
        super().__init__(headless=headless, window_position=window_position, rng=rng,
                         window_size=window_size, window_target=window_target)
        self.video_id = video_id
        self.prepare_context = prepare_context  # 테스트: 가짜 페이지를 끼워 넣는 자리
        self.sel = selectors
        self.left_page = ""  # 머물면 안 되는 곳으로 옮겨 간 주소

    def _missing(self, key: str) -> DriverError:
        return DriverError(missing_text(key, self.sel), code=CODE_MISSING)

    # ------------------------------------------------------------ 열기

    def open(self, user_data_dir: Path, url: str) -> None:
        if not is_watch_url_for(url, self.video_id):
            raise ValueError(f"이번 작업의 영상 주소가 아니라 열지 않습니다: {url!r}")
        from playwright.sync_api import Error as PlaywrightError

        self._launch(user_data_dir)
        if self.prepare_context is not None:
            self.prepare_context(self._ctx)
        try:
            self._page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError:
            raise DriverError(TEXT_OPEN_FAILED, screenshot=False) from None
        self._check_page()
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
            return  # 둘 다 못 찾으면(화면이 바뀐 경우) 댓글 영역에서 다시 본다
        if self._page.locator(sel.signed_in).count() == 0:
            raise DriverError(TEXT_NOT_SIGNED_IN, code=CODE_SIGNED_OUT)

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
                    raise DriverError(TEXT_COMMENTS_OFF, code=CODE_COMMENTS_OFF)
                signed_out = page.locator(sel.sign_in).count() > 0
                if signed_out and page.locator(sel.signed_in).count() == 0:
                    raise DriverError(TEXT_NOT_SIGNED_IN, code=CODE_SIGNED_OUT)
                page.mouse.wheel(0, SCROLL_PX)
                page.wait_for_timeout(SCROLL_PAUSE_MS)
            has_comments = page.locator(sel.comments).count() > 0
        except PlaywrightError:
            raise self._missing("comments") from None
        raise self._missing("placeholder" if has_comments else "comments")

    # ------------------------------------------------------------ 입력·게시·확인

    def type_comment(
        self, text: str, delay_ms: tuple[int, int], should_stop: Callable[[], bool]
    ) -> None:
        """「댓글 추가...」를 눌러 글 칸을 열고 한 글자씩 입력한다."""
        from playwright.sync_api import Error as PlaywrightError

        page, sel = self._page, self.sel
        lo, hi = delay_ms
        self._check_page()
        try:
            page.locator(sel.placeholder).first.click(timeout=CLICK_TIMEOUT_MS)
        except PlaywrightError:
            raise self._missing("placeholder") from None
        editor = page.locator(sel.editor).first
        try:
            editor.wait_for(state="visible")
        except PlaywrightError:
            raise self._missing("editor") from None
        try:
            editor.click()
            for ch in text:
                if should_stop():
                    raise Stopped
                page.keyboard.type(ch)
                page.wait_for_timeout(self.rng.randint(lo, hi))
            typed = editor.inner_text()
        except PlaywrightError:
            raise DriverError(TEXT_TYPE_FAILED) from None
        self._check_page()
        if normalize(typed) != normalize(text):
            raise DriverError(TEXT_TYPED_DIFFERENT)

    def click_post(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        self._check_page()
        submit = self._page.locator(self.sel.submit).first
        try:
            if self._page.locator(self.sel.submit).count() == 0:
                raise self._missing("submit")
            submit.click(timeout=CLICK_TIMEOUT_MS)
        except PlaywrightError:
            raise DriverError(TEXT_CLICK_FAILED) from None

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
            raise DriverError(TEXT_NOT_FOUND_AFTER_POST) from None
