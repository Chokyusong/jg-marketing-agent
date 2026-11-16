"""게시 작업(job) 서비스 — 8단계(DESIGN 6.2 · PLAYBOOK 8단계).

```text
start(video_id, draft_id, profile, target) -> job_id
                                승인한 초안 확인 → rules.reserve → 작업 스레드에
approve(job_id)                 승인 대기 중인 sandbox 작업의 게시를 허락
confirm(job_id, posted)         assist(실제 유튜브)에서 사람이 「게시했어요 / 게시 안 함」
cancel(job_id)
get(job_id) -> JobView          상태, 지난 단계, 메시지, 실패 사유, 캡처 유무, 댓글 보기 주소
```

상태: 대기(queued) → 프로필 실행(launching) → 댓글 입력(typing) → **승인 대기(awaiting_approval)**
→ 게시 중(posting) → 확인(verifying) → 게시 완료(posted) / 실패(failed).
assist는 대기 → 프로필 실행 → 사람 게시 대기(awaiting_confirm) → 확인 → 게시 완료 / 실패.

- **한 번에 작업 하나.** 진행 중인 작업이 있으면 `start`가 `job_busy`로 거절한다.
- 작업은 **전용 작업 스레드 하나**에서 돈다. Playwright는 그 스레드에서만 만들고 쓴다
  (스레드에 안전하지 않다). 그래서 다른 스레드(API 요청)는 이벤트 깃발만 세운다.
- 승인 없이는 게시 단계로 가지 않는다: 작업 스레드가 승인 깃발을 기다리고,
  깃발은 `approve()`만 세운다.
- 상태가 바뀔 때마다 `job_events`에 한 줄. 끝나면 `rules.mark_posted` / `mark_failed`가
  상태를 바꾸는 같은 거래 안에서 작업 기록(`runs`)에 결과 한 줄을 남긴다
  (그래서 `Ledger.record`를 따로 부르지 않는다 — 부르면 같은 결과가 두 줄 생긴다).
- 실패하면 `error_screenshots/<작업ID>.png`(sandbox만. assist는 실제 유튜브 화면을 찍지 않는다).
- **sandbox**: 이 앱의 `/sandbox/watch` 주소만 연다(`sandbox_driver.require_sandbox_url`).
- **assist**: 크롬을 프로필 폴더와 영상 주소로 실행만 한다(`chrome.assist_args`, 셸 없이).
  실제 유튜브 화면은 건드리지 않는다. 사람이 [게시했어요]를 누르면
  YouTube 키가 있을 때만 Data API로 찾아본다.
- **창 위치(9단계).** 창이 보이는 실행(assist, 또는 headless가 아닌 sandbox)은 띄우기 전에
  `browser.window_position`이 실제 모니터 안인지 본다(`screens.check_window_position`). 밖이면
  주 모니터의 안전한 위치로 바꿔 띄우고 작업 기록(job_events)에 그렇게 했다고 남긴다.
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
from app.browser.chrome import (
    Launcher,
    assist_args,
    ensure_profile_dir,
    popen_launcher,
    require_profile_free,
    stop_process,
)
from app.browser.sandbox_driver import (
    LOCAL_HOSTS,
    BrowserDriver,
    DriverError,
    PlaywrightSandboxDriver,
    Stopped,
    require_sandbox_url,
)
from app.browser.screens import Monitor, check_window_position
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
    "awaiting_confirm",
    "posting",
    "verifying",
    "posted",
    "failed",
)
FINAL_STATES = ("posted", "failed")
STATE_LABELS = {
    "queued": "대기",
    "launching": "프로필 실행",
    "typing": "댓글 입력",
    "awaiting_approval": "승인 대기",
    "awaiting_confirm": "게시 확인 대기",
    "posting": "게시 중",
    "verifying": "확인 중",
    "posted": "게시 완료",
    "failed": "실패",
}
# 화면의 진행 단계 표시 6개(UI_SPEC A4: 대기 · 프로필 실행 · 댓글 입력 · 승인 대기 · 게시 · 확인)
# 에서 지금 있는 칸(0~5). 게시 완료는 6(모두 지남)
STEP_INDEX = {
    "queued": 0,
    "launching": 1,
    "typing": 2,
    "awaiting_approval": 3,
    "awaiting_confirm": 3,
    "posting": 4,
    "verifying": 5,
    "posted": 6,
}
MODES = ("sandbox", "assist")
APPROVAL_TIMEOUT_SECONDS = 5 * 60  # sandbox: 승인 대기 5분
CONFIRM_TIMEOUT_SECONDS = 10 * 60  # assist: 사람 게시 대기 10분
STALE_AFTER = timedelta(minutes=15)  # 이보다 오래 예약으로 남은 게시는 꺼진 작업의 흔적으로 본다
KEEP_JOBS = 50
WAIT_STEP_SECONDS = 0.1

REASON_APPROVAL_TIMEOUT = "승인 시간 초과(5분 안에 [게시 승인]을 누르지 않았습니다)"
REASON_CONFIRM_TIMEOUT = "확인 시간 초과(10분 안에 [게시했어요]·[게시 안 함]을 누르지 않았습니다)"
REASON_CANCELLED = "사용자가 작업을 취소했습니다"
REASON_NOT_POSTED = "게시 안 함(사람이 [게시 안 함]을 눌렀습니다)"
REASON_STALE = "프로그램이 게시 작업 중에 꺼졌습니다"
NOTE_UNVERIFIED = "게시됨(확인 못 함)"


def mode_of(target: str) -> tuple[str, str]:
    """화면·API의 대상 이름 → (작업 방식, 게시 기록의 대상). assist와 youtube는 같은 것."""
    t = (target or "").strip().lower()
    if t == "sandbox":
        return "sandbox", "sandbox"
    if t in ("assist", "youtube"):
        return "assist", "youtube"
    raise ValueError(f"알 수 없는 대상: {target!r} (sandbox | assist)")


def new_job_id(clock: Clock) -> str:
    """파일 이름으로도 쓰는 작업 ID(영문·숫자·-만): 20261116-153012-a1b2c3."""
    stamp = clock().astimezone(_KST).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def is_job_id(value: str) -> bool:
    return bool(value) and len(value) <= 40 and all(c.isalnum() or c == "-" for c in value)


def sandbox_url(base_url: str, video_id: str, profile: str, fail: str = "") -> str:
    """이 앱의 테스트 페이지 주소. `base_url`은 로컬 주소(http://127.0.0.1:포트)만."""
    parts = urlsplit(base_url)
    if parts.scheme != "http" or (parts.hostname or "").lower() not in LOCAL_HOSTS:
        raise ValueError(f"테스트 페이지는 이 PC의 앱 주소에서만 엽니다: {base_url!r}")
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
    mode: str  # sandbox | assist
    target: str  # sandbox | youtube (게시 기록의 대상)
    video_id: str
    draft_id: int
    post_id: int
    profile: str
    folder: str
    comment_text: str
    open_url: str  # 크롬이 여는 주소(sandbox 페이지 / 실제 유튜브 영상)
    view_url: str  # [댓글 보기] 주소
    created_at: str
    state: str = "queued"
    message: str = ""
    reason: str = ""
    failed_step: int | None = None
    verified: bool | None = None  # assist: Data API로 찾았는지(키가 없거나 못 찾으면 거짓)
    screenshot: Path | None = None
    finished_at: str | None = None
    deadline: float | None = None  # 승인·확인을 기다리는 마감(time.monotonic)
    events: list[JobEvent] = field(default_factory=list)
    approve_flag: threading.Event = field(default_factory=threading.Event)
    confirm_flag: threading.Event = field(default_factory=threading.Event)
    confirm_posted: bool | None = None
    cancel_flag: threading.Event = field(default_factory=threading.Event)
    proc: Any = None  # assist: 실행한 크롬 프로세스
    driver: Any = None  # sandbox: 아직 닫지 않은 실행기(닫으면 None)
    chrome: Path | None = None  # chrome.exe 위치
    profile_path: Path | None = None  # 프로필 폴더(API에는 싣지 않는다)
    window_position: tuple[int, int] | None = None  # 실제로 띄운 창 위치(화면 밖이면 바꾼 값)

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
    waiting_for: str | None  # approve | confirm | None
    seconds_left: int | None  # 승인·확인 마감까지 남은 초
    created_at: str
    finished_at: str | None
    events: list[JobEvent]


VerifyComment = Callable[
    [str, str], bool | None
]  # (video_id, text) -> 찾음/못 찾음/확인 불가(None)
DriverFactory = Callable[[BrowserSettings], BrowserDriver]


def default_driver_factory(settings: BrowserSettings) -> BrowserDriver:
    return PlaywrightSandboxDriver(
        headless=settings.headless, window_position=settings.window_position
    )


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
        launcher: Launcher = popen_launcher,
        verify_comment: VerifyComment | None = None,
        playwright_ready: Callable[[], bool] = playwright_installed,
        clock: Clock = utc_now,
        approval_timeout: float = APPROVAL_TIMEOUT_SECONDS,
        confirm_timeout: float = CONFIRM_TIMEOUT_SECONDS,
        rng: random.Random | None = None,
        screens: Callable[[], Sequence[Monitor]] | None = None,
    ) -> None:
        self.db_path = db_path
        # 모니터 목록을 읽는 함수(9단계). None이면 확인하지 않고 설정값 그대로 띄운다
        self.screens = screens
        self.rules = rules
        self.profiles = profiles
        self.browser = browser
        self.chrome_finder = chrome_finder
        self.driver_factory = driver_factory
        self.launcher = launcher
        self.verify_comment = verify_comment
        self.playwright_ready = playwright_ready
        self.clock = clock
        self.approval_timeout = float(approval_timeout)
        self.confirm_timeout = float(confirm_timeout)
        self.rng = rng or random.Random()
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._active: Job | None = None
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._closed = False

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
        """작업을 만들고 작업 스레드에 넣는다. 막히면 AppError(예약 전이면 아무것도 안 남긴다)."""
        mode, post_target = mode_of(target)
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        with self._lock:
            if self._closed:
                raise AppError(ErrorKind.JOB_BUSY, detail="프로그램을 닫는 중")
            if self._active is not None and not self._active.finished:
                raise AppError(
                    ErrorKind.JOB_BUSY,
                    detail=f"진행 중: {self._active.id}",
                    extra={"job_id": self._active.id},
                )
            self.recover_stale()
            if mode == "sandbox" and not self.playwright_ready():
                raise AppError(ErrorKind.PLAYWRIGHT_MISSING)
            chrome = self.chrome_finder()
            if chrome is None:
                raise AppError(ErrorKind.CHROME_NOT_FOUND)
            chosen = self.profiles.resolve(profile or None, post_target)
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
            job = Job(
                id=new_job_id(self.clock),
                mode=mode,
                target=post_target,
                video_id=video_id,
                draft_id=int(draft_id),
                post_id=post_id,
                profile=chosen.name,
                folder=chosen.folder,
                comment_text=self._draft_body(int(draft_id)),
                open_url=open_url,
                view_url=view_url,
                created_at=self.clock().isoformat(),
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

    def _draft_body(self, draft_id: int) -> str:
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT body FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return row["body"] if row else ""

    # ------------------------------------------------------------ 사람의 응답

    def approve(self, job_id: str) -> JobView:
        with self._lock:
            job = self._require(job_id)
            if job.state != "awaiting_approval":
                raise AppError(
                    ErrorKind.JOB_WRONG_STATE, detail=f"지금 상태: {STATE_LABELS[job.state]}"
                )
            if not job.approve_flag.is_set():
                job.approve_flag.set()
                self._event(job, job.state, "사람이 게시를 승인했습니다", change=False)
            return self._view(job)

    def confirm(self, job_id: str, posted: bool) -> JobView:
        with self._lock:
            job = self._require(job_id)
            if job.mode != "assist" or job.state != "awaiting_confirm":
                raise AppError(
                    ErrorKind.JOB_WRONG_STATE, detail=f"지금 상태: {STATE_LABELS[job.state]}"
                )
            if not job.confirm_flag.is_set():
                job.confirm_posted = bool(posted)
                job.confirm_flag.set()
                text = (
                    "사람이 「게시했어요」를 눌렀습니다"
                    if posted
                    else "사람이 「게시 안 함」을 눌렀습니다"
                )
                self._event(job, job.state, text, change=False)
            return self._view(job)

    def cancel(self, job_id: str) -> JobView:
        with self._lock:
            job = self._require(job_id)
            if job.finished:
                raise AppError(ErrorKind.JOB_WRONG_STATE, detail="이미 끝난 작업")
            if not job.cancel_flag.is_set():
                job.cancel_flag.set()
                self._event(job, job.state, "취소 요청을 받았습니다", change=False)
            return self._view(job)

    # ------------------------------------------------------------ 조회

    def get(self, job_id: str) -> JobView:
        with self._lock:
            return self._view(self._require(job_id))

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
        waiting = {"awaiting_approval": "approve", "awaiting_confirm": "confirm"}.get(job.state)
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
        )

    # ------------------------------------------------------------ 기록

    def _event(self, job: Job, state: str, message: str, *, change: bool = True) -> None:
        """상태를 바꾸고(change) job_events에 한 줄 남긴다."""
        stamp = self.clock().isoformat()
        with self._lock:
            if change:
                job.state = state
                job.message = message
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
            job = self._queue.get()
            if job is None:
                return
            self._run(job)

    def _run(self, job: Job) -> None:
        driver: BrowserDriver | None = None
        try:
            if job.cancel_flag.is_set():
                raise JobCancelled
            if job.mode == "sandbox":
                browser = self.browser
                if not browser.headless:  # 창이 보일 때만 위치를 확인한다
                    browser = replace(browser, window_position=self._place_window(job))
                driver = job.driver = self.driver_factory(browser)
                self._run_sandbox(job, driver)
            else:
                self._run_assist(job)
        except JobCancelled:
            if job.mode == "assist":
                stop_process(job.proc)  # 취소했으면 우리가 연 크롬을 닫는다(끝을 알리기 전에)
            self._fail(job, REASON_CANCELLED, driver=driver, screenshot=False)
        except JobFailed as exc:
            self._fail(job, exc.reason, driver=driver, screenshot=exc.screenshot)
        except Exception as exc:  # 예상 못 한 오류도 작업을 실패로 끝내고 예약을 푼다
            log.exception("job %s crashed", job.id)
            self._fail(job, f"예상하지 못한 오류: {type(exc).__name__}", driver=driver)
        finally:
            self._close_driver(job)

    def _place_window(self, job: Job) -> tuple[int, int]:
        """창을 띄울 위치. 설정값이 화면 밖이면 주 모니터의 안전한 위치로 바꾸고 기록에 남긴다."""
        wanted = self.browser.window_position
        if self.screens is None:
            job.window_position = wanted
            return wanted
        try:
            monitors = list(self.screens())
        except Exception:  # 모니터를 못 읽어도 작업은 설정값으로 계속한다
            log.exception("job %s: 모니터 정보를 읽지 못했습니다", job.id)
            monitors = []
        check = check_window_position(wanted, monitors)
        position = check.position or wanted
        job.window_position = position
        if check.adjusted:
            log.info("job %s: %s", job.id, check.note)
            self._event(job, job.state, f"크롬 {check.note}", change=False)
        return position

    @staticmethod
    def _close_driver(job: Job) -> None:
        """sandbox 실행기를 한 번만 닫는다."""
        driver, job.driver = job.driver, None
        if driver is not None:
            driver.close()

    def _check_cancel(self, job: Job) -> None:
        if job.cancel_flag.is_set():
            raise JobCancelled

    def _wait_for(self, job: Job, flag: threading.Event, timeout: float, reason: str) -> None:
        """사람의 응답(flag)을 기다린다. 취소되면 JobCancelled, 시간이 넘으면 JobFailed(reason)."""
        deadline = time.monotonic() + timeout
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

    def _run_sandbox(self, job: Job, driver: BrowserDriver) -> None:
        self._event(job, "launching", f"{job.profile}({job.folder}) 프로필로 크롬을 여는 중")
        try:
            driver.open(job.profile_path, job.open_url)  # type: ignore[arg-type]
        except DriverError as exc:
            raise JobFailed(exc.reason, screenshot=exc.screenshot) from None
        self._check_cancel(job)
        self._event(job, "typing", "테스트 페이지 댓글 상자에 한 글자씩 입력하는 중")
        try:
            driver.type_comment(
                job.comment_text, self.browser.typing_delay_ms, job.cancel_flag.is_set
            )
        except Stopped:
            raise JobCancelled from None
        except DriverError as exc:
            raise JobFailed(exc.reason, screenshot=exc.screenshot) from None
        self._check_cancel(job)
        self._event(
            job, "awaiting_approval", "입력을 마쳤습니다. 대시보드에서 [게시 승인]을 눌러 주세요"
        )
        self._wait_for(job, job.approve_flag, self.approval_timeout, REASON_APPROVAL_TIMEOUT)
        self._event(job, "posting", "승인을 받아 「댓글」 단추를 누르는 중")
        try:
            driver.click_post()
            self._event(job, "verifying", "페이지에서 내 댓글을 찾는 중")
            driver.verify_posted(job.comment_text)
        except DriverError as exc:
            raise JobFailed(exc.reason, screenshot=exc.screenshot) from None
        self._close_driver(job)  # 끝났다고 알리기 전에 크롬을 닫아 프로필 폴더를 풀어 둔다
        self._finish_posted(
            job, verified=True, note="", message="테스트 페이지에 댓글이 달린 것을 확인했습니다"
        )

    def _run_assist(self, job: Job) -> None:
        self._event(
            job, "launching", f"{job.profile}({job.folder}) 프로필로 크롬에서 영상을 여는 중"
        )
        args = assist_args(
            job.chrome,  # type: ignore[arg-type]
            job.profile_path,  # type: ignore[arg-type]
            job.open_url,
            self._place_window(job),
        )
        try:
            job.proc = self.launcher(args)
        except OSError as exc:
            raise JobFailed(
                f"크롬을 실행하지 못했습니다: {exc.strerror or exc}", screenshot=False
            ) from None
        self._check_cancel(job)
        self._event(
            job,
            "awaiting_confirm",
            "크롬에서 초안을 붙여 넣고 직접 게시한 뒤 [게시했어요] 또는 [게시 안 함]을 눌러 주세요",
        )
        self._wait_for(job, job.confirm_flag, self.confirm_timeout, REASON_CONFIRM_TIMEOUT)
        if not job.confirm_posted:
            raise JobFailed(REASON_NOT_POSTED, screenshot=False)
        self._event(job, "verifying", "YouTube Data API로 댓글을 찾아보는 중")
        found: bool | None = None
        if self.verify_comment is not None:
            try:
                found = self.verify_comment(job.video_id, job.comment_text)
            except Exception:  # 확인을 못 해도 사람이 게시했다고 했으니 게시로 본다
                found = None
        if found:
            self._finish_posted(
                job, verified=True, note="", message="Data API로 댓글을 확인했습니다"
            )
        else:
            self._finish_posted(
                job,
                verified=False,
                note=NOTE_UNVERIFIED,
                message="게시됨(확인 못 함) — 사람이 게시했다고 알렸고, "
                "Data API로는 찾지 못했거나 키가 없습니다",
            )

    def _finish_posted(self, job: Job, *, verified: bool, note: str, message: str) -> None:
        self.rules.mark_posted(job.post_id, comment_text=job.comment_text, job_id=job.id, note=note)
        with self._lock:
            job.verified = verified
            job.finished_at = self.clock().isoformat()
        self._event(job, "posted", message)

    def _fail(
        self, job: Job, reason: str, *, driver: BrowserDriver | None, screenshot: bool = True
    ) -> None:
        shot: Path | None = None
        if driver is not None and screenshot and job.mode == "sandbox":
            path = Path(self.browser.screenshot_dir) / f"{job.id}.png"
            if driver.screenshot(path):
                shot = path
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
        """진행 중인 작업을 취소하고 크롬을 닫은 뒤 작업 스레드를 멈춘다. 멈췄으면 True."""
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
        if job is not None and job.mode == "assist" and job.cancel_flag.is_set():
            stop_process(job.proc)
        return not worker.is_alive()
