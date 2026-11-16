"""아래 줄 시스템 상태. 2단계 YouTube 키 유무와 오늘 할당량, 4단계 AI(LLM) 상태, 8단계 브라우저.

R2: 브라우저 프로필마다 로그인 확인 결과(로그인됨·채널 이름·확인한 때)를 더했다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.browser.chrome import profile_dir
from app.browser.jobs import LOGIN_TRUST
from app.config import DEFAULT_OLLAMA_MODEL
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


def same_model(a: str, b: str) -> bool:
    """모델 이름이 같은지(태그가 없으면 :latest). Ollama 모듈은 registry만 부른다."""

    def norm(n: str) -> str:
        n = n.strip().lower()
        return n if ":" in n else f"{n}:latest"

    return norm(a) == norm(b)


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
    loaded, rec_installed = None, False
    llm = services.llm
    if llm is not None and health.reachable and health.installed:
        is_loaded = getattr(llm, "is_loaded", None)
        loaded = is_loaded() if callable(is_loaded) else None
    if llm is not None and health.reachable and not same_model(health.model, DEFAULT_OLLAMA_MODEL):
        lister = getattr(llm, "list_models", None)
        found = lister() if callable(lister) else None
        rec_installed = any(same_model(m["name"], DEFAULT_OLLAMA_MODEL) for m in found or [])
    return AIStatusOut(
        **health.to_dict(),
        error=_problem(error) if error else None,
        loaded=loaded,
        recommended_model=DEFAULT_OLLAMA_MODEL,
        recommended_installed=rec_installed,
    )


def browser_status(services: Services) -> BrowserStatusOut:
    """크롬이 있는지, Playwright가 있는지, 프로필 폴더가 있는지(경로는 싣지 않는다)."""
    root = services.settings.browser.profiles_root
    logins = {s.name: s for s in services.accounts.states()} if services.accounts else {}

    def login(name: str) -> dict:
        s = logins.get(name)
        if s is None:
            return {}
        return {"signed_in": s.signed_in, "channel_name": s.channel, "checked_at": s.checked_at,
                "login_window_open": s.window_open}

    return BrowserStatusOut(
        chrome_found=services.find_chrome() is not None,
        playwright_ready=services.jobs.playwright_ready(),
        profiles=[
            BrowserProfileOut(
                name=p.name, folder=p.folder, exists=profile_dir(root, p.folder).is_dir(),
                **login(p.name),
            )
            for p in services.profiles.list_profiles()
        ],
        active_job_id=services.jobs.active_id(),
        confirm_before_post=services.settings.confirm_before_post,
        disclose_default=services.settings.disclose_default,
        login_trust_seconds=int(LOGIN_TRUST.total_seconds()),
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
