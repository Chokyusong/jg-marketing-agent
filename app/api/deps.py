"""라우터가 쓰는 서비스 묶음. 첫 요청 때 한 번 만든다(앱을 켤 때 DB·설정을 건드리지 않게)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import httpx
from fastapi import Request

from app import db
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.validator import ValidatorRules
from app.config import Settings, load_settings
from app.errors import AppError
from app.llm.base import LLMClient, LLMHealth
from app.llm.registry import build_llm
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
        self.videos.client.close()
        if self.llm is not None:
            self.llm.close()


def build_services(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
    llm_transport: httpx.BaseTransport | None = None,
    clock: Clock = utc_now,
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
    return Services(
        settings=settings,
        quota=quota,
        videos=videos,
        context=context,
        checks=checks,
        llm=llm,
        llm_error=llm_error,
    )


class ServiceHolder:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        llm_transport: httpx.BaseTransport | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._settings = settings
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
                )
            return self._services

    def close(self) -> None:
        with self._lock:
            if self._services is not None:
                self._services.close()
                self._services = None


def get_services(request: Request) -> Services:
    return request.app.state.services.get()


def get_settings(request: Request) -> Settings:
    return request.app.state.services.settings
