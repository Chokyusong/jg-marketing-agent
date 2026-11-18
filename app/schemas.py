"""API 입출력 모델 (pydantic)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer

from app.analysis.analyzer import Analysis
from app.analysis.context import VideoContext, context_material
from app.analysis.drafter import Draft
from app.analysis.validator import Validation, ValidatorRules
from app.llm.prompts import SOURCE_LABELS
from app.ops.ledger import Run, TodayStats
from app.ops.profiles import Profile
from app.transcript.auto import source_label
from app.transcript.manual import MAX_TRANSCRIPT_CHARS
from app.youtube.rising import RisingResult
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
    # 2026-11-18 자료가 얇은 영상: 이미 읽은 영상만 yes(자막 있음)·no(자막 없음), 안 읽었으면 빈 글
    # (목록을 불러도 자막을 미리 읽지 않는다)
    transcript: Literal["yes", "no", "thin", ""] = ""
    # R4: 뜨기 직전 목록에서 온 영상만(시간당 조회수, 「뜨기 직전」 표시). 초안까지만 된다
    views_per_hour: float | None = None
    rising: bool = False

    @classmethod
    def from_stored(cls, stored: StoredVideo) -> VideoOut:
        data = stored.to_dict()
        return cls(url=watch_url(stored.video.video_id), **data)


class QuotaOut(BaseModel):
    used_today: int
    daily_limit: int


class RisingRuleOut(BaseModel):
    """뜨기 직전 영상 조건(설정값). 화면의 "조회수 1,000~5,000 · 시간당 150회 이상" 문구."""

    query: str
    min_views: int
    max_views: int
    min_views_per_hour: int
    window_hours: int


class VideoListOut(BaseModel):
    query: str
    order: str
    period: str
    max_results: int
    cached: bool
    items: list[VideoOut]
    quota: QuotaOut
    # 실제 데이터 보정(필드 추가): 쇼츠(61초 미만·길이 없음)를 뺐는지와 뺀 수
    exclude_shorts: bool = False
    shorts_excluded: int = 0
    # R4: 'search'(검색) | 'rising'(뜨기 직전 영상). rising이면 조건과 조건을 본 영상 수
    mode: Literal["search", "rising"] = "search"
    rising: RisingRuleOut | None = None
    checked: int = 0

    @classmethod
    def from_rising(cls, result: RisingResult, quota: dict[str, int]) -> VideoListOut:
        items = []
        for item in result.items:
            out = VideoOut.from_stored(item.stored)
            out.views_per_hour = round(item.views_per_hour, 1)
            out.rising = True
            items.append(out)
        rule = result.rule
        return cls(
            query=result.query, order="date", period="34h", max_results=len(items),
            cached=result.cached, items=items, quota=QuotaOut(**quota),
            exclude_shorts=result.exclude_shorts, shorts_excluded=result.shorts_excluded,
            mode="rising", checked=result.checked,
            rising=RisingRuleOut(
                query=rule.query, min_views=rule.min_views, max_views=rule.max_views,
                min_views_per_hour=rule.min_views_per_hour, window_hours=34,
            ),
        )

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
            exclude_shorts=result.exclude_shorts,
            shorts_excluded=result.shorts_excluded,
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
    # R4: 모델이 지금 메모리에 올라가 있는지(모르면 null). 아니면 첫 답이 1~3분 걸린다
    loaded: bool | None = None
    # R4: 추천 모델(코드 기본값)과 그것이 이 PC에 설치돼 있는지. 시작 준비 상자의 [바꾸기]
    recommended_model: str = ""
    recommended_installed: bool = False
    # R5: 화면에 보일 AI 이름, 어디서 도는지(local 이 PC · api API 키 · program 로그인된 프로그램),
    # 영상 자료가 가는 곳(외부일 때 알림 문구). 추천 모델은 Ollama일 때만 채운다
    label: str = ""
    kind: Literal["local", "api", "program"] = "local"
    sends_to: str = ""


class BrowserProfileOut(BaseModel):
    name: str  # 화면 이름(유튜브1)
    folder: str  # 폴더 이름(profile-1). PC의 전체 경로는 싣지 않는다
    exists: bool  # 프로필 폴더가 이미 있는지
    # R2: 로그인 확인 결과(확인한 적 없으면 signed_in null). 아이디·비밀번호는 없다
    signed_in: bool | None = None
    channel_name: str = ""
    checked_at: str | None = None
    login_window_open: bool = False  # 프로그램이 연 로그인·유튜브 창이 아직 열려 있는지
    login_checking: bool = False  # 지금 로그인을 확인하는 중인지(로그인 확인 고침)
    login_checking_auto: bool = False  # 창을 닫아 저절로 시작한 확인인지


class AutoPickOut(BaseModel):
    """자동 배정이 이번에 고를 프로필과 까닭."""

    name: str
    confirmed: bool | None = None  # True 확인된 것 중에서 · False 확인된 것 없음 · None 연습
    note: str = ""


class BrowserStatusOut(BaseModel):
    """위 줄 BROWSER 상태(8단계)."""

    chrome_found: bool
    playwright_ready: bool  # 자동 입력(실제 게시·연습 모드)에 필요한 Playwright가 설치돼 있는지
    profiles: list[BrowserProfileOut]
    active_job_id: str | None = None  # 진행 중인 게시 작업(화면을 새로 고쳐도 이어 보게)
    # R3: 화면이 쓰는 게시 설정(설정 화면에서 바꾸면 바로 바뀐다)
    confirm_before_post: bool = False  # 게시 직전 확인(켜면 입력 뒤 [게시])
    disclose_default: bool = True  # 「광고 표기 붙이기」의 처음 상태
    login_trust_seconds: int = 3600  # 이보다 최근의 「로그인 안 됨」 확인이면 [댓글 달기]를 막는다
    # 2026-11-17: 「자동 배정」이 이번에 쓸 프로필(대상별). ③칸 「자동 배정 · 이번에는 유튜브2」
    auto_pick: dict[str, AutoPickOut] = Field(default_factory=dict)


class StatusOut(BaseModel):
    """사이드바 시스템 상태. 키는 있는지 없는지만 알려 준다(값은 절대 싣지 않는다)."""

    youtube: YouTubeStatusOut
    ai: AIStatusOut
    browser: BrowserStatusOut | None = None  # 8단계


class LLMLoadedOut(BaseModel):
    """R4: 모델이 메모리에 올라가 있는지(`GET /api/ps`). 모르면 null."""

    provider: str
    model: str
    loaded: bool | None
    cold_timeout_seconds: float


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
    transcript_source: Literal["manual", "auto", "unofficial", "none"]
    transcript_chars: int
    # 붙여 넣은 자막(고쳐 쓸 수 있게 글 상자에 다시 채운다). R4: 자동으로 읽은 자막은 싣지 않는다
    # (글자 수·언어만. 글 상자는 사람이 넣는 곳이다)
    transcript_text: str
    comment_count: int
    comments_disabled: bool
    truncated: bool  # 모델 입력 한도(context_chars)에 맞추느라 줄였는지
    transcript_truncated: bool
    context_chars: int
    built_at: str
    quota: QuotaOut
    # 옛 화면 호환으로 남긴 칸. R3부터 광고 표기는 모든 영상에서 켜고 끌 수 있어 늘 false다
    own_video: bool = False
    # R4: 자막 자동 읽기. 언어 코드(ko 등)·자동 생성 여부·화면용 이름(「한국어, 자동 생성」),
    # 자동으로 못 읽었을 때 이유 코드(none·disabled·blocked·timeout·off …)와 한 줄
    transcript_language: str = ""
    transcript_generated: bool | None = None
    transcript_label: str = ""
    transcript_reason: str = ""
    transcript_note: str = ""
    auto_transcript: bool = True  # 「자막 자동으로 읽기」가 켜져 있는지
    # 2026-11-18 자료 상태: yes 자막 있음 · no 자막 없음(제목·설명·댓글로 씀) · thin 자료 부족
    material: Literal["yes", "no", "thin"] = "no"

    @classmethod
    def from_context(
        cls,
        context: VideoContext,
        *,
        context_chars: int,
        quota: dict[str, int],
        own_video: bool = False,
        auto_transcript: bool = True,
    ) -> ContextOut:
        auto = context.transcript_source == "auto"
        return cls(
            own_video=own_video,
            video_id=context.video_id,
            body_source=context.body_source,
            transcript_source=context.transcript_source,
            transcript_chars=context.transcript_chars,
            transcript_text="" if auto else context.transcript_text,
            transcript_language=context.transcript_language,
            transcript_generated=context.transcript_generated,
            transcript_label=(
                source_label(context.transcript_language, context.transcript_generated)
                if auto else ""
            ),
            transcript_reason=context.transcript_reason,
            transcript_note=context.transcript_note,
            auto_transcript=auto_transcript,
            material=context_material(context),
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
    # R3: 광고 표기를 켰는지. 끄면 V4가 「표기 끔」으로 통과한다
    # (표기가 있으면 맨 앞이어야 하는 것은 같다)
    disclose: bool = True


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
    fallback: bool  # (예전) 근거가 모두 버려져 제목을 근거로 썼는지. 이제는 멈추므로 늘 거짓
    model: str
    created_at: str
    # 실제 데이터 보정(필드 추가): 연애 고민이 없으면 분석이 no_love_concern 오류로 멈추므로
    # 응답으로 온 분석은 늘 참이다. love_reason은 모델이 적은 판단 까닭(저장된 분석에는 없다)
    has_love_concern: bool = True
    love_reason: str = ""
    key_phrases: list[str] = []  # C1: 그 영상의 핵심 말(예전 분석은 제목·해시태그에서 뽑은 것)

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
            has_love_concern=a.has_love_concern,
            love_reason=a.love_reason,
            key_phrases=list(a.key_phrases),
        )


class DraftCreateIn(BaseModel):
    video_id: str = Field(min_length=1, max_length=64)
    # [다른 초안 생성]: 이미 쓴 근거 구절. 비우면 서버가 그 영상 초안들의 근거를 피한다(another)
    avoid_quotes: list[str] = Field(default_factory=list, max_length=20)
    another: bool = False
    # 광고 표기를 붙일지(R3: 모든 영상에서 켜고 끌 수 있다). 비우면 설정의 「광고 표기 기본값」
    disclose: bool | None = None
    # AI 검수 한 번(2026-11-18): 비우면 규칙 검사를 통과한 초안을 바로 검수한다(설정이 켜져 있을
    # 때). false면 「pending」으로 두고 화면이 POST /api/drafts/{id}/review를 따로 부른다
    review: bool | None = None


class DraftPatchIn(BaseModel):
    body: str = Field(max_length=2000)


class DraftDisclosureIn(BaseModel):
    """R3: 초안의 광고 표기를 붙이거나 뗀다(저장된 글에서 표기만 바꾸고 다시 검사)."""

    disclose: bool


class ReviewOut(BaseModel):
    """AI 검수 한 번(2026-11-18).

    status: passed | rewritten | flagged | error | off | pending | 빈 글(안 함)."""

    status: str = ""
    label: str = ""  # 화면에 보이는 한 줄(없으면 빈 글)
    problems: list[str] = Field(default_factory=list)  # 남은 문제(flagged일 때만)
    # 이야기 방식의 맥락 일치 검증(2026-11-18): 그 검증인지와 벗어난 문장(flagged일 때만)
    story: bool = False
    drift: str = ""

    @model_serializer(mode="wrap")
    def _drop_story_fields(self, handler):
        """조각 맞추기의 검수 답은 예전 모양 그대로(story·drift 칸은 이야기 방식일 때만)."""
        data = handler(self)
        if not self.story and isinstance(data, dict):
            data.pop("story", None)
            data.pop("drift", None)
        return data

    @classmethod
    def from_review(cls, review: dict | None) -> ReviewOut:
        from app.analysis import review as rv

        data = review or {}
        status = str(data.get("status") or "")
        story = bool(data.get("story"))
        flagged = status == rv.FLAGGED
        problems = [str(p) for p in data.get("problems") or []] if flagged else []
        label = rv.label(status, story=story)
        missing = [str(m) for m in data.get("missing") or []]
        if status == rv.INCOMPLETE and missing:  # 2026-11-18: 빠진 칸을 통과와 구분해 보인다
            label = f"{label}(빠진 칸: {', '.join(missing)})"
        return cls(status=status, label=label, problems=problems,
                   story=story, drift=str(data.get("drift") or "") if flagged else "")


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
    disclosed: bool = True  # 광고 표기를 붙인 초안인지(R3: 모든 영상에서 켜고 끌 수 있다)
    review: ReviewOut = Field(default_factory=ReviewOut)  # AI 검수 한 번(2026-11-18)

    @classmethod
    def from_draft(cls, d: Draft, rules: ValidatorRules) -> DraftOut:
        return cls(
            disclosed=d.disclosed,
            review=ReviewOut.from_review(d.review),
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

TARGET_LABELS = {"sandbox": "연습", "youtube": "유튜브", "": ""}  # 11-17: 옛 「테스트 페이지」
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
    # R2: 로그인 확인 결과(필드 추가)
    exists: bool = False
    signed_in: bool | None = None
    channel_name: str = ""
    checked_at: str | None = None
    login_state: Literal["signed_in", "signed_out", "unknown"] | None = None
    login_note: str = ""
    login_window_open: bool = False
    login_checking: bool = False  # 지금 로그인을 확인하는 중인지
    login_checking_auto: bool = False  # 창을 닫아 저절로 시작한 확인인지

    @classmethod
    def from_profile(cls, p: Profile, last_used: dict[str, str]) -> ProfileOut:
        return cls(name=p.name, folder=p.folder, last_used_at=last_used.get(p.name))


class ProfilesOut(BaseModel):
    target: Literal["sandbox", "youtube"]
    items: list[ProfileOut]
    auto: str  # 「자동 배정」이면 지금 고를 프로필(가장 오래 안 쓴 것)
    # 2026-11-17: 실제 게시는 로그인이 확인된 프로필 중에서만 고른다(없으면 False와 안내)
    auto_confirmed: bool | None = None
    auto_note: str = ""


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
    disclosed: bool | None = None  # R3: 그 댓글이 광고 표기를 붙였는지(댓글이 없는 줄은 null)

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
            disclosed=r.disclosed,
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


# ---------------------------------------------------------------- 8단계: 게시 작업


class JobIn(BaseModel):
    video_id: str
    draft_id: int
    profile: str = ""  # 비우면 자동 배정
    # R3: sandbox = 연습 모드, youtube = 실제 게시(어떤 영상이든). 옛 이름 assist·youtube_auto도
    # 받아서 실제 게시로 처리한다
    target: Literal["sandbox", "assist", "youtube", "youtube_auto"] = "sandbox"
    daily_limit: int | None = Field(default=None, ge=0, le=1000)  # 화면에서 낮춘 상한
    fail: Literal["", "hide_button", "slow", "reject"] = ""  # 테스트 페이지 실패 스위치(시험용)


class JobConfirmIn(BaseModel):
    posted: bool


class JobEventOut(BaseModel):
    at: str
    state: str
    message: str


class JobOut(BaseModel):
    """게시 작업 한 건(0.5초마다 화면이 물어 온다).

    프로필 폴더의 전체 경로·캡처 경로는 싣지 않는다.
    """

    id: str
    mode: Literal["sandbox", "youtube"]  # 연습 모드 | 실제 게시
    target: Literal["sandbox", "youtube"]
    target_label: str
    state: str
    state_label: str
    step: int  # 진행 단계 표시(대기·프로필 실행·댓글 입력·승인 대기·게시·확인)의 지금 칸, 끝나면 6
    finished: bool
    video_id: str
    draft_id: int
    profile: str
    folder: str
    comment_text: str
    message: str
    reason: str  # 실패 사유(실패했을 때만)
    verified: bool | None  # 게시를 확인했는지(「댓글」을 눌렀지만 내 댓글을 못 찾으면 false)
    has_screenshot: bool
    screenshot_url: str | None
    view_url: str  # [댓글 보기]
    waiting_for: Literal["approve", "confirm"] | None  # approve: 게시 직전 확인(설정 켬)에서 [게시]
    seconds_left: int | None
    created_at: str
    finished_at: str | None
    events: list[JobEventOut]
    confirm_before_post: bool = False  # 입력 뒤 [게시]를 기다리는 작업인지(설정 「게시 직전 확인」)
    disclosed: bool = True  # 그 댓글이 광고 표기를 붙였는지
    window_open: bool = False  # 게시 뒤 크롬 창이 아직 열려 있는지(2026-11-18)

    @classmethod
    def from_view(cls, v) -> JobOut:  # v: app.browser.jobs.JobView
        return cls(
            id=v.id,
            mode=v.mode,
            target=v.target,
            target_label=TARGET_LABELS.get(v.target, v.target),
            state=v.state,
            state_label=v.state_label,
            step=v.step,
            finished=v.finished,
            video_id=v.video_id,
            draft_id=v.draft_id,
            profile=v.profile,
            folder=v.folder,
            comment_text=v.comment_text,
            message=v.message,
            reason=v.reason,
            verified=v.verified,
            has_screenshot=v.has_screenshot,
            screenshot_url=f"/api/jobs/{v.id}/screenshot" if v.has_screenshot else None,
            view_url=v.view_url,
            waiting_for=v.waiting_for,
            seconds_left=v.seconds_left,
            created_at=v.created_at,
            finished_at=v.finished_at,
            events=[JobEventOut(at=e.at, state=e.state, message=e.message) for e in v.events],
            confirm_before_post=v.confirm_before_post,
            disclosed=v.disclosed,
            window_open=v.window_open,
        )


# ---------------------------------------------------------------- 9단계: SETTINGS 패널(읽기 전용)


class SettingsCommentOut(BaseModel):
    min_chars: int
    max_chars: int
    disclosure: str  # 홍보 표기([광고])
    brand: str
    own_video_count: int = 0  # 옛 칸(R3부터 내 채널 영상 구분이 없어 늘 0)


class SettingsProfileOut(BaseModel):
    name: str  # 화면 이름(유튜브1)
    folder: str  # 폴더 이름(profile-1). PC의 전체 경로는 싣지 않는다
    ready: bool  # 프로필 폴더가 이미 있는지


class SettingsLLMOut(BaseModel):
    """지금 쓰는 LLM. 주소·키는 싣지 않는다(모델을 부르지 않고 설정만 읽는다)."""

    active: str  # llm.active(공급자 이름)
    type: str  # 공급자 종류(ollama 등). 모르는 이름이면 빈 글
    model: str
    local: bool  # 이 PC 안에서 도는지(거짓이면 「외부」 — 영상 자료가 그 회사로 간다)
    timeout_seconds: float
    keep_alive: str
    context_chars: int
    error: ProblemOut | None = None  # 설정이 틀려 공급자를 못 만들었을 때
    # R4: 모델이 아직 메모리에 없을 때 기다리는 시간, 켤 때 미리 불러오기, 추천 모델(코드 기본값)
    cold_timeout_seconds: float = 420.0
    warmup_on_start: bool = True
    recommended_model: str = ""
    # R5
    label: str = ""
    kind: Literal["local", "api", "program"] = "local"
    sends_to: str = ""


class SettingsBrowserOut(BaseModel):
    default_target: Literal["sandbox", "youtube"]
    default_target_label: str
    headless: bool
    window_position: str  # 설정값 "x,y"
    window_position_used: str | None  # 실제로 띄울 위치(화면 밖이면 바꾼 값)
    window_position_adjusted: bool
    window_position_checked: bool  # 모니터 정보를 읽어 확인했는지
    window_position_note: str
    typing_delay_ms: list[int]
    # 2026-11-17 창 위치 자동(필드 추가): 고른 화면(auto · 모니터 ID · 빈 값=옛 좌표)과 지금 뜰 곳
    window_screen: str = "auto"
    window_auto: bool = True
    window_where: str = ""  # 「지금은 모니터 2(위쪽)에 뜹니다」
    window_size_used: str = ""  # 「1280×900」(크롬 DIP)
    window_fell_back: bool = False  # 고른 모니터가 없어 자동으로 떨어졌는지
    chrome_found: bool
    playwright_ready: bool


class SettingsYouTubeOut(BaseModel):
    key_configured: bool  # 키는 있는지 없는지만(값은 절대 싣지 않는다)
    quota: QuotaOut
    # R2: 어디서 왔는지(program 프로그램에 저장 / dev_file 개발용 .env·환경 변수 / null 없음)
    key_source: Literal["program", "dev_file"] | None = None
    can_store_key: bool = True  # 이 PC에서 키를 암호화해 저장할 수 있는지(Windows)


class SettingsDiscoverOut(BaseModel):
    query: str
    max_results: int
    exclude_shorts: bool
    shorts_under_seconds: int = 181  # R2: 이보다 짧은 영상을 쇼츠로 본다


class SettingsOut(BaseModel):
    """SETTINGS 패널(9단계). 비밀값(키)·PC의 경로·LLM 주소는 싣지 않는다."""

    version: str
    stage: int
    comment: SettingsCommentOut
    brand_facts: list[str]
    daily_max_comments: int
    profiles: list[SettingsProfileOut]
    llm: SettingsLLMOut
    browser: SettingsBrowserOut
    youtube: SettingsYouTubeOut
    discover: SettingsDiscoverOut
    transcript_provider: str
    edit: SettingsEditOut | None = None  # R2: 편집에 필요한 지금 값·기본값·고를 수 있는 값


# ---------------------------------------------------------------- R2: 설정 저장과 프로필 로그인


class ChoiceOut(BaseModel):
    value: str
    label: str


class SettingsEditOut(BaseModel):
    """설정 화면이 편집에 쓰는 값. 칸 이름은 `app/user_settings.FIELDS`와 같다(키 값은 없다)."""

    values: dict[str, Any]  # 지금 쓰는 값
    defaults: dict[str, Any]  # config.yaml(·개발용 .env)의 값 = [기본값으로] 누르면 돌아갈 값
    changed: list[str]  # 프로그램 안에서 바꿔 저장한 칸
    ranges: dict[str, list[int]]  # 숫자 칸의 [최소, 최대]
    typing_speeds: list[ChoiceOut]
    writers: list[ChoiceOut] = Field(default_factory=list)  # 댓글 쓰는 방식(2026-11-18)
    # 게시 뒤 크롬 창: 열어 두기(5분) · 바로 닫기(2026-11-18)
    after_post_windows: list[ChoiceOut] = Field(default_factory=list)
    store_ready: bool  # 저장할 곳이 있는지(실제 프로그램은 늘 참)
    applies_later: list[str]  # 값은 저장하지만 동작에는 다음 단계(R3)에서 쓰는 칸


class SettingsUpdateIn(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class YouTubeKeyIn(BaseModel):
    key: str = Field(min_length=1, max_length=400)


class YouTubeKeyOut(BaseModel):
    """키 저장·지우기 결과. 키 값은 싣지 않는다."""

    key_configured: bool
    key_source: Literal["program", "dev_file"] | None
    can_store_key: bool


class KeyTestOut(BaseModel):
    ok: bool
    result: Literal["ok", "no_key", "rejected", "quota", "network", "error"]
    message: str
    action: str = ""
    quota: QuotaOut


class LLMModelOut(BaseModel):
    name: str
    kind: Literal["general", "code", "embed"]
    size_gb: float | None = None
    current: bool = False
    label: str | None = None  # R5: 회사가 붙인 보기 이름(있을 때만)
    # 2026-11-18 그 모델이 받는 추론 수준과 기본(Codex `debug models`, 필드 추가. 모르면 빈 값)
    reasoning_levels: list[str] = []
    default_reasoning: str = ""


class LLMModelsOut(BaseModel):
    reachable: bool  # Ollama에 닿았는지(R5: ?provider=면 그 AI에 닿았는지)
    current: str  # 지금 쓰는 모델
    current_installed: bool
    items: list[LLMModelOut]
    # R5: ?provider=<이름>으로 물었을 때. 목록을 주지 않는 AI(로그인된 프로그램)는 manual_only
    provider: str = ""
    manual_only: bool = False
    error: ProblemOut | None = None
    # 2026-11-17 모델 고르는 목록(필드 추가): config.yaml `llm.providers.<이름>.models` 추천 목록,
    # 보일 목록의 출처(api 받아 옴 · recommended 추천 · none 없음 → 「직접 입력…」만),
    # 받아 오지 못했을 때 한 줄
    recommended: list[str] = []
    source: Literal["api", "recommended", "none"] = "api"
    note: str = ""


class InstallGuideOut(BaseModel):
    """[설치 방법 보기]: 공식 문서의 설치 명령과 페이지. 이 앱은 설치하지 않는다(2026-11-17)."""

    command: str
    page: str
    shell: str
    notes: list[str] = []
    checked: str  # 공식 문서로 확인한 날


class LLMProviderOut(BaseModel):
    """설정 화면 「AI」 목록 한 줄. 키 값·주소는 싣지 않는다(있는지와 어디서 왔는지만)."""

    name: str
    label: str
    type: str
    kind: Literal["local", "api", "program"]
    active: bool
    local: bool  # 거짓이면 영상 자료가 sends_to로 간다
    sends_to: str
    model: str
    needs_key: bool
    key_allowed: bool  # API 키를 넣을 수 있는 AI인지
    key_configured: bool
    key_source: Literal["program", "dev_file"] | None = None
    can_store_key: bool
    url_editable: bool  # 「직접 입력」: 주소를 적는다
    models_listable: bool  # [모델 불러오기]가 되는지(아니면 직접 적는다)
    installed: bool
    verified: bool  # 안전하게 실행하는 방법을 확인한 프로그램인지(아니면 고를 수 없다)
    unavailable_reason: str | None = None  # 고를 수 없는 이유(쉬운 한국어)
    # 2026-11-17 모델 고르는 목록(필드 추가): 추천 목록(받아 오기 전에 바로 보인다)과, 로그인된
    # 프로그램의 맨 위 칸 이름(「기본값 (그 프로그램이 정한 모델)」, 값은 빈 글)
    recommended_models: list[str] = []
    default_label: str = ""
    # 2026-11-17 로그인된 프로그램이 모델 목록 명령을 주는지(Codex `debug models`, 필드 추가)
    models_from_program: bool = False
    # 2026-11-18 추론 수준(필드 추가, 지금은 Codex만): 지금 쓸 값과, 모델 목록을 받아 오지 못했을 때
    # 보일 수준(config.yaml `reasoning_levels`). 빈 목록이면 화면에 「추론 수준」 칸이 없다
    reasoning: str = ""
    reasoning_levels: list[str] = []
    # 2026-11-17 아무 PC에서나 AI 연결(필드 추가): 로그인된 프로그램의 상태와
    # [설치 방법 보기]·[로그인하기]
    logged_in: bool | None = None  # 마지막으로 그 프로그램에 물어본 로그인 상태(모르면 None)
    # 2026-11-18 로그인 상태를 이번 실행에서 물어봤는지(필드 추가): 화면이 「모름」을 「준비됨」으로
    # 보이지 않고, 안 물어봤으면 「확인 중」으로 두고 물어본다
    login_asked: bool = False
    login_window_open: bool = False  # [로그인하기]로 연 명령 창이 아직 열려 있는지
    login_checking: bool = False  # 그 창이 닫혀 로그인 상태를 저절로 묻는 중인지
    can_open_login: bool = False  # [로그인하기]가 되는지(설치돼 있고 로그인 명령을 아는 프로그램)
    install_guide: InstallGuideOut | None = None  # [설치 방법 보기](공식 명령과 페이지)
    not_wired_notes: list[str] = []  # 고를 수 없는 프로그램의 까닭(쉬운 말)
    not_wired_page: str = ""  # 그 까닭을 적은 공식 페이지


class FirstRunPathOut(BaseModel):
    """처음 켠 PC에서 AI를 붙이는 길 하나(2026-11-17). 순서가 권하는 순서다."""

    key: Literal["program", "key", "ollama"]
    title: str
    detail: str
    providers: list[str]  # 이 길에서 열어 볼 AI 이름(설정 「AI 모델」의 칸)
    link: str = ""  # 공식 페이지(키 받는 곳·설치 안내)
    link_label: str = ""
    ready: bool = False  # 이 길로 이미 쓸 수 있는 AI가 있는지


class LLMProvidersOut(BaseModel):
    active: str
    items: list[LLMProviderOut]
    kinds: list[dict[str, str]]
    first_run: list[FirstRunPathOut] = []  # 2026-11-17 첫 실행 안내(필드 추가)


class LLMTestOut(BaseModel):
    ok: bool
    result: Literal[
        "ok", "no_key", "rejected", "rate_limited", "network", "not_installed",
        "not_logged_in", "no_url", "not_wired", "error",
    ]
    message: str
    action: str = ""
    models: int | None = None  # 키가 통하면 받아 온 모델 수
    version: str | None = None  # 로그인된 프로그램의 버전


class LLMKeyIn(BaseModel):
    key: str = Field(min_length=1, max_length=500)


class LLMKeyOut(BaseModel):
    """AI API 키 저장·지우기 결과. 키 값은 싣지 않는다."""

    name: str
    key_configured: bool
    key_source: Literal["program", "dev_file"] | None
    can_store_key: bool


class ScreenOut(BaseModel):
    id: str
    label: str
    left: int
    top: int
    width: int
    height: int
    primary: bool
    position: str  # 이 모니터를 고르면 쓸 창 위치 "x,y"
    current: bool  # 지금 창 위치가 이 모니터 안인지


class ScreensOut(BaseModel):
    checked: bool  # 모니터 정보를 읽었는지
    window_position: str  # 지금 설정한 창 위치
    items: list[ScreenOut]
    # 2026-11-17 창 위치 자동(필드 추가)
    screen: str = "auto"  # 지금 고른 것: auto · 모니터 ID · 빈 값(옛 좌표)
    where: str = ""  # 「지금은 모니터 2(위쪽)에 뜹니다」
    auto_where: str = ""  # 「자동 (권장)」을 고르면 뜰 곳
    note: str = ""  # 고른 모니터가 없어 자동으로 떨어졌을 때 등


class ProfileLoginOut(BaseModel):
    """로그인 창 열기·로그인 확인 결과."""

    name: str
    exists: bool
    signed_in: bool | None
    login_state: Literal["signed_in", "signed_out", "unknown"] | None
    channel_name: str
    checked_at: str | None
    note: str
    login_window_open: bool
    message: str  # 화면에 보일 한 줄
    login_checking: bool = False  # 지금 로그인을 확인하는 중인지
    login_checking_auto: bool = False
