"""①칸 영상 불러오기 API와 ②칸 영상 맥락 API(3단계). 얇게: 입력 검증 → 서비스 → 응답."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.analysis.context import VideoContext
from app.api.deps import Services, get_services
from app.schemas import (
    ContextOut,
    ResolveIn,
    TranscriptIn,
    VideoItemOut,
    VideoListOut,
    VideoOut,
)

router = APIRouter(prefix="/api/videos", tags=["videos"])

ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("", response_model=VideoListOut)
def list_videos(
    services: ServicesDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    order: Literal["date", "relevance", "viewCount"] = "date",
    period: Literal["day", "week", "month", "any"] = "week",
    max_results: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> VideoListOut:
    """입력 없이 부르면 config.yaml의 discover.query·max_results로 최신 영상을 찾는다."""
    discover = services.settings.discover
    query = (q or "").strip() or discover.query
    result = services.videos.search(
        query, order=order, period=period, max_results=max_results or discover.max_results
    )
    return VideoListOut.from_result(result, services.quota.summary())


@router.post("/resolve", response_model=VideoItemOut)
def resolve_video(body: ResolveIn, services: ServicesDep) -> VideoItemOut:
    stored = services.videos.resolve(body.url)
    return VideoItemOut(item=VideoOut.from_stored(stored), quota=services.quota.summary())


@router.get("/{video_id}", response_model=VideoItemOut)
def get_video(video_id: str, services: ServicesDep) -> VideoItemOut:
    stored = services.videos.get(video_id)
    return VideoItemOut(item=VideoOut.from_stored(stored), quota=services.quota.summary())


# ---------------------------------------------------------------- 3단계: 영상 맥락


def _context_out(context: VideoContext, services: Services) -> ContextOut:
    return ContextOut.from_context(
        context, context_chars=services.context.context_chars, quota=services.quota.summary()
    )


@router.post("/{video_id}/context", response_model=ContextOut)
def build_context(video_id: str, services: ServicesDep, refresh: bool = False) -> ContextOut:
    """맥락을 만들고 요약을 돌려준다.

    저장된 인기 댓글이 있으면 다시 부르지 않는다. `refresh=true`면 새로 부른다(1단위).
    """
    return _context_out(services.context.build(video_id, refresh=refresh), services)


@router.put("/{video_id}/transcript", response_model=ContextOut)
def save_transcript(video_id: str, body: TranscriptIn, services: ServicesDep) -> ContextOut:
    return _context_out(services.context.set_manual_transcript(video_id, body.text), services)


@router.delete("/{video_id}/transcript", response_model=ContextOut)
def delete_transcript(video_id: str, services: ServicesDep) -> ContextOut:
    return _context_out(services.context.clear_manual_transcript(video_id), services)
