"""①칸 영상 불러오기 API. 얇게: 입력 검증 → 서비스 → 응답."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.schemas import ResolveIn, VideoItemOut, VideoListOut, VideoOut

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
