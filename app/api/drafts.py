"""분석과 초안 API(5단계). 얇게: 입력 검증 → 서비스 → 응답.

화면이 "맥락 수집 → 분석 → 초안 → 검사"를 차례로 보이도록 분석과 초안을 나눠 부른다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.analysis.drafter import used_quotes
from app.api.deps import Services, get_services
from app.schemas import (
    AnalysisOut,
    DraftCreateIn,
    DraftListOut,
    DraftOut,
    DraftPatchIn,
)

router = APIRouter(prefix="/api", tags=["drafts"])

ServicesDep = Annotated[Services, Depends(get_services)]


@router.post("/analysis/{video_id}", response_model=AnalysisOut)
def analyze_video(video_id: str, services: ServicesDep) -> AnalysisOut:
    """맥락이 없으면 만들고(인기 댓글 1단위) 분석한다. 자료에 없는 근거는 버린다."""
    return AnalysisOut.from_analysis(services.drafts.analyze(video_id))


@router.get("/analysis/{video_id}", response_model=AnalysisOut | None)
def stored_analysis(video_id: str, services: ServicesDep) -> AnalysisOut | None:
    """저장된 마지막 분석(없으면 null). 모델을 부르지 않는다 — 영상을 다시 고를 때 화면이 쓴다."""
    analysis = services.drafts.stored_analysis(video_id)
    return AnalysisOut.from_analysis(analysis) if analysis else None


@router.post("/drafts", response_model=DraftOut)
def create_draft(body: DraftCreateIn, services: ServicesDep) -> DraftOut:
    """초안 생성(최대 3번 시도). 다 걸리면 실패가 가장 적은 것을 걸린 항목과 함께."""
    drafts = services.drafts
    avoid = list(body.avoid_quotes)
    if body.another:
        avoid += used_quotes(drafts.list(body.video_id))
    draft = drafts.generate(body.video_id, avoid_quotes=avoid, disclose=body.disclose)
    return DraftOut.from_draft(draft, services.checks.rules)


@router.get("/drafts", response_model=DraftListOut)
def list_drafts(
    services: ServicesDep, video_id: Annotated[str, Query(min_length=1, max_length=64)]
) -> DraftListOut:
    rules = services.checks.rules
    items = [DraftOut.from_draft(d, rules) for d in services.drafts.list(video_id)]
    return DraftListOut(video_id=video_id, items=items)


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: int, body: DraftPatchIn, services: ServicesDep) -> DraftOut:
    """사람이 고친 글. 같은 규칙 검사를 다시 거친다."""
    draft = services.drafts.update_text(draft_id, body.body)
    return DraftOut.from_draft(draft, services.checks.rules)


@router.post("/drafts/{draft_id}/approve", response_model=DraftOut)
def approve_draft(draft_id: int, services: ServicesDep) -> DraftOut:
    """승인. 지금 글을 다시 검사해 걸리면 409(`draft_not_passed`)와 걸린 항목(`failures`)."""
    draft = services.drafts.approve(draft_id)
    return DraftOut.from_draft(draft, services.checks.rules)
