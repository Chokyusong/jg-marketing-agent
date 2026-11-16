"""API 입출력 모델 (pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.context import VideoContext
from app.analysis.validator import Validation, ValidatorRules
from app.transcript.manual import MAX_TRANSCRIPT_CHARS
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


# ---------------------------------------------------------------- 3단계: 영상 맥락


class TranscriptIn(BaseModel):
    # 정리(공백 줄이기) 전 원문이라 넉넉히 받고, 정리한 뒤 20,000자 한도를 확인한다.
    text: str = Field(max_length=MAX_TRANSCRIPT_CHARS * 5)


class ContextOut(BaseModel):
    """맥락 요약. 02칸 「자막 출처」 줄이 이것을 그린다."""

    video_id: str
    body_source: Literal["transcript", "title_description"]
    transcript_source: Literal["manual", "unofficial", "none"]
    transcript_chars: int
    transcript_text: str  # 붙여 넣은 자막(고쳐 쓸 수 있게 글 상자에 다시 채운다)
    comment_count: int
    comments_disabled: bool
    truncated: bool  # 모델 입력 한도(context_chars)에 맞추느라 줄였는지
    transcript_truncated: bool
    context_chars: int
    built_at: str
    quota: QuotaOut

    @classmethod
    def from_context(
        cls, context: VideoContext, *, context_chars: int, quota: dict[str, int]
    ) -> ContextOut:
        return cls(
            video_id=context.video_id,
            body_source=context.body_source,
            transcript_source=context.transcript_source,
            transcript_chars=context.transcript_chars,
            transcript_text=context.transcript_text,
            comment_count=len(context.comments),
            comments_disabled=context.comments_disabled,
            truncated=context.truncated,
            transcript_truncated=context.transcript_truncated,
            context_chars=context_chars,
            built_at=context.built_at,
            quota=QuotaOut(**quota),
        )


# ---------------------------------------------------------------- 6단계: 규칙 검사


class ValidateIn(BaseModel):
    video_id: str = Field(min_length=1, max_length=64)
    # 120자 한도를 넘는 글도 검사해서 "몇 자 줄이세요"를 알려 준다. 너무 긴 글만 막는다.
    text: str = Field(max_length=2000)


class CheckOut(BaseModel):
    code: str
    name: str
    passed: bool
    message: str


class ValidationOut(BaseModel):
    """규칙 검사 결과. 02칸이 글자 수·통과 요약·실패 목록을 그린다."""

    passed: bool
    char_count: int
    min_chars: int
    max_chars: int
    disclosure: str
    evidence_quote: str | None
    passed_count: int
    total: int
    checks: list[CheckOut]

    @classmethod
    def from_validation(cls, result: Validation, rules: ValidatorRules) -> ValidationOut:
        checks = [CheckOut(**c.to_dict()) for c in result.checks]
        return cls(
            passed=result.passed,
            char_count=result.char_count,
            min_chars=rules.min_chars,
            max_chars=rules.max_chars,
            disclosure=rules.disclosure,
            evidence_quote=result.evidence_quote,
            passed_count=sum(c.passed for c in checks),
            total=len(checks),
            checks=checks,
        )
