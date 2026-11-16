"""API 입출력 모델 (pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.analyzer import Analysis
from app.analysis.context import VideoContext
from app.analysis.drafter import Draft
from app.analysis.validator import Validation, ValidatorRules
from app.llm.prompts import SOURCE_LABELS
from app.ops.ledger import Run, TodayStats
from app.ops.profiles import Profile
from app.transcript.manual import MAX_TRANSCRIPT_CHARS
from app.youtube.service import SearchResult, StoredVideo
from app.youtube.url_parser import watch_url


class CommentedOut(BaseModel):
    """7단계: 그 대상에 댓글을 단(게시 완료) 영상인지. 01칸 「댓글 단 영상」 표시."""

    sandbox: bool = False
    youtube: bool = False


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
    commented: CommentedOut = Field(default_factory=CommentedOut)  # 7단계(필드 추가)

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


class ProblemOut(BaseModel):
    kind: str
    message: str
    action: str


class AIStatusOut(BaseModel):
    """위 줄 AI 상태(4단계). `local`이 거짓이면 「외부」(영상 자료가 그 회사로 간다)."""

    provider: str
    model: str
    reachable: bool
    installed: bool
    local: bool
    error: ProblemOut | None = None  # 문제가 있을 때만: 무엇이 문제이고 무엇을 하면 되는지


class StatusOut(BaseModel):
    """사이드바 시스템 상태. 키는 있는지 없는지만 알려 준다(값은 절대 싣지 않는다)."""

    youtube: YouTubeStatusOut
    ai: AIStatusOut


class WarmupOut(BaseModel):
    provider: str
    model: str
    seconds: float  # 모델을 불러 두는 데 걸린 시간(이미 올라가 있으면 거의 0)


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


# ---------------------------------------------------------------- 5단계: 분석과 초안


class EvidenceOut(BaseModel):
    quote: str
    source: Literal["transcript", "title", "description", "comment"]
    source_label: str  # 자막 · 제목 · 설명 · 댓글


class AnalysisOut(BaseModel):
    """02칸 「영상 맥락 분석」 다섯 줄."""

    video_id: str
    topic: str
    concern: str  # 과제의 "고민 한 줄"
    tone: str
    viewer_needs: str
    evidence: list[EvidenceOut]
    dropped_count: int  # 모델이 고른 근거 중 영상 자료에 없어서 버린 수
    fallback: bool  # 근거가 모두 버려져 제목을 근거로 썼는지
    model: str
    created_at: str

    @classmethod
    def from_analysis(cls, a: Analysis) -> AnalysisOut:
        return cls(
            video_id=a.video_id,
            topic=a.topic,
            concern=a.concern,
            tone=a.tone,
            viewer_needs=a.viewer_needs,
            evidence=[
                EvidenceOut(quote=e.quote, source=e.source, source_label=e.source_label)
                for e in a.evidence
            ],
            dropped_count=len(a.dropped),
            fallback=a.fallback,
            model=a.model,
            created_at=a.created_at,
        )


class DraftCreateIn(BaseModel):
    video_id: str = Field(min_length=1, max_length=64)
    # [다른 초안 생성]: 이미 쓴 근거 구절. 비우면 서버가 그 영상 초안들의 근거를 피한다(another)
    avoid_quotes: list[str] = Field(default_factory=list, max_length=20)
    another: bool = False


class DraftPatchIn(BaseModel):
    body: str = Field(max_length=2000)


class DraftOut(BaseModel):
    id: int
    video_id: str
    body: str  # 표기를 포함한 전체 글
    evidence_quote: str
    evidence_source: str
    evidence_label: str
    tone_label: str
    model: str
    attempts: int
    first_passed: bool
    passed: bool
    status: Literal["draft", "approved", "superseded"]
    edited_by_human: bool
    created_at: str
    updated_at: str
    approved_at: str | None
    validation: ValidationOut

    @classmethod
    def from_draft(cls, d: Draft, rules: ValidatorRules) -> DraftOut:
        return cls(
            id=d.id,
            video_id=d.video_id,
            body=d.body,
            evidence_quote=d.evidence_quote,
            evidence_source=d.evidence_source,
            evidence_label=SOURCE_LABELS.get(d.evidence_source, ""),
            tone_label=d.tone_label,
            model=d.model,
            attempts=d.attempts,
            first_passed=d.first_passed,
            passed=d.passed,
            status=d.status,  # type: ignore[arg-type]
            edited_by_human=d.edited_by_human,
            created_at=d.created_at,
            updated_at=d.updated_at,
            approved_at=d.approved_at,
            validation=ValidationOut.from_validation(d.validation, rules),
        )


class DraftListOut(BaseModel):
    video_id: str
    items: list[DraftOut]  # 최신이 위


# ---------------------------------------------------------------- 7단계: 운영 규칙과 기록

TARGET_LABELS = {"sandbox": "테스트 페이지", "youtube": "유튜브", "": ""}
ACTION_LABELS = {
    "analyze": "AI 분석",
    "draft": "초안 생성",
    "approve": "초안 승인",
    "post": "댓글 게시",
}


def status_label(action: str, result: str) -> str:
    if action == "post":
        return {"success": "게시 완료", "failure": "게시 실패"}.get(result, "진행")
    return {"failure": "실패"}.get(result, "완료")


class ProfileOut(BaseModel):
    name: str  # 화면 이름(유튜브1)
    folder: str  # 폴더 이름(profile-1). PC의 전체 경로는 싣지 않는다
    last_used_at: str | None  # 그 대상에서 마지막으로 예약한 시각(없으면 null)

    @classmethod
    def from_profile(cls, p: Profile, last_used: dict[str, str]) -> ProfileOut:
        return cls(name=p.name, folder=p.folder, last_used_at=last_used.get(p.name))


class ProfilesOut(BaseModel):
    target: Literal["sandbox", "youtube"]
    items: list[ProfileOut]
    auto: str  # 「자동 배정」이면 지금 고를 프로필(가장 오래 안 쓴 것)


class RunOut(BaseModel):
    """작업 기록 한 줄(UI_SPEC 2.7). 화면 캡처는 있는지만 알린다(경로는 싣지 않는다)."""

    id: int
    at: str
    day: str
    action: Literal["analyze", "draft", "approve", "post"]
    action_label: str
    video_id: str
    video_title: str
    video_url: str
    profile: str
    comment_text: str
    target: Literal["", "sandbox", "youtube"]
    target_label: str
    result: Literal["success", "failure", "info"]
    status_label: str
    reason: str
    has_screenshot: bool
    job_id: str

    @classmethod
    def from_run(cls, r: Run) -> RunOut:
        return cls(
            id=r.id,
            at=r.at,
            day=r.day,
            action=r.action,  # type: ignore[arg-type]
            action_label=ACTION_LABELS.get(r.action, r.action),
            video_id=r.video_id,
            video_title=r.video_title,
            video_url=watch_url(r.video_id) if r.video_id else "",
            profile=r.profile,
            comment_text=r.comment_text,
            target=r.target,  # type: ignore[arg-type]
            target_label=TARGET_LABELS.get(r.target, r.target),
            result=r.result,  # type: ignore[arg-type]
            status_label=status_label(r.action, r.result),
            reason=r.reason,
            has_screenshot=bool(r.screenshot_path),
            job_id=r.job_id,
        )


class RecordsOut(BaseModel):
    items: list[RunOut]  # 최신이 위
    total: int  # 전체 기록 수(화면은 최근 몇 줄만 보인다)


class TodayStatsOut(BaseModel):
    target: Literal["sandbox", "youtube"]
    target_label: str
    day: str  # 한국 날짜
    videos: int  # 오늘 처리한 영상(예약 + 게시, 상한에 세는 수)
    daily_limit: int
    remaining: int
    drafts: int
    posted: int
    failed: int
    success_rate: float | None  # 0~1. 오늘 게시 시도가 없으면 null(화면은 –)

    @classmethod
    def from_stats(cls, t: TodayStats) -> TodayStatsOut:
        return cls(
            target=t.target,  # type: ignore[arg-type]
            target_label=TARGET_LABELS[t.target],
            day=t.day,
            videos=t.videos,
            daily_limit=t.daily_limit,
            remaining=t.remaining,
            drafts=t.drafts,
            posted=t.posted,
            failed=t.failed,
            success_rate=t.success_rate,
        )
