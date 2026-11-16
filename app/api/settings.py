"""SETTINGS 패널 API(9단계): `GET /api/settings` — 지금 설정값을 읽기 전용으로 보여 준다.

- 비밀값(YouTube 키, LLM 키)은 있는지 없는지만. PC의 경로(프로필 폴더 위치, 크롬 위치, DB 위치),
  LLM 주소도 싣지 않는다(공개 저장소 규칙, AGENTS.md).
- 모델을 부르지 않는다(Ollama가 꺼져 있어도 바로 답한다). AI가 켜져 있는지는 `GET /api/status`.
- 크롬 창 위치는 설정값과, 지금 모니터 배치에서 실제로 띄울 위치를 함께 준다(화면 밖이면 바꾼 값).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import Services, get_services
from app.api.status import _problem
from app.browser.chrome import profile_dir
from app.browser.screens import check_window_position
from app.schemas import (
    TARGET_LABELS,
    QuotaOut,
    SettingsBrowserOut,
    SettingsCommentOut,
    SettingsDiscoverOut,
    SettingsLLMOut,
    SettingsOut,
    SettingsProfileOut,
    SettingsYouTubeOut,
)

router = APIRouter(prefix="/api", tags=["settings"])


def _xy(point: tuple[int, int] | None) -> str | None:
    return f"{point[0]},{point[1]}" if point else None


def llm_settings(services: Services) -> SettingsLLMOut:
    cfg = services.settings.llm
    provider = cfg.active_provider
    llm = services.llm
    return SettingsLLMOut(
        active=cfg.active,
        type=provider.type if provider else "",
        model=llm.model if llm is not None else "",
        local=bool(llm.local) if llm is not None else True,
        timeout_seconds=cfg.timeout_seconds,
        keep_alive=cfg.keep_alive,
        context_chars=services.settings.context_chars,
        error=_problem(services.llm_error) if services.llm_error else None,
    )


def browser_settings(services: Services) -> SettingsBrowserOut:
    b = services.settings.browser
    check = check_window_position(b.window_position, services.monitors())
    target = services.settings.default_target
    return SettingsBrowserOut(
        default_target=target,  # type: ignore[arg-type]
        default_target_label=TARGET_LABELS.get(target, target),
        headless=b.headless,
        window_position=_xy(b.window_position) or "",
        window_position_used=_xy(check.position),
        window_position_adjusted=check.adjusted,
        window_position_checked=check.checked,
        window_position_note=check.note,
        typing_delay_ms=list(b.typing_delay_ms),
        chrome_found=services.find_chrome() is not None,
        playwright_ready=services.jobs.playwright_ready(),
    )


@router.get("/settings", response_model=SettingsOut)
def settings(request: Request, services: Annotated[Services, Depends(get_services)]) -> SettingsOut:
    s = services.settings
    comment = s.rules.get("comment") or {}
    root = s.browser.profiles_root
    return SettingsOut(
        version=str(request.app.version),
        stage=int(getattr(request.app.state, "stage", 0)),
        comment=SettingsCommentOut(
            min_chars=int(comment.get("min_chars", 40)),
            max_chars=int(comment.get("max_chars", 120)),
            disclosure=str(comment.get("disclosure", "[광고]")),
            brand=str(comment.get("brand", "운명원")),
        ),
        brand_facts=list(s.brand_facts),
        daily_max_comments=s.daily_max_comments,
        profiles=[
            SettingsProfileOut(
                name=p.name, folder=p.folder, ready=profile_dir(root, p.folder).is_dir()
            )
            for p in services.profiles.list_profiles()
        ],
        llm=llm_settings(services),
        browser=browser_settings(services),
        youtube=SettingsYouTubeOut(
            key_configured=s.youtube_key_configured,
            quota=QuotaOut(**services.quota.summary()),
        ),
        discover=SettingsDiscoverOut(
            query=s.discover.query,
            max_results=s.discover.max_results,
            exclude_shorts=s.discover.exclude_shorts,
        ),
        transcript_provider=s.transcript_provider,
    )
