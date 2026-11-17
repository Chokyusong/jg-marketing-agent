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
    """고른 AI의 상태. 바깥(요금이 드는 곳)에는 묻지 않는다(30초마다 불린다).

    R5: 모델이 메모리에 있는지·추천 모델은 Ollama일 때만 본다. API 키 AI와 로그인된 프로그램은
    그 공급자가 아는 준비 문제(`problem()` — 키 없음·주소 없음·모델 안 고름·설치 안 됨)를 알린다.
    """
    from app.api.ai_choice import is_local, kind_of, label_of, sends_to

    health = services.llm_health()
    provider = services.settings.llm.active_provider
    is_ollama = provider is not None and provider.type == "ollama"
    llm = services.llm
    error: AppError | None = None
    check = getattr(llm, "problem", None)
    problem = check() if llm is not None and callable(check) else None
    if services.llm_error is not None:
        error = services.llm_error
    elif problem is not None:
        error = problem
    elif not health.reachable:
        error = AppError(ErrorKind.LLM_DOWN)
    elif not health.installed:
        error = AppError(ErrorKind.LLM_MODEL_MISSING)
    loaded, rec_installed = None, False
    if is_ollama and llm is not None and health.reachable and health.installed:
        is_loaded = getattr(llm, "is_loaded", None)
        loaded = is_loaded() if callable(is_loaded) else None
    if (
        is_ollama
        and llm is not None
        and health.reachable
        and not same_model(health.model, DEFAULT_OLLAMA_MODEL)
    ):
        lister = getattr(llm, "list_models", None)
        found = lister() if callable(lister) else None
        rec_installed = any(same_model(m["name"], DEFAULT_OLLAMA_MODEL) for m in found or [])
    view = health.to_dict()
    if provider is not None:  # 이름 · 이 PC/외부 · (Ollama 밖의) 모델은 설정으로 정한다
        view["provider"] = provider.name
        view["local"] = is_local(services.settings, provider)
        if not is_ollama:
            view["model"] = services.settings.llm.model_for(provider.name)
    return AIStatusOut(
        **view,
        error=_problem(error) if error else None,
        loaded=loaded,
        recommended_model=DEFAULT_OLLAMA_MODEL if is_ollama or provider is None else "",
        recommended_installed=rec_installed,
        label=label_of(provider, services.settings.llm.active),
        kind=kind_of(provider),  # type: ignore[arg-type]
        sends_to=sends_to(provider),
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
                "login_window_open": s.window_open, "login_checking": s.checking,
                "login_checking_auto": s.checking_auto}

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
