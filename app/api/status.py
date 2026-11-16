"""위 줄 시스템 상태. 2단계 YouTube 키 유무와 오늘 할당량, 4단계 AI(LLM) 상태, 8단계 브라우저."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.browser.chrome import profile_dir
from app.errors import AppError, ErrorKind
from app.schemas import (
    AIStatusOut,
    BrowserProfileOut,
    BrowserStatusOut,
    ProblemOut,
    QuotaOut,
    StatusOut,
    YouTubeStatusOut,
)

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


def browser_status(services: Services) -> BrowserStatusOut:
    """크롬이 있는지, Playwright가 있는지, 프로필 폴더가 있는지(경로는 싣지 않는다)."""
    root = services.settings.browser.profiles_root
    return BrowserStatusOut(
        chrome_found=services.find_chrome() is not None,
        playwright_ready=services.jobs.playwright_ready(),
        profiles=[
            BrowserProfileOut(
                name=p.name, folder=p.folder, exists=profile_dir(root, p.folder).is_dir()
            )
            for p in services.profiles.list_profiles()
        ],
        active_job_id=services.jobs.active_id(),
    )


@router.get("/status", response_model=StatusOut)
def status(services: Annotated[Services, Depends(get_services)]) -> StatusOut:
    return StatusOut(
        youtube=YouTubeStatusOut(
            key_configured=services.settings.youtube_key_configured,
            quota=QuotaOut(**services.quota.summary()),
        ),
        ai=ai_status(services),
        browser=browser_status(services),
    )
