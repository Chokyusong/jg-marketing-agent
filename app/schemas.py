"""API 입출력 모델 (pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.youtube.service import SearchResult, StoredVideo
from app.youtube.url_parser import watch_url


class VideoOut(BaseModel):
    video_id: str
    url: str
    title: str
    channel_id: str
    channel_title: str
    description: str
    published_at: str
    thumbnail_url: str
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    source: Literal["search", "link", "rising"]
    fetched_at: str

    @classmethod
    def from_stored(cls, stored: StoredVideo) -> VideoOut:
        data = stored.to_dict()
        return cls(url=watch_url(stored.video.video_id), **data)


class QuotaOut(BaseModel):
    used_today: int
    daily_limit: int


class VideoListOut(BaseModel):
    query: str
    order: str
    period: str
    max_results: int
    cached: bool
    items: list[VideoOut]
    quota: QuotaOut

    @classmethod
    def from_result(cls, result: SearchResult, quota: dict[str, int]) -> VideoListOut:
        return cls(
            query=result.query,
            order=result.order,
            period=result.period,
            max_results=result.max_results,
            cached=result.cached,
            items=[VideoOut.from_stored(s) for s in result.videos],
            quota=QuotaOut(**quota),
        )


class VideoItemOut(BaseModel):
    item: VideoOut
    quota: QuotaOut


class ResolveIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class YouTubeStatusOut(BaseModel):
    key_configured: bool
    quota: QuotaOut


class StatusOut(BaseModel):
    """사이드바 시스템 상태. 키는 있는지 없는지만 알려 준다(값은 절대 싣지 않는다)."""

    youtube: YouTubeStatusOut
