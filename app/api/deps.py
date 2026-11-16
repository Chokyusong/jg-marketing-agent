"""라우터가 쓰는 서비스 묶음. 첫 요청 때 한 번 만든다(앱을 켤 때 DB·설정을 건드리지 않게)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import httpx
from fastapi import Request

from app import db
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.drafter import DraftService
from app.analysis.validator import ValidatorRules
from app.browser.chrome import find_chrome
from app.browser.hooks import BrowserHooks
from app.browser.jobs import JobService
from app.browser.screens import Monitor, read_monitors
from app.config import Settings, load_settings
from app.errors import AppError
from app.llm.base import LLMClient, LLMHealth
from app.llm.registry import build_llm
from app.ops.ledger import Ledger
from app.ops.profiles import ProfileService
from app.ops.rules import PostRules
from app.youtube.client import YouTubeClient
from app.youtube.quota import Clock, QuotaTracker, SearchCache, utc_now
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

    def find_chrome(self):
        if self.hooks.chrome_finder is not None:
            return self.hooks.chrome_finder()
        return find_chrome(self.settings.browser.chrome_path)

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
    )
    context = ContextService(
        videos,
        db_path=settings.db_path,
        clock=clock,
        transcript_provider=settings.transcript_provider,
        context_chars=settings.context_chars,
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
    )
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
    )
    services.hooks = browser_hooks or BrowserHooks()
    services.jobs = build_jobs(services, clock=clock)
    services.jobs.recover_stale()  # 지난번에 작업 중 꺼져 예약으로 남은 게시를 푼다
    return services


def build_jobs(services: Services, *, clock: Clock = utc_now) -> JobService:
    hooks = services.hooks
    settings = services.settings
    client = services.videos.client

    def verify_comment(video_id: str, text: str) -> bool | None:
        """assist: 사람이 게시했다고 한 댓글을 Data API로 찾는다. 키가 없으면 None(확인 못 함)."""
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
    if hooks.launcher is not None:
        extra["launcher"] = hooks.launcher
    if hooks.playwright_ready is not None:
        extra["playwright_ready"] = hooks.playwright_ready
    if hooks.approval_timeout is not None:
        extra["approval_timeout"] = hooks.approval_timeout
    if hooks.confirm_timeout is not None:
        extra["confirm_timeout"] = hooks.confirm_timeout
    return JobService(
        db_path=settings.db_path,
        rules=services.rules,
        profiles=services.profiles,
        browser=settings.browser,
        chrome_finder=services.find_chrome,
        verify_comment=hooks.verify_comment or verify_comment,
        clock=clock,
        screens=services.monitors,
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
    ) -> None:
        self._settings = settings
        self._browser_hooks = browser_hooks
        self._transport = transport
        self._llm_transport = llm_transport
        self._clock = clock
        self._services: Services | None = None
        self._lock = threading.Lock()

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    def get(self) -> Services:
        with self._lock:
            if self._services is None:
                self._services = build_services(
                    self.settings,
                    transport=self._transport,
                    llm_transport=self._llm_transport,
                    clock=self._clock,
                    browser_hooks=self._browser_hooks,
                )
            return self._services

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


def get_services(request: Request) -> Services:
    return request.app.state.services.get()


def get_settings(request: Request) -> Settings:
    return request.app.state.services.settings
