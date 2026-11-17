"""①칸 영상 불러오기 API와 ②칸 영상 맥락 API(3단계). 얇게: 입력 검증 → 서비스 → 응답."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.analysis.context import VideoContext
from app.api.deps import Services, get_services
from app.schemas import (
    CommentedOut,
    ContextOut,
    ResolveIn,
    TranscriptIn,
    VideoItemOut,
    VideoListOut,
    VideoOut,
)

router = APIRouter(prefix="/api/videos", tags=["videos"])

ServicesDep = Annotated[Services, Depends(get_services)]


def _mark_commented(items: list[VideoOut], services: Services) -> None:
    """7단계: 영상마다 댓글을 단(게시 완료) 대상을 붙인다. 기존 필드는 그대로."""
    marks = services.rules.commented_map(v.video_id for v in items)
    # 2026-11-18: 이미 읽은 영상에만 「자막 있음/없음」(저장된 맥락만 본다, 새로 읽지 않는다)
    read = services.context.transcript_map([v.video_id for v in items])
    for item in items:
        item.commented = CommentedOut(**marks.get(item.video_id, {}))
        if item.video_id in read:
            item.transcript = "yes" if read[item.video_id] else "no"


@router.get("", response_model=VideoListOut)
def list_videos(
    services: ServicesDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    order: Literal["date", "relevance", "viewCount"] = "date",
    period: Literal["day", "week", "month", "any"] = "week",
    max_results: Annotated[int | None, Query(ge=1, le=50)] = None,
    exclude_shorts: bool | None = None,
) -> VideoListOut:
    """입력 없이 부르면 config.yaml의 discover.query·max_results로 최신 영상을 찾는다.

    `exclude_shorts`(선택, 비우면 config.yaml의 discover.exclude_shorts = 기본 참): 쇼츠(61초 미만·
    길이 없음)를 빼고 `max_results`개를 채운다. 응답의 `shorts_excluded`가 뺀 수다.
    """
    discover = services.settings.discover
    query = (q or "").strip() or discover.query
    result = services.videos.search(
        query,
        order=order,
        period=period,
        max_results=max_results or discover.max_results,
        exclude_shorts=discover.exclude_shorts if exclude_shorts is None else exclude_shorts,
    )
    out = VideoListOut.from_result(result, services.quota.summary())
    _mark_commented(out.items, services)
    return out


@router.get("/rising", response_model=VideoListOut)
def rising_videos(services: ServicesDep, exclude_shorts: bool | None = None) -> VideoListOut:
    """뜨기 직전 영상(R4, 가점). 조건은 설정 `rising.*`. 같은 요청은 10분 저장(검색 1회 100단위).

    이 목록의 영상은 초안까지만 된다(게시 작업 시작을 거절한다).
    """
    discover = services.settings.discover
    result = services.rising.find(
        exclude_shorts=discover.exclude_shorts if exclude_shorts is None else exclude_shorts
    )
    out = VideoListOut.from_rising(result, services.quota.summary())
    _mark_commented(out.items, services)
    return out


@router.post("/resolve", response_model=VideoItemOut)
def resolve_video(body: ResolveIn, services: ServicesDep) -> VideoItemOut:
    stored = services.videos.resolve(body.url)
    item = VideoOut.from_stored(stored)
    _mark_commented([item], services)
    return VideoItemOut(item=item, quota=services.quota.summary())


@router.get("/{video_id}", response_model=VideoItemOut)
def get_video(video_id: str, services: ServicesDep) -> VideoItemOut:
    stored = services.videos.get(video_id)
    item = VideoOut.from_stored(stored)
    _mark_commented([item], services)
    return VideoItemOut(item=item, quota=services.quota.summary())


# ---------------------------------------------------------------- 3단계: 영상 맥락


def _context_out(context: VideoContext, services: Services) -> ContextOut:
    return ContextOut.from_context(
        context,
        context_chars=services.context.context_chars,
        quota=services.quota.summary(),
        auto_transcript=services.context.auto_enabled,
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
