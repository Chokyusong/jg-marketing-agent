"""라우터가 쓰는 서비스 묶음. 첫 요청 때 한 번 만든다(앱을 켤 때 DB·설정을 건드리지 않게)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import httpx
from fastapi import Request

from app import db
from app.config import Settings, load_settings
from app.youtube.client import YouTubeClient
from app.youtube.quota import Clock, QuotaTracker, SearchCache, utc_now
from app.youtube.service import VideoService


@dataclass
class Services:
    settings: Settings
    quota: QuotaTracker
    videos: VideoService

    def close(self) -> None:
        self.videos.client.close()


def build_services(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
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
    return Services(settings=settings, quota=quota, videos=videos)


class ServiceHolder:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._settings = settings
        self._transport = transport
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
                    self.settings, transport=self._transport, clock=self._clock
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
