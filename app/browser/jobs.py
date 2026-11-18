"""게시 작업(job) 서비스 — 8단계(DESIGN 6.2 · PLAYBOOK 8단계), R3에서 실제 게시를 기본으로.

```text
start(video_id, draft_id, profile, target) -> job_id
                                시작 전 확인 → rules.reserve → 작업 스레드에
approve(job_id)                 게시 직전 확인(설정 켬)에서 사람이 [게시]
cancel(job_id)
get(job_id) -> JobView          상태, 지난 단계, 메시지, 실패 사유, 캡처 유무, 댓글 보기 주소
```

게시 방식은 둘(R3):
- **실제 게시**(`youtube`, 기본): 고른 프로필의 크롬으로 **그 영상의 유튜브 주소 하나만** 열어
  (`youtube_driver.PlaywrightYouTubeDriver`) 한 글자씩 입력하고 「댓글」을 누르고 내 댓글을 찾는다.
  어떤 영상이든 된다. 옛 대상 이름 `assist`·`youtube_auto`도 실제 게시로 받는다.
- **연습 모드**(`sandbox`): 이 앱의 `/sandbox/watch` 주소만 연다
  (`sandbox_driver.require_sandbox_url`).

상태: 대기(queued) → 프로필 여는 중(launching) → 입력 중(typing)
→ [게시 직전 확인을 켰을 때만] 게시 대기(awaiting_approval)
→ 게시 중(posting) → 확인 중(verifying) → 게시 완료(posted) / 실패(failed).

- **[댓글 달기] 한 번으로 끝까지.** 사람이 [댓글 달기]를 누르면 화면이 그 초안을 승인하고
  작업을 시작한다. 서버는 승인한 초안만 받는다(`rules.reserve`가 승인 여부를 본다 — 승인은 규칙
  검사를 통과한 글만 된다). 설정 「게시 직전 확인」(`confirm_before_post`, 기본 끔)을 켜면 입력 뒤
  멈추고, 화면의 [게시](`approve()`)를 받아야 「댓글」을 누른다.
- **시작 전 확인**(하나라도 걸리면 아무것도 남기지 않고 거절): 한 번에 작업 하나 · 댓글이 막힌
  영상(맥락을 모을 때 YouTube가 알려 준 것) · 자동 입력 도구와 크롬 · 프로필(실제 게시는 최근 로그인
  확인에서 로그인 안 됨으로 나온 프로필이면 「로그인하기」 안내, 확인한 적이 없거나 오래됐으면
  실행기가 열 때 직접 본다) · 그 프로필 창이 열려 있지 않은지 · 승인한 초안 · 영상당 1개 ·
  오늘 상한.
- 작업은 **전용 작업 스레드 하나**에서 돈다. Playwright는 그 스레드에서만 만들고 쓴다
  (스레드에 안전하지 않다). 그래서 다른 스레드(API 요청)는 이벤트 깃발만 세운다.
- 상태가 바뀔 때마다 `job_events`에 한 줄. 끝나면 `rules.mark_posted` / `mark_failed`가
  상태를 바꾸는 같은 거래 안에서 작업 기록(`runs`)에 결과 한 줄을 남긴다(그 댓글이 광고 표기를
  붙였는지도). `Ledger.record`를 따로 부르지 않는다 — 부르면 같은 결과가 두 줄 생긴다.
- 실패하면 사유와 `error_screenshots/<작업ID>.png`(크롬 화면이 열린 뒤 실패한 경우).
- 실제 게시에서 「댓글」을 누른 뒤에는 페이지·Data API로 못 찾아도 실패로 되돌리지 않고
  「게시됨(확인 못 함)」으로 남긴다(다시 시도해 같은 댓글이 두 번 달리지 않게).
- 실행기가 로그인 안 됨을 보면 그 프로필의 로그인 확인 결과(`profile_logins`)를 「로그인 안 됨」으로
  고쳐 둔다(프로필 화면에 바로 보인다).
- **작업 스레드에서 도는 짧은 일(R2).** 프로필 로그인 확인처럼 Playwright를 쓰는 다른 일도
  `run_task(fn)`로 같은 작업 스레드에서 돌린다. 게시 작업이 진행 중이면 받지 않고, 도는 동안에는
  새 게시를 받지 않는다. `busy()`는 둘 중 하나라도 돌고 있는지, `close_if_idle()`은 쉬고 있을 때만
  더 받지 않게 닫는다(설정을 저장해 서비스를 다시 만들 때).
- **창 위치(2026-11-17 자동).** 창이 보이는 실행은 작업을 시작할 때마다 모니터를 다시 읽어
  `placement.plan_window`로 정한다(기본 자동, 고른 모니터가 없으면 자동으로 떨어지고 기록에 한 줄).
  크기도 그 모니터 작업 영역에 맞춘다. 아래 9단계 확인은 옛 좌표가 남아 있을 때만 쓴다.
- **창 위치(9단계).** 창이 보이는 실행(headless가 아닐 때)은 띄우기 전에 `browser.window_position`이
  실제 모니터 안인지 본다(`screens.check_window_position`). 밖이면 주 모니터의 안전한 위치로 바꿔
  띄우고 작업 기록(job_events)에 그렇게 했다고 남긴다.
- 프로그램 창을 닫으면(`shutdown`) 진행 중인 작업을 취소하고 크롬을 닫는다.
- **게시 뒤 크롬 창 열어 두기(2026-11-18 대표).** 「댓글」을 누른 뒤(내 댓글을 찾았든 못 찾았든)
  설정 `posting.keep_window_seconds`(기본 300초, 0이면 바로 닫기)가 있으면 내 댓글을 화면 가운데로
  내려 두고 창을 닫지 않는다. 작업은 바로 「게시 완료」로 끝나고(`busy()`가 아님) 더는 아무것도
  누르지 않는다. 창은 작업 스레드가 쥐고 있다가(Playwright는 만든 스레드에서만 닫는다) 사람이 창을
  닫거나 · 다음 브라우저 일(게시 · 로그인 확인 · [로그인하기] · [유튜브 열기] — `release_window()`로
  먼저 닫고 닫힌 것을 확인) · 프로그램 종료 · 시간이 다 되면 닫는다. 게시 전에 실패하면 예전대로
  캡처하고 닫는다.
"""

from __future__ import annotations

import importlib.util
import logging
import queue
import random
import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from app import db
from app.browser.chrome import ensure_profile_dir, require_profile_free
from app.browser.placement import WindowPlan, plan_window
from app.browser.sandbox_driver import (
    LOCAL_HOSTS,
    BrowserDriver,
    DriverError,
    PlaywrightSandboxDriver,
    Stopped,
    require_sandbox_url,
)
from app.browser.screens import Monitor
from app.config import BrowserSettings
from app.errors import AppError, ErrorKind
from app.ops.profiles import ProfileService
from app.ops.rules import PostRules
from app.youtube.quota import Clock, utc_now
from app.youtube.url_parser import is_video_id, watch_url

log = logging.getLogger("app.browser.jobs")
_KST = timezone(timedelta(hours=9))  # 작업 ID의 시각(한국)

STATES = (
    "queued",
    "launching",
    "typing",
    "awaiting_approval",
    "posting",
    "verifying",
    "posted",
    "failed",
)
FINAL_STATES = ("posted", "failed")
# 과제 PDF의 말: 프로필 여는 중 → 입력 중 → 게시 완료
STATE_LABELS = {
    "queued": "준비 중",
    "launching": "프로필 여는 중",
    "typing": "입력 중",
    "awaiting_approval": "게시 대기",
    "posting": "게시 중",
    "verifying": "내 댓글 확인 중",
    "posted": "게시 완료",
    "failed": "실패",
}
# 진행 단계 표시(대기 · 프로필 여는 중 · 입력 중 · 게시 대기 · 게시 · 확인)에서 지금 칸(0~5).
# 게시 완료는 6(모두 지남). 게시 직전 확인을 끈 작업은 3번 칸을 건너뛴다
STEP_INDEX = {
    "queued": 0,
    "launching": 1,
    "typing": 2,
    "awaiting_approval": 3,
    "posting": 4,
    "verifying": 5,
    "posted": 6,
}
MODES = ("sandbox", "youtube")  # 연습 모드 | 실제 게시
APPROVAL_TIMEOUT_SECONDS = 5 * 60  # 게시 직전 확인(켬): [게시]를 기다리는 시간
STALE_AFTER = timedelta(minutes=15)  # 이보다 오래 예약으로 남은 게시는 꺼진 작업의 흔적으로 본다
# 이보다 최근에 「로그인 안 됨」으로 확인된 프로필은 시작 전에 막는다(오래됐으면 실행기가 직접 본다)
LOGIN_TRUST = timedelta(hours=1)
KEEP_JOBS = 50
WAIT_STEP_SECONDS = 0.1

REASON_APPROVAL_TIMEOUT = "게시 대기 시간 초과(5분 안에 [게시]를 누르지 않았습니다)"
REASON_CANCELLED = "사용자가 게시를 그만뒀습니다"
REASON_STALE = "프로그램이 게시 작업 중에 꺼졌습니다"
NOTE_UNVERIFIED = "게시됨(확인 못 함)"
# 게시 뒤 크롬 창(2026-11-18 대표): 기본 5분 열어 두기. 작업 스레드는 이 간격으로 창이 닫혔는지 본다
KEEP_WINDOW_SECONDS = 300
LINGER_POLL_SECONDS = 0.25
RELEASE_TIMEOUT_SECONDS = 15.0
MSG_WINDOW_OPEN = "크롬 창에 내 댓글이 떠 있습니다 · 다음 일을 시작하면 닫힙니다"
# 창을 닫은 까닭(job_events에 「크롬 창을 닫았습니다(…)」로 남는다)
CLOSED_BY_PERSON = "사람이 닫음"
CLOSED_BY_NEXT = "다음 일을 시작함"
CLOSED_BY_TIMEOUT = "열어 둔 시간이 다 됨"
CLOSED_BY_SHUTDOWN = "프로그램을 닫음"


def mode_of(target: str) -> tuple[str, str]:
    """화면·API의 대상 이름 → (게시 방식, 게시 기록의 대상).

    sandbox = 연습 모드. youtube = 실제 게시. 옛 이름 assist·youtube_auto도 실제 게시다(R3).
    """
    t = (target or "").strip().lower()
    if t == "sandbox":
        return "sandbox", "sandbox"
    if t in ("youtube", "assist", "youtube_auto"):
        return "youtube", "youtube"
    raise ValueError(f"알 수 없는 대상: {target!r} (youtube | sandbox)")


def new_job_id(clock: Clock) -> str:
    """파일 이름으로도 쓰는 작업 ID(영문·숫자·-만): 20261116-153012-a1b2c3."""
    stamp = clock().astimezone(_KST).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def is_job_id(value: str) -> bool:
    return bool(value) and len(value) <= 40 and all(c.isalnum() or c == "-" for c in value)


def sandbox_url(base_url: str, video_id: str, profile: str, fail: str = "") -> str:
    """이 앱의 연습 페이지 주소. `base_url`은 로컬 주소(http://127.0.0.1:포트)만."""
    parts = urlsplit(base_url)
    if parts.scheme != "http" or (parts.hostname or "").lower() not in LOCAL_HOSTS:
        raise ValueError(f"연습 페이지는 이 PC의 앱 주소에서만 엽니다: {base_url!r}")
    query = {"v": video_id, "profile": profile}
    if fail:
        query["fail"] = fail
    return require_sandbox_url(f"{base_url.rstrip('/')}/sandbox/watch?{urlencode(query)}")


class JobFailed(Exception):  # noqa: N818
    def __init__(self, reason: str, *, screenshot: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.screenshot = screenshot


class JobCancelled(Exception):  # noqa: N818
    pass


@dataclass
class JobEvent:
    at: str
    state: str
    message: str


@dataclass
class Job:
    id: str
    mode: str  # sandbox | youtube
    target: str  # sandbox | youtube (게시 기록의 대상)
    video_id: str
    draft_id: int
    post_id: int
    profile: str
    folder: str
    comment_text: str
    open_url: str  # 크롬이 여는 주소(연습 페이지 / 그 영상의 유튜브 주소)
    view_url: str  # [댓글 보기] 주소
    created_at: str
    confirm_before_post: bool = False  # 입력 뒤 사람의 [게시]를 기다리는지(시작할 때의 설정)
    disclosed: bool = True  # 그 댓글이 광고 표기를 붙였는지
    state: str = "queued"
    message: str = ""
    reason: str = ""
    failed_step: int | None = None
    verified: bool | None = None  # 내 댓글을 찾았는지(실제 게시에서 못 찾으면 거짓)
    screenshot: Path | None = None
    finished_at: str | None = None
    deadline: float | None = None  # [게시]를 기다리는 마감(time.monotonic)
    events: list[JobEvent] = field(default_factory=list)
    approve_flag: threading.Event = field(default_factory=threading.Event)
    cancel_flag: threading.Event = field(default_factory=threading.Event)
    driver: Any = None  # 아직 닫지 않은 실행기(닫으면 None)
    chrome: Path | None = None  # chrome.exe 위치
    profile_path: Path | None = None  # 프로필 폴더(API에는 싣지 않는다)
    window_position: tuple[int, int] | None = None  # 실제로 띄운 창 위치(화면 밖이면 바꾼 값)
    window_open: bool = False  # 게시 뒤 크롬 창을 열어 둔 채인지(2026-11-18)

    @property
    def finished(self) -> bool:
        return self.state in FINAL_STATES


@dataclass(frozen=True)
class JobView:
    """API에 내보내는 작업 모습(복사본). PC의 경로는 싣지 않는다."""

    id: str
    mode: str
    target: str
    state: str
    state_label: str
    step: int  # 진행 단계 표시에서 지금 칸(0~5, 끝나면 6). 실패면 실패한 칸
    finished: bool
    video_id: str
    draft_id: int
    profile: str
    folder: str
    comment_text: str
    message: str
    reason: str
    verified: bool | None
    has_screenshot: bool
    view_url: str
    waiting_for: str | None  # approve | None
    seconds_left: int | None  # [게시] 마감까지 남은 초
    created_at: str
    finished_at: str | None
    events: list[JobEvent]
    confirm_before_post: bool = False
    disclosed: bool = True
    window_open: bool = False  # 게시 뒤 크롬 창이 아직 열려 있는지(닫히면 거짓)


VerifyComment = Callable[
    [str, str], bool | None
]  # (video_id, text) -> 찾음/못 찾음/확인 불가(None)
DriverFactory = Callable[[BrowserSettings], BrowserDriver]
# (브라우저 설정, 이번 작업의 영상 ID) -> 그 영상만 여는 실행기
YouTubeDriverFactory = Callable[[BrowserSettings, str], BrowserDriver]


def default_driver_factory(settings: BrowserSettings) -> BrowserDriver:
    return PlaywrightSandboxDriver(
        headless=settings.headless, window_position=settings.window_position,
        window_size=settings.window_size, window_target=settings.window_target,
    )


def default_youtube_driver_factory(settings: BrowserSettings, video_id: str) -> BrowserDriver:
    from app.browser.youtube_driver import PlaywrightYouTubeDriver

    return PlaywrightYouTubeDriver(
        video_id=video_id, headless=settings.headless, window_position=settings.window_position,
        window_size=settings.window_size, window_target=settings.window_target,
    )


class _Task:
    """작업 스레드에서 돌릴 짧은 일 하나(결과나 오류를 기다리는 쪽에 넘긴다)."""

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001 - 기다리는 쪽에서 다시 던진다
            self.error = exc
        finally:
            self.done.set()


class _Release:
    """열어 둔 크롬 창을 닫아 달라는 요청(작업 스레드가 닫고 `done`을 세운다)."""

    def __init__(self) -> None:
        self.done = threading.Event()


@dataclass
class _Linger:
    """게시 뒤 열어 둔 크롬 창(작업 스레드만 만지는 실행기와 마감)."""

    job: Job
    driver: Any
    deadline: float  # time.monotonic


def playwright_installed() -> bool:
    return importlib.util.find_spec("playwright") is not None


class JobService:
    def __init__(
        self,
        *,
        db_path: Path,
        rules: PostRules,
        profiles: ProfileService,
        browser: BrowserSettings,
        chrome_finder: Callable[[], Path | None],
        driver_factory: DriverFactory = default_driver_factory,
        verify_comment: VerifyComment | None = None,
        playwright_ready: Callable[[], bool] = playwright_installed,
        clock: Clock = utc_now,
        approval_timeout: float = APPROVAL_TIMEOUT_SECONDS,
        rng: random.Random | None = None,
        screens: Callable[[], Sequence[Monitor]] | None = None,
        app_monitor: Callable[[Sequence[Monitor]], Monitor | None] | None = None,
        youtube_driver_factory: YouTubeDriverFactory = default_youtube_driver_factory,
        confirm_before_post: bool = False,
        keep_window_seconds: float = 0,
    ) -> None:
        self.db_path = db_path
        # 게시 뒤 크롬 창을 열어 둘 시간(초). 0이면 예전처럼 바로 닫는다(2026-11-18 대표)
        self.keep_window_seconds = max(0.0, float(keep_window_seconds))
        self.youtube_driver_factory = youtube_driver_factory  # 실제 게시 실행기 만들기
        # 설정 「게시 직전 확인」(R3). 끄면(기본) 입력을 마치고 바로 「댓글」을 누른다
        self.confirm_before_post = bool(confirm_before_post)
        # 모니터 목록을 읽는 함수(9단계). None이면 확인하지 않고 설정값 그대로 띄운다
        self.screens = screens
        self.app_monitor = app_monitor  # 프로그램 창이 있는 모니터(자동 규칙, 모르면 None)
        self.rules = rules
        self.profiles = profiles
        self.browser = browser
        self.chrome_finder = chrome_finder
        self.driver_factory = driver_factory
        self.verify_comment = verify_comment
        self.playwright_ready = playwright_ready
        self.clock = clock
        self.approval_timeout = float(approval_timeout)
        self.rng = rng or random.Random()
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._active: Job | None = None
        self._queue: queue.Queue[Job | _Task | _Release | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._closed = False
        self._task: _Task | None = None  # 작업 스레드에서 도는 짧은 일(로그인 확인)
        self._linger: _Linger | None = None  # 게시 뒤 열어 둔 크롬 창(작업 스레드만 닫는다)

    # ------------------------------------------------------------ 시작

    def start(
        self,
        video_id: str,
        draft_id: int,
        profile: str | None,
        target: str,
        *,
        base_url: str = "",
        daily_limit: int | None = None,
        fail: str = "",
    ) -> str:
        """시작 전 확인을 하고 작업을 작업 스레드에 넣는다. 막히면 AppError(아무것도 안 남긴다).

        게시 뒤 열어 둔 크롬 창이 있으면 먼저 닫고 닫힌 것을 확인한다(프로필 폴더를 풀어 둔다)."""
        mode, post_target = mode_of(target)
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        self._release_or_fail()
        with self._lock:
            if self._closed:
                raise AppError(ErrorKind.JOB_BUSY, detail="프로그램을 닫는 중")
            if self._active is not None and not self._active.finished:
                raise AppError(
                    ErrorKind.JOB_BUSY,
                    detail=f"진행 중: {self._active.id}",
                    extra={"job_id": self._active.id},
                )
            if self._task is not None:
                raise AppError(ErrorKind.JOB_BUSY, detail="프로필 로그인을 확인하는 중")
            self.recover_stale()
            if self._rising_only(video_id):  # R4: 뜨기 직전 목록에서 고른 영상은 초안까지만
                raise AppError(ErrorKind.RISING_DRAFT_ONLY, detail=video_id)
            live = mode == "youtube"
            if live and self._comments_disabled(video_id):
                raise AppError(ErrorKind.COMMENTS_DISABLED, detail=video_id)
            if not self.playwright_ready():
                raise AppError(ErrorKind.PLAYWRIGHT_MISSING)
            chrome = self.chrome_finder()
            if chrome is None:
                raise AppError(ErrorKind.CHROME_NOT_FOUND)
            signed_out = self._recently_signed_out() if live else set()
            if not profile or profile == "auto":  # 실제 게시는 로그인이 확인된 프로필 중에서만
                chosen = self.profiles.choose_auto(
                    post_target, login=live, now=self.clock(), trust=LOGIN_TRUST
                ).profile
            else:
                chosen = self.profiles.get(profile)
            if chosen.name in signed_out:
                raise AppError(ErrorKind.PROFILE_NOT_SIGNED_IN, detail=chosen.name)
            folder_path = ensure_profile_dir(self.browser.profiles_root, chosen.folder)
            require_profile_free(folder_path)
            if mode == "sandbox":
                open_url = sandbox_url(base_url, video_id, chosen.name, fail)
                view_url = open_url.split("&fail=", 1)[0]
            else:
                open_url = view_url = watch_url(video_id)
            post_id = self.rules.reserve(
                video_id, post_target, chosen.name, int(draft_id), daily_limit=daily_limit
            )
            body, disclosed = self._draft(int(draft_id))
            job = Job(
                id=new_job_id(self.clock),
                mode=mode,
                target=post_target,
                video_id=video_id,
                draft_id=int(draft_id),
                post_id=post_id,
                profile=chosen.name,
                folder=chosen.folder,
                comment_text=body,
                open_url=open_url,
                view_url=view_url,
                created_at=self.clock().isoformat(),
                confirm_before_post=self.confirm_before_post,
                disclosed=disclosed,
                chrome=chrome,
                profile_path=folder_path,
            )
            self._jobs[job.id] = job
            self._active = job
            self._trim()
            self._event(job, "queued", "작업을 받았습니다")
            self._ensure_worker()
            self._queue.put(job)
            return job.id

    def _draft(self, draft_id: int) -> tuple[str, bool]:
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT body, disclosed FROM drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        return (row["body"], bool(row["disclosed"])) if row else ("", True)

    def _rising_only(self, video_id: str) -> bool:
        """마지막으로 불러온 목록이 뜨기 직전 영상이면 참(videos.source = 'rising')."""
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT source FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
        return bool(row and row["source"] == "rising")

    def _comments_disabled(self, video_id: str) -> bool:
        """맥락을 모을 때 YouTube가 「댓글 막힘」을 알려 준 영상인지."""
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT comments_disabled FROM video_context WHERE video_id = ?", (video_id,)
            ).fetchone()
        return bool(row and row["comments_disabled"])

    def _recently_signed_out(self) -> set[str]:
        """최근(`LOGIN_TRUST` 안에) 로그인 확인에서 「로그인 안 됨」으로 나온 프로필 이름들."""
        return self.profiles.login_sets(now=self.clock(), trust=LOGIN_TRUST)[1]

    def _save_signed_out(self, profile: str) -> None:
        """실행기가 로그인 안 됨을 봤다: 프로필 화면의 로그인 상태도 그렇게 고쳐 둔다."""
        now = self.clock().isoformat()
        try:
            with db.session(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO profile_logins(profile, state, channel, checked_at, note) "
                    "VALUES (?, 'signed_out', '', ?, '게시할 때 확인') "
                    "ON CONFLICT(profile) DO UPDATE "
                    "SET state='signed_out', channel='', checked_at=excluded.checked_at, "
                    "note=excluded.note",
                    (profile, now),
                )
        except Exception:  # 기록을 못 고쳐도 작업 실패 사유는 남는다
            log.exception("로그인 상태를 고치지 못했습니다(%s)", profile)

    # ------------------------------------------------------------ 사람의 응답

    def approve(self, job_id: str) -> JobView:
        """게시 직전 확인(설정 켬)에서 사람이 [게시]를 눌렀다."""
        with self._lock:
            job = self._require(job_id)
            if job.state != "awaiting_approval":
                raise AppError(
                    ErrorKind.JOB_WRONG_STATE, detail=f"지금 상태: {STATE_LABELS[job.state]}"
                )
            if not job.approve_flag.is_set():
                job.approve_flag.set()
                self._event(job, job.state, "사람이 [게시]를 눌렀습니다", change=False)
            return self._view(job)

    def confirm(self, job_id: str, posted: bool) -> JobView:  # noqa: ARG002 - 옛 API
        """옛 API(사람이 직접 게시하던 방식의 「게시했어요」).

        R3부터 그런 작업이 없어 늘 거절한다."""
        with self._lock:
            job = self._require(job_id)
            raise AppError(
                ErrorKind.JOB_WRONG_STATE, detail=f"지금 상태: {STATE_LABELS[job.state]}"
            )

    def cancel(self, job_id: str) -> JobView:
        with self._lock:
            job = self._require(job_id)
            if job.finished:
                raise AppError(ErrorKind.JOB_WRONG_STATE, detail="이미 끝난 작업")
            if not job.cancel_flag.is_set():
                job.cancel_flag.set()
                self._event(job, job.state, "그만두기 요청을 받았습니다", change=False)
            return self._view(job)

    # ------------------------------------------------------------ 조회

    def get(self, job_id: str) -> JobView:
        with self._lock:
            return self._view(self._require(job_id))

    def busy(self) -> bool:
        """게시 작업이나 작업 스레드의 짧은 일이 돌고 있는지."""
        with self._lock:
            job_running = self._active is not None and not self._active.finished
            return job_running or self._task is not None

    def task_running(self) -> bool:
        """작업 스레드에서 짧은 일(로그인 확인)이 도는지(게시 작업과 나눠 문구를 고른다)."""
        with self._lock:
            return self._task is not None

    def close_if_idle(self) -> bool:
        """쉬고 있으면 더 받지 않게 닫고 True. 무엇이 돌고 있으면 아무것도 안 하고 False."""
        with self._lock:
            if self._closed:
                return True
            job_running = self._active is not None and not self._active.finished
            if job_running or self._task is not None:
                return False
            self._closed = True
            return True

    def run_task(self, fn: Callable[[], Any], *, timeout: float = 90.0) -> Any:
        """`fn`을 작업 스레드에서 돌리고 결과를 돌려준다(Playwright는 그 스레드에서만 쓴다).

        게시 작업이 진행 중이거나 다른 짧은 일이 돌고 있으면 `profile_check_busy`.
        게시 뒤 열어 둔 크롬 창은 이 일보다 먼저 닫힌다(작업 스레드가 다음 일을 받을 때).
        """
        with self._lock:
            if self._closed:
                raise AppError(
                    ErrorKind.PROFILE_CHECK_BUSY,
                    message="프로그램을 닫는 중이라 지금은 로그인을 확인할 수 없습니다.",
                    action="프로그램을 다시 켠 뒤 [로그인 확인]을 눌러 주세요.",
                    detail="프로그램을 닫는 중",
                )
            job_running = self._active is not None and not self._active.finished
            if job_running:
                raise AppError(ErrorKind.PROFILE_CHECK_BUSY)  # 「게시 중」 문구 그대로
            if self._task is not None:
                raise AppError(
                    ErrorKind.PROFILE_CHECK_BUSY,
                    message="다른 로그인 확인이 아직 끝나지 않았습니다.",
                    action="잠시 뒤 [로그인 확인]을 다시 눌러 주세요.",
                    detail="다른 로그인 확인",
                )
            task = self._task = _Task(fn)
            self._ensure_worker()
            self._queue.put(task)
        try:
            if not task.done.wait(timeout):
                raise AppError(ErrorKind.PROFILE_CHECK_FAILED, detail="시간 초과")
        finally:
            with self._lock:
                if self._task is task and task.done.is_set():
                    self._task = None
        if task.error is not None:
            raise task.error
        return task.result

    def active_id(self) -> str | None:
        with self._lock:
            job = self._active
            return job.id if job is not None and not job.finished else None

    def screenshot_path(self, job_id: str) -> Path:
        """실패 화면 캡처 파일. 메모리에 없는 지난 작업(앱을 다시 켠 뒤, 9단계 전체 기록)은
        캡처 폴더의 `<작업ID>.png`를 찾는다(작업 ID 모양이 아니면 job_not_found)."""
        with self._lock:
            job = self._jobs.get(job_id)
            path = job.screenshot if job is not None else None
        if job is None:
            if not is_job_id(job_id):
                raise AppError(ErrorKind.JOB_NOT_FOUND)
            path = Path(self.browser.screenshot_dir) / f"{job_id}.png"
        if path is None or not path.is_file():
            raise AppError(ErrorKind.SCREENSHOT_NOT_FOUND)
        return path

    def wait(self, job_id: str, timeout: float = 30.0) -> JobView:
        """작업이 끝날 때까지 기다린다(테스트·스크립트용)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            view = self.get(job_id)
            if view.finished:
                return view
            time.sleep(0.02)
        return self.get(job_id)

    def wait_for_state(self, job_id: str, state: str, timeout: float = 30.0) -> JobView:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            view = self.get(job_id)
            if view.state == state or view.finished:
                return view
            time.sleep(0.02)
        return self.get(job_id)

    def _require(self, job_id: str) -> Job:
        job = self._jobs.get(job_id) if is_job_id(job_id) else None
        if job is None:
            raise AppError(ErrorKind.JOB_NOT_FOUND)
        return job

    def _view(self, job: Job) -> JobView:
        waiting = "approve" if job.state == "awaiting_approval" else None
        left = None
        if waiting and job.deadline is not None:
            left = max(0, int(job.deadline - time.monotonic()))
        step = job.failed_step if job.state == "failed" else STEP_INDEX[job.state]
        return JobView(
            id=job.id,
            mode=job.mode,
            target=job.target,
            state=job.state,
            state_label=STATE_LABELS[job.state],
            step=step if step is not None else 0,
            finished=job.finished,
            video_id=job.video_id,
            draft_id=job.draft_id,
            profile=job.profile,
            folder=job.folder,
            comment_text=job.comment_text,
            message=job.message,
            reason=job.reason,
            verified=job.verified,
            has_screenshot=bool(job.screenshot and job.screenshot.is_file()),
            view_url=job.view_url,
            waiting_for=waiting,
            seconds_left=left,
            created_at=job.created_at,
            finished_at=job.finished_at,
            events=list(job.events),
            confirm_before_post=job.confirm_before_post,
            disclosed=job.disclosed,
            window_open=job.window_open,
        )

    # ------------------------------------------------------------ 기록

    def _event(
        self,
        job: Job,
        state: str,
        message: str,
        *,
        change: bool = True,
        deadline: float | None = None,
    ) -> None:
        """상태를 바꾸고(change) job_events에 한 줄 남긴다.

        `deadline`: 사람의 응답을 기다리는 마감(time.monotonic). 상태와 같은 잠금 안에서 정한다
        — 「게시 대기」를 읽었는데 남은 시간이 비어 있는 틈이 없게(2026-11-18)."""
        stamp = self.clock().isoformat()
        with self._lock:
            if change:
                job.state = state
                job.message = message
                if deadline is not None:
                    job.deadline = deadline
            job.events.append(JobEvent(stamp, state, message))
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO job_events(job_id, at, state, message) VALUES (?,?,?,?)",
                (job.id, stamp, state, message),
            )

    def events_in_db(self, job_id: str) -> list[JobEvent]:
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT at, state, message FROM job_events WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return [JobEvent(r["at"], r["state"], r["message"]) for r in rows]

    def _trim(self) -> None:
        done = [j for j in self._jobs.values() if j.finished]
        for job in done[: max(0, len(self._jobs) - KEEP_JOBS)]:
            self._jobs.pop(job.id, None)

    def recover_stale(self) -> int:
        """작업 없이 오래 예약으로 남은 게시(프로그램이 작업 중에 꺼진 흔적)를 실패로 푼다.

        풀어야 그 영상을 다시 시도할 수 있고 오늘 상한에서도 빠진다.
        진행 중인 작업의 예약은 건드리지 않는다.
        """
        cutoff = (self.clock() - STALE_AFTER).isoformat()
        live = {j.post_id for j in self._jobs.values() if not j.finished}
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM posts WHERE status='reserved' AND updated_at < ?", (cutoff,)
            ).fetchall()
        count = 0
        for row in rows:
            if int(row["id"]) in live:
                continue
            try:
                self.rules.mark_failed(int(row["id"]), REASON_STALE)
                count += 1
            except (LookupError, ValueError):
                continue
        return count

    # ------------------------------------------------------------ 작업 스레드

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._work_loop, name="jg-browser-worker", daemon=True
            )
            self._worker.start()

    def _work_loop(self) -> None:
        while True:
            if self._linger is None:
                job = self._queue.get()
            else:  # 열어 둔 창이 있다: 사람이 닫았는지·시간이 다 됐는지 보면서 다음 일을 기다린다
                try:
                    job = self._queue.get_nowait()
                except queue.Empty:
                    self._tend_linger()
                    continue
            # 다음 일(게시 · 짧은 일 · 닫기 요청 · 멈춤)보다 열어 둔 창을 먼저 닫는다
            self._end_linger(CLOSED_BY_SHUTDOWN if job is None else CLOSED_BY_NEXT)
            if job is None:
                return
            if isinstance(job, _Release):
                job.done.set()
                continue
            if isinstance(job, _Task):
                job.run()
                with self._lock:
                    if self._task is job:
                        self._task = None
                continue
            self._run(job)

    def _tend_linger(self) -> None:
        """열어 둔 창을 잠깐 지켜본다(작업 스레드). 사람이 닫았거나 시간이 다 됐으면 닫는다."""
        linger = self._linger
        if linger is None:
            return
        left = linger.deadline - time.monotonic()
        if left <= 0:
            self._end_linger(CLOSED_BY_TIMEOUT)
            return
        step = min(LINGER_POLL_SECONDS, left)
        wait_closed = getattr(linger.driver, "wait_closed", None)
        try:
            if callable(wait_closed):
                closed = bool(wait_closed(step))  # Playwright 이벤트도 이때 받는다
            else:
                time.sleep(step)
                closed = False
        except Exception:  # 창 상태를 못 읽으면 닫힌 것으로 본다(남는 것이 없게 마저 닫는다)
            closed = True
        if closed:
            self._end_linger(CLOSED_BY_PERSON)

    def _end_linger(self, why: str) -> None:
        """열어 둔 창을 닫는다(작업 스레드에서만 부른다). 없으면 아무것도 안 한다.

        다 닫은 뒤에야 `_linger`를 비운다 — 그 사이 다른 스레드의 `release_window()`가
        「창 없음」으로 보고 프로필 폴더를 쓰려 들지 않게(닫기 요청은 큐에 들어가 이 닫기 뒤에
        답을 받는다)."""
        linger = self._linger
        if linger is None:
            return
        job = linger.job
        try:
            linger.driver.close()
        except Exception:
            log.exception("job %s: 열어 둔 크롬 창을 닫지 못했습니다", job.id)
        with self._lock:
            self._linger = None
            job.window_open = False
            if job.driver is linger.driver:
                job.driver = None
        try:
            self._event(job, job.state, f"크롬 창을 닫았습니다({why})", change=False)
        except Exception:  # 기록을 못 남겨도 창은 닫혔다
            log.exception("job %s: 창 닫힘을 기록하지 못했습니다", job.id)

    def window_open(self) -> bool:
        """게시 뒤 열어 둔 크롬 창이 있는지."""
        with self._lock:
            return self._linger is not None

    def release_window(self, timeout: float = RELEASE_TIMEOUT_SECONDS) -> bool:
        """열어 둔 크롬 창을 닫고 닫힐 때까지 기다린다(다른 브라우저 일을 시작하기 전).

        창이 없으면 바로 True. 닫는 것은 작업 스레드다(Playwright는 만든 스레드에서만 닫는다).
        잠금을 쥔 채 부르지 않는다(작업 스레드가 닫으면서 잠금을 잠깐 쓴다)."""
        with self._lock:
            if self._linger is None:
                return True
            worker = self._worker
            request = _Release()
            self._queue.put(request)
        if worker is None or not worker.is_alive():
            return True
        return request.done.wait(timeout)

    def _release_or_fail(self) -> None:
        if not self.release_window():
            raise AppError(ErrorKind.JOB_BUSY, detail="게시 뒤 열어 둔 크롬 창을 닫는 중")

    def _run(self, job: Job) -> None:
        driver: BrowserDriver | None = None
        try:
            if job.cancel_flag.is_set():
                raise JobCancelled
            browser = self.browser
            if not browser.headless:  # 창이 보일 때만 위치를 정한다(작업마다 모니터를 다시 읽는다)
                plan = self._place_window(job)
                browser = replace(browser, window_position=plan.position, window_size=plan.size,
                                  window_target=plan.target)
            if job.mode == "sandbox":
                driver = job.driver = self.driver_factory(browser)
            else:
                driver = job.driver = self.youtube_driver_factory(browser, job.video_id)
            self._run_steps(job, driver)
        except JobCancelled:
            self._fail(job, REASON_CANCELLED, driver=driver, screenshot=False)
        except JobFailed as exc:
            self._fail(job, exc.reason, driver=driver, screenshot=exc.screenshot)
        except Exception as exc:  # 예상 못 한 오류도 작업을 실패로 끝내고 예약을 푼다
            log.exception("job %s crashed", job.id)
            self._fail(job, f"예상하지 못한 오류: {type(exc).__name__}", driver=driver)
        finally:
            if self._linger is None or self._linger.job is not job:
                self._close_driver(job)

    def _place_window(self, job: Job) -> WindowPlan:
        """창을 띄울 곳(자동 · 고른 모니터 · 옛 좌표). 바꾸거나 떨어지면 기록에 한 줄 남긴다."""
        b = self.browser
        monitors: list[Monitor] = []
        if self.screens is not None:
            try:
                monitors = list(self.screens())
            except Exception:  # 모니터를 못 읽어도 작업은 계속한다(크롬이 정하는 곳)
                log.exception("job %s: 모니터 정보를 읽지 못했습니다", job.id)
        app_monitor = None
        if self.app_monitor is not None and monitors:
            try:
                app_monitor = self.app_monitor(monitors)
            except Exception:
                app_monitor = None
        plan = plan_window(monitors, screen=b.window_screen, legacy=b.window_position,
                           app_monitor=app_monitor)
        if plan.mode == "unknown" and self.screens is None:
            plan = replace(plan, note="")  # 모니터를 읽는 곳이 없다(테스트): 알릴 것 없음
        job.window_position = plan.position
        if plan.adjusted:  # 옛 좌표가 화면 밖(예전과 같은 문구)
            log.info("job %s: %s", job.id, plan.note)
            self._event(job, job.state, f"크롬 {plan.note}", change=False)
        elif plan.fell_back:
            log.info("job %s: %s", job.id, plan.note)
            self._event(job, job.state, f"크롬 창: {plan.note}", change=False)
        return plan

    @staticmethod
    def _close_driver(job: Job) -> None:
        """실행기를 한 번만 닫는다."""
        driver, job.driver = job.driver, None
        if driver is not None:
            driver.close()

    def _check_cancel(self, job: Job) -> None:
        if job.cancel_flag.is_set():
            raise JobCancelled

    def _wait_for(self, job: Job, flag: threading.Event, deadline: float, reason: str) -> None:
        """사람의 응답(flag)을 마감(`deadline`, time.monotonic)까지 기다린다. 마감은 상태를 바꿀 때
        `_event(deadline=)`로 함께 정해 둔다. 취소되면 JobCancelled, 시간이 넘으면
        JobFailed(reason)."""
        with self._lock:
            job.deadline = deadline
        try:
            while True:
                self._check_cancel(job)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise JobFailed(reason)
                if flag.wait(min(WAIT_STEP_SECONDS, left)):
                    self._check_cancel(job)
                    return
        finally:
            with self._lock:
                job.deadline = None

    def _driver_failed(self, job: Job, exc: DriverError) -> JobFailed:
        if job.mode == "youtube" and exc.code == "signed_out":
            self._save_signed_out(job.profile)
        return JobFailed(exc.reason, screenshot=exc.screenshot)

    def _run_steps(self, job: Job, driver: BrowserDriver) -> None:
        """프로필 여는 중 → 입력 중 → (게시 대기) → 게시 중 → 확인 중 → 게시 완료."""
        live = job.mode == "youtube"
        where = "유튜브 영상으로" if live else "연습 페이지로"
        self._event(
            job, "launching", f"{job.profile}({job.folder}) 프로필로 크롬을 열어 {where} 가는 중"
        )
        try:
            driver.open(job.profile_path, job.open_url)  # type: ignore[arg-type]
        except DriverError as exc:
            raise self._driver_failed(job, exc) from None
        note = getattr(driver, "window_note", "")
        if isinstance(note, str) and note:  # 연 뒤 확인에서 창을 정한 모니터에 맞추지 못함
            self._event(job, job.state, note, change=False)
        self._check_cancel(job)
        self._event(job, "typing", "댓글 입력 자리를 눌러 한 글자씩 입력하는 중")
        try:
            driver.type_comment(
                job.comment_text, self.browser.typing_delay_ms, job.cancel_flag.is_set
            )
        except Stopped:
            raise JobCancelled from None
        except DriverError as exc:
            raise self._driver_failed(job, exc) from None
        self._check_cancel(job)
        if job.confirm_before_post:
            deadline = time.monotonic() + self.approval_timeout  # 기다리는 시간은 그대로
            self._event(
                job,
                "awaiting_approval",
                "입력을 마쳤습니다. 크롬 창의 글을 보고 [게시]를 눌러 주세요",
                deadline=deadline,
            )
            self._wait_for(job, job.approve_flag, deadline, REASON_APPROVAL_TIMEOUT)
            self._event(job, "posting", "[게시]를 받아 「댓글」 단추를 누르는 중")
        else:
            self._event(job, "posting", "입력을 마쳤습니다. 「댓글」 단추를 누르는 중")
        self._check_cancel(job)
        try:
            driver.click_post()
        except DriverError as exc:
            raise self._driver_failed(job, exc) from None
        self._event(job, "verifying", "페이지에서 내 댓글을 찾는 중")
        if not live:
            try:
                driver.verify_posted(job.comment_text)
            except DriverError as exc:
                raise JobFailed(exc.reason, screenshot=exc.screenshot) from None
            keep = self._keep_window(job, driver, found=True)
            if not keep:  # 끝났다고 알리기 전에 크롬을 닫아 프로필 폴더를 풀어 둔다
                self._close_driver(job)
            self._finish_posted(
                job, verified=True, note="", message="연습 페이지에 댓글이 달린 것을 확인했습니다",
                keep=keep,
            )
            return
        # 실제 게시: 여기부터는 이미 눌렀다. 못 찾아도 실패로 되돌리지 않는다
        # (다시 달면 두 번 달린다)
        found: bool | None
        try:
            driver.verify_posted(job.comment_text)
            found = True
        except DriverError:
            found = None
            if self.verify_comment is not None:
                try:
                    found = self.verify_comment(job.video_id, job.comment_text)
                except Exception:  # Data API 확인을 못 해도 게시는 이미 했다
                    found = None
        keep = self._keep_window(job, driver, found=bool(found))
        if not keep:
            self._close_driver(job)
        if found:
            self._finish_posted(
                job, verified=True, note="", message="유튜브에 내 댓글이 달린 것을 확인했습니다",
                keep=keep,
            )
        else:
            self._finish_posted(
                job,
                verified=False,
                note=NOTE_UNVERIFIED,
                message="게시됨(확인 못 함) — 「댓글」을 눌렀지만 페이지·Data API에서 "
                "내 댓글을 찾지 못했습니다. [댓글 보기]로 확인해 주세요",
                keep=keep,
            )

    def _keep_window(self, job: Job, driver: BrowserDriver, *, found: bool) -> bool:
        """게시 뒤 창을 열어 둘지 정하고, 열어 두면 내 댓글이 화면에 보이게 내려 둔다.

        설정이 0초이거나 그만두기·프로그램 닫기 중이면 False(예전처럼 바로 닫는다). 내 댓글을 못
        찾았어도 창은 열어 둔다(사람이 직접 볼 수 있게). 내려 두기에 실패해도 창은 그대로 둔다.
        작업 스레드에서만 부른다."""
        if self.keep_window_seconds <= 0 or job.cancel_flag.is_set():
            return False
        with self._lock:
            if self._closed:
                return False
        show = getattr(driver, "show_comment", None)
        if found and callable(show):
            try:
                if not show(job.comment_text):
                    log.info("job %s: 내 댓글을 화면 가운데로 내리지 못했습니다", job.id)
            except Exception:
                log.info("job %s: 내 댓글로 내려 가지 못했습니다", job.id)
        with self._lock:  # 작업을 끝났다고 알리기(_finish_posted) 전에 정해 둔다
            self._linger = _Linger(job, driver, time.monotonic() + self.keep_window_seconds)
            job.window_open = True
        return True

    def _finish_posted(
        self, job: Job, *, verified: bool, note: str, message: str, keep: bool = False
    ) -> None:
        self.rules.mark_posted(job.post_id, comment_text=job.comment_text, job_id=job.id, note=note)
        with self._lock:
            job.verified = verified
            job.finished_at = self.clock().isoformat()
        if keep:  # 진행 줄의 안내(화면은 window_open을 보고 같은 말을 붙인다). 끝 알림보다 먼저
            self._event(job, "posted", f"{MSG_WINDOW_OPEN}(길어도 {self._keep_span()})",
                        change=False)
        self._event(job, "posted", message)

    def _keep_span(self) -> str:
        seconds = int(self.keep_window_seconds)
        return f"{seconds // 60}분" if seconds % 60 == 0 else f"{seconds}초"

    def _fail(
        self, job: Job, reason: str, *, driver: BrowserDriver | None, screenshot: bool = True
    ) -> None:
        shot: Path | None = None
        if driver is not None and screenshot:
            path = Path(self.browser.screenshot_dir) / f"{job.id}.png"
            if driver.screenshot(path):
                shot = path
        with self._lock:  # 열어 두려던 창도 실패면 닫는다(그 실행기는 아래에서 닫힌다)
            if self._linger is not None and self._linger.job is job:
                self._linger = None
                job.window_open = False
        self._close_driver(job)  # 실패를 알리기 전에 닫는다(다시 시도할 때 프로필이 풀려 있게)
        try:
            self.rules.mark_failed(
                job.post_id,
                reason,
                comment_text=job.comment_text,
                screenshot_path=str(shot) if shot else "",
                job_id=job.id,
            )
        except (LookupError, ValueError):
            log.warning("job %s: 예약 %s을 실패로 바꾸지 못했습니다", job.id, job.post_id)
        with self._lock:
            job.failed_step = min(STEP_INDEX.get(job.state, 0), 5)
            job.reason = reason
            job.screenshot = shot
            job.finished_at = self.clock().isoformat()
        self._event(job, "failed", reason)

    # ------------------------------------------------------------ 닫기

    def shutdown(self, timeout: float = 8.0) -> bool:
        """진행 중인 작업을 취소하고 크롬을 닫은 뒤 작업 스레드를 멈춘다. 멈췄으면 True.

        게시 뒤 열어 둔 크롬 창도 작업 스레드가 멈추기 전에 닫는다(`_work_loop`가 None을
        받을 때)."""
        with self._lock:
            self._closed = True
            job = self._active
            if job is not None and not job.finished:
                job.cancel_flag.set()
        worker = self._worker
        if worker is None:
            return True
        self._queue.put(None)
        worker.join(timeout)
        return not worker.is_alive()
