"""라우터가 쓰는 서비스 묶음. 첫 요청 때 한 번 만든다(앱을 켤 때 DB·설정을 건드리지 않게).

R2: 설정을 저장하면 `ServiceHolder.update_settings`가 설정을 다시 읽고 서비스 묶음을 버린다.
다음 요청이 새 설정으로 새 묶음을 만든다(프로그램을 다시 켜지 않아도 바로 적용). 게시 작업이나
로그인 확인이 돌고 있으면 저장하지 않는다(`settings_busy`). 버린 묶음의 바깥 연결(YouTube·LLM)은
그때 진행 중인 요청이 끝날 수 있게 프로그램을 닫을 때 함께 닫는다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from fastapi import Request

from app import db
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.drafter import DraftService
from app.analysis.validator import ValidatorRules
from app.browser.chrome import find_chrome, popen_launcher
from app.browser.hooks import BrowserHooks
from app.browser.jobs import JobService
from app.browser.login import LoginWindows, ProfileAccounts, default_checker
from app.browser.screens import Monitor, app_window_monitor, read_monitors
from app.config import Settings, load_settings, reload_settings
from app.errors import AppError, ErrorKind, remember_log_secrets
from app.llm.base import LLMClient, LLMHealth
from app.llm.cli_login import CLILogins
from app.llm.registry import build_llm
from app.ops.ledger import Ledger
from app.ops.profiles import ProfileService
from app.ops.rules import PostRules
from app.transcript.auto import AutoTranscriptProvider
from app.user_settings import UserStore, default_user_dir
from app.youtube.client import YouTubeClient
from app.youtube.quota import Clock, QuotaTracker, SearchCache, utc_now
from app.youtube.rising import RisingService
from app.youtube.service import VideoService


@dataclass
class Services:
    settings: Settings
    quota: QuotaTracker
    videos: VideoService
    context: ContextService
    checks: CheckService
    # 4단계: 고른 LLM 공급자. 설정이 틀려 못 만들었으면 llm은 None, 이유는 llm_error
    llm: LLMClient | None = None
    llm_error: AppError | None = None
    # 5단계: 분석과 초안. LLM은 그때그때 `require_llm()`으로 받는다(테스트가 바꿔 끼울 수 있게)
    drafts: DraftService = field(default=None)  # type: ignore[assignment]
    # 7단계: 운영 규칙(영상당 1개·하루 상한), 프로필, 작업 기록
    rules: PostRules = field(default=None)  # type: ignore[assignment]
    profiles: ProfileService = field(default=None)  # type: ignore[assignment]
    ledger: Ledger = field(default=None)  # type: ignore[assignment]
    # 8단계: 게시 작업(테스트 페이지 자동 실행 · 실제 유튜브 열기)
    jobs: JobService = field(default=None)  # type: ignore[assignment]
    hooks: BrowserHooks = field(default_factory=BrowserHooks)
    # R2: 프로필 로그인 창 열기와 로그인 확인
    accounts: ProfileAccounts = field(default=None)  # type: ignore[assignment]
    # R4: 뜨기 직전 영상(초안까지만)
    rising: RisingService = field(default=None)  # type: ignore[assignment]
    # R5: 고른 AI가 아닌 AI도 [연결 확인]·[모델 불러오기]를 할 때 쓰는 연결(테스트는 가짜)
    llm_transport: httpx.BaseTransport | None = None
    # 2026-11-17 로그인된 프로그램의 [로그인하기] 창과 마지막 로그인 확인 결과
    cli_logins: CLILogins = field(default_factory=CLILogins)

    def find_chrome(self):
        if self.hooks.chrome_finder is not None:
            return self.hooks.chrome_finder()
        return find_chrome(self.settings.browser.chrome_path)

    def app_monitor(self, monitors: list[Monitor]) -> Monitor | None:
        """프로그램 창이 있는 모니터(창 위치 자동 규칙). 테스트는 hooks.app_monitor로 바꾼다."""
        reader = self.hooks.app_monitor or app_window_monitor
        try:
            return reader(monitors)
        except Exception:
            return None

    def monitors(self) -> list[Monitor]:
        """지금 연결된 모니터 영역(9단계, 창 위치 확인). 테스트는 hooks.screens로 바꾼다."""
        reader = self.hooks.screens or read_monitors
        try:
            return list(reader())
        except Exception:
            return []

    def require_llm(self) -> LLMClient:
        if self.llm is None:
            raise self.llm_error or AppError("llm_provider_unknown")
        return self.llm

    def llm_health(self) -> LLMHealth:
        if self.llm is None:
            llm = self.settings.llm
            return LLMHealth(llm.active, "", False, False, True)
        return self.llm.health()

    def close(self) -> None:
        if self.jobs is not None:
            self.jobs.shutdown()  # 진행 중인 작업을 취소하고 크롬을 닫는다
        self.videos.client.close()
        if self.llm is not None:
            self.llm.close()


def build_services(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
    llm_transport: httpx.BaseTransport | None = None,
    clock: Clock = utc_now,
    browser_hooks: BrowserHooks | None = None,
    windows: LoginWindows | None = None,
) -> Services:
    db.init_db(settings.db_path)
    quota = QuotaTracker(settings.db_path, clock=clock)
    client = YouTubeClient(settings.youtube_api_key, transport=transport, on_units=quota.add)
    videos = VideoService(
        client,
        db_path=settings.db_path,
        quota=quota,
        cache=SearchCache(settings.db_path, clock=clock),
        clock=clock,
        shorts_under_seconds=settings.discover.shorts_under_seconds,
    )
    context = ContextService(
        videos,
        db_path=settings.db_path,
        clock=clock,
        transcript_provider=settings.transcript_provider,
        context_chars=settings.context_chars,
        # R4: 자막 자동 읽기(제한 시간은 설정 transcript.timeout_seconds, 기본 10초)
        auto=AutoTranscriptProvider(timeout_seconds=settings.transcript_timeout_seconds),
    )
    checks = CheckService(
        context,
        rules=ValidatorRules.from_config(settings.rules, settings.validator_extra_patterns),
        brand_facts=settings.brand_facts,
    )
    llm: LLMClient | None = None
    llm_error: AppError | None = None
    try:
        llm = build_llm(settings, transport=llm_transport)
    except AppError as exc:  # 앱은 뜬다. AI 상태와 AI 기능에서 이유를 알린다
        llm_error = exc
    services = Services(
        settings=settings,
        quota=quota,
        videos=videos,
        context=context,
        checks=checks,
        llm=llm,
        llm_error=llm_error,
        llm_transport=llm_transport,
    )
    remember_log_secrets(settings.secret_values())  # R5: 저장한 키도 로그에서 가린다
    services.rising = RisingService(videos, rule=settings.rising, clock=clock)
    services.ledger = Ledger(
        settings.db_path, daily_limit=settings.daily_max_comments, clock=clock
    )
    services.rules = PostRules(
        settings.db_path,
        daily_limit=settings.daily_max_comments,
        profiles=settings.profiles,
        clock=clock,
    )
    services.profiles = ProfileService(settings.profiles, db_path=settings.db_path)
    services.drafts = DraftService(
        context,
        checks,
        llm=services.require_llm,
        db_path=settings.db_path,
        clock=clock,
        brand_facts=settings.brand_facts,
        ledger=services.ledger,
        disclose_default=settings.disclose_default,
        ai_review=settings.ai_review,
        writer=settings.writer,
    )
    services.hooks = browser_hooks or BrowserHooks()
    services.jobs = build_jobs(services, clock=clock)
    services.jobs.recover_stale()  # 지난번에 작업 중 꺼져 예약으로 남은 게시를 푼다
    hooks = services.hooks
    services.accounts = ProfileAccounts(
        db_path=settings.db_path,
        profiles=services.profiles,
        browser=settings.browser,
        chrome_finder=services.find_chrome,
        run_on_worker=services.jobs.run_task,
        busy=services.jobs.busy,
        task_running=services.jobs.task_running,
        release_window=services.jobs.release_window,  # 게시 뒤 열어 둔 크롬 창을 먼저 닫는다
        windows=windows or LoginWindows(),
        launcher=hooks.launcher or popen_launcher,
        checker=hooks.login_checker or default_checker,
        playwright_ready=services.jobs.playwright_ready,
        screens=services.monitors,
        clock=clock,
        app_monitor=services.app_monitor,
    )
    services.cli_logins.check = lambda name: _program_login(services, name)
    if hooks.cli_login_launcher is not None:
        services.cli_logins.launcher = hooks.cli_login_launcher
    return services


def _program_login(services: Services, name: str) -> bool | None:
    """[로그인하기] 창이 닫힌 뒤: 그 프로그램의 로그인 상태 명령으로 묻는다."""
    from app.api.ai_choice import program_login

    return program_login(services, name)


def build_jobs(services: Services, *, clock: Clock = utc_now) -> JobService:
    hooks = services.hooks
    settings = services.settings
    client = services.videos.client

    def verify_comment(video_id: str, text: str) -> bool | None:
        """실제 게시: 페이지에서 못 찾은 내 댓글을 Data API로 찾는다.

        키가 없으면 None(확인 못 함)."""
        if not settings.youtube_key_configured:
            return None
        wanted = " ".join(text.split())
        for comment in client.search_comments(video_id, wanted):
            if " ".join(comment.text.split()) == wanted:
                return True
        return False

    extra = {}
    if hooks.driver_factory is not None:
        extra["driver_factory"] = hooks.driver_factory
    if hooks.youtube_driver_factory is not None:
        extra["youtube_driver_factory"] = hooks.youtube_driver_factory
    if hooks.playwright_ready is not None:
        extra["playwright_ready"] = hooks.playwright_ready
    if hooks.approval_timeout is not None:
        extra["approval_timeout"] = hooks.approval_timeout
    return JobService(
        db_path=settings.db_path,
        rules=services.rules,
        profiles=services.profiles,
        browser=settings.browser,
        chrome_finder=services.find_chrome,
        verify_comment=hooks.verify_comment or verify_comment,
        clock=clock,
        screens=services.monitors,
        app_monitor=services.app_monitor,
        confirm_before_post=settings.confirm_before_post,
        keep_window_seconds=settings.keep_window_seconds,
        **extra,
    )


class ServiceHolder:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        llm_transport: httpx.BaseTransport | None = None,
        clock: Clock = utc_now,
        browser_hooks: BrowserHooks | None = None,
        on_build: Callable[[Services], None] | None = None,
    ) -> None:
        self._settings = settings
        self._browser_hooks = browser_hooks
        self._transport = transport
        self._llm_transport = llm_transport
        self._clock = clock
        self._on_build = on_build  # 테스트: 새로 만든 묶음에 가짜 LLM 등을 끼우는 자리
        self._services: Services | None = None
        self._retired: list[Services] = []
        self._lock = threading.RLock()
        # 로그인 창 목록은 서비스를 다시 만들어도 그대로 둔다. 창이 닫히면 지금 묶음으로 확인한다
        self.windows = LoginWindows()
        self.windows.on_closed = self._check_after_close

    @property
    def settings(self) -> Settings:
        with self._lock:
            if self._settings is None:
                # 실제 프로그램: 프로그램 안에서 바꾼 설정(%LOCALAPPDATA%/JGMarketingAgent)을 먼저
                self._settings = load_settings(user_dir=default_user_dir())
            return self._settings

    def get(self) -> Services:
        with self._lock:
            if self._services is None:
                services = build_services(
                    self.settings,
                    transport=self._transport,
                    llm_transport=self._llm_transport,
                    clock=self._clock,
                    browser_hooks=self._browser_hooks,
                    windows=self.windows,
                )
                if self._on_build is not None:
                    self._on_build(services)
                self._services = services
            return self._services

    def store(self) -> UserStore:
        source = self.settings.source
        store = source.store() if source is not None else None
        if store is None:
            raise AppError(ErrorKind.SETTINGS_NO_STORE)
        return store

    def busy(self) -> bool:
        with self._lock:
            services = self._services
        return services is not None and services.jobs is not None and services.jobs.busy()

    def update_settings(self, change: Callable[[UserStore], None]) -> Settings:
        """사용자 설정을 바꾸고(`change`) 바로 적용한다. 게시 중이면 `settings_busy`.

        `change`가 실패하면 오류를 던진다(서비스는 그때의 설정으로 다음 요청이 새로 만든다).
        """
        with self._lock:
            current = self.settings
            store = self.store()
            services = self._services
            if services is not None and services.jobs is not None:
                if not services.jobs.close_if_idle():
                    raise AppError(ErrorKind.SETTINGS_BUSY)
            try:
                change(store)
                self._settings = reload_settings(current)
            finally:
                if services is not None:
                    self._retire(services)
                    self._services = None
            return self._settings

    def _retire(self, services: Services) -> None:
        """버리는 묶음: 작업 스레드는 바로 멈추고, 바깥 연결은 프로그램을 닫을 때 닫는다."""
        if services.jobs is not None:
            services.jobs.shutdown(timeout=5)
        self._retired.append(services)

    def _check_after_close(self, name: str) -> None:
        try:
            services = self.get()
        except Exception:
            return
        if services.accounts is not None:
            services.accounts.check_after_close(name)

    def shutdown_jobs(self) -> None:
        """프로그램 창을 닫을 때: 진행 중인 게시 작업을 취소하고 크롬을 닫는다.

        서비스를 아직 만들지 않았으면 할 일이 없다.
        """
        with self._lock:
            services = self._services
        if services is not None and services.jobs is not None:
            services.jobs.shutdown()

    def close(self) -> None:
        with self._lock:
            if self._services is not None:
                self._services.close()
                self._services = None
            for old in self._retired:
                try:
                    old.close()
                except Exception:  # 이미 닫힌 연결 등은 무시
                    pass
            self._retired.clear()


def get_services(request: Request) -> Services:
    return request.app.state.services.get()


def get_settings(request: Request) -> Settings:
    return request.app.state.services.settings
