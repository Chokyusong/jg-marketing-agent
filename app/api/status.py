"""위 줄 시스템 상태. 2단계 YouTube 키 유무와 오늘 할당량, 4단계 AI(LLM) 상태(8단계에 브라우저)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.errors import AppError, ErrorKind
from app.schemas import AIStatusOut, ProblemOut, QuotaOut, StatusOut, YouTubeStatusOut

router = APIRouter(prefix="/api", tags=["status"])


def _problem(error: AppError) -> ProblemOut:
    return ProblemOut(kind=str(error.kind), message=error.message, action=error.action)


def ai_status(services: Services) -> AIStatusOut:
    health = services.llm_health()
    error: AppError | None = None
    if services.llm_error is not None:
        error = services.llm_error
    elif not health.reachable:
        error = AppError(ErrorKind.LLM_DOWN)
    elif not health.installed:
        error = AppError(ErrorKind.LLM_MODEL_MISSING)
    return AIStatusOut(**health.to_dict(), error=_problem(error) if error else None)


@router.get("/status", response_model=StatusOut)
def status(services: Annotated[Services, Depends(get_services)]) -> StatusOut:
    return StatusOut(
        youtube=YouTubeStatusOut(
            key_configured=services.settings.youtube_key_configured,
            quota=QuotaOut(**services.quota.summary()),
        ),
        ai=ai_status(services),
    )
