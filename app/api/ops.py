"""운영 규칙과 기록 API(7단계): 프로필, 작업 기록, 오늘 통계. 얇게: 입력 검증 → 서비스 → 응답.

게시를 예약·완료하는 API는 여기 없다. 8단계 작업 서비스(`POST /api/jobs`)가 `rules`를 부른다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.schemas import ProfileOut, ProfilesOut, RecordsOut, RunOut, TodayStatsOut

router = APIRouter(prefix="/api", tags=["ops"])

ServicesDep = Annotated[Services, Depends(get_services)]
Target = Literal["sandbox", "youtube"]


@router.get("/profiles", response_model=ProfilesOut)
def list_profiles(services: ServicesDep, target: Target = "sandbox") -> ProfilesOut:
    """설정의 프로필(이름 ↔ 폴더 이름)과 자동 배정이 지금 고를 프로필."""
    profiles = services.profiles
    used = profiles.last_used(target)
    return ProfilesOut(
        target=target,
        items=[ProfileOut.from_profile(p, used) for p in profiles.list_profiles()],
        auto=profiles.pick_auto(target).name,
    )


@router.get("/records", response_model=RecordsOut)
def list_records(
    services: ServicesDep, limit: Annotated[int, Query(ge=1, le=200)] = 20
) -> RecordsOut:
    """작업 기록(최신이 위)."""
    items = [RunOut.from_run(r) for r in services.ledger.recent(limit)]
    return RecordsOut(items=items, total=services.ledger.count())


@router.get("/stats/today", response_model=TodayStatsOut)
def today_stats(
    services: ServicesDep,
    target: Target = "sandbox",
    daily_limit: Annotated[int | None, Query(ge=0, le=1000)] = None,
) -> TodayStatsOut:
    """오늘(한국 날짜) 통계. `daily_limit`은 화면에서 낮춘 상한(설정값보다 높일 수 없다)."""
    return TodayStatsOut.from_stats(
        services.ledger.today_stats(target, daily_limit=daily_limit)
    )
