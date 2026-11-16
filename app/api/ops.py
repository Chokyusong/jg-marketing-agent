"""운영 규칙과 기록 API(7단계): 프로필, 작업 기록, 오늘 통계. 얇게: 입력 검증 → 서비스 → 응답.

게시를 예약·완료하는 API는 여기 없다. 8단계 작업 서비스(`POST /api/jobs`)가 `rules`를 부른다.

R2: 프로필 로그인. `POST /api/profiles/{이름}/login`(일반 크롬을 로그인 주소로 열기),
`POST /api/profiles/{이름}/check`(창 없이 로그인 여부와 채널 이름을 읽기만),
`POST /api/profiles/{이름}/open`(일반 크롬으로 유튜브 첫 화면 — 로그아웃은 거기서 사람이).
`GET /api/profiles` 항목에 로그인 확인 결과를 더했다. 아이디·비밀번호는 받지도 저장하지도 않는다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.browser.login import HOME_URL, LOGIN_URL, LoginState
from app.schemas import (
    ProfileLoginOut,
    ProfileOut,
    ProfilesOut,
    RecordsOut,
    RunOut,
    TodayStatsOut,
)

router = APIRouter(prefix="/api", tags=["ops"])

ServicesDep = Annotated[Services, Depends(get_services)]
Target = Literal["sandbox", "youtube"]


def _login_fields(state: LoginState | None) -> dict:
    if state is None:
        return {}
    return {
        "exists": state.exists,
        "signed_in": state.signed_in,
        "channel_name": state.channel,
        "checked_at": state.checked_at,
        "login_state": state.state,
        "login_note": state.note,
        "login_window_open": state.window_open,
    }


@router.get("/profiles", response_model=ProfilesOut)
def list_profiles(services: ServicesDep, target: Target = "sandbox") -> ProfilesOut:
    """설정의 프로필(이름 ↔ 폴더 이름)과 자동 배정이 지금 고를 프로필, 로그인 확인 결과."""
    profiles = services.profiles
    used = profiles.last_used(target)
    states = {s.name: s for s in services.accounts.states()}
    return ProfilesOut(
        target=target,
        items=[
            ProfileOut.from_profile(p, used).model_copy(update=_login_fields(states.get(p.name)))
            for p in profiles.list_profiles()
        ],
        auto=profiles.pick_auto(target).name,
    )


def _login_out(state: LoginState, message: str) -> ProfileLoginOut:
    return ProfileLoginOut(
        name=state.name,
        exists=state.exists,
        signed_in=state.signed_in,
        login_state=state.state,  # type: ignore[arg-type]
        channel_name=state.channel,
        checked_at=state.checked_at,
        note=state.note,
        login_window_open=state.window_open,
        message=message,
    )


def _check_message(state: LoginState) -> str:
    if state.signed_in is True:
        who = f" · {state.channel}" if state.channel else ""
        return f"로그인돼 있습니다{who}"
    if state.signed_in is False:
        return "로그인돼 있지 않습니다. [로그인하기]를 눌러 구글 계정으로 로그인하세요."
    return state.note or "로그인 여부를 알 수 없습니다. 잠시 뒤 다시 확인해 주세요."


@router.post("/profiles/{name}/login", response_model=ProfileLoginOut)
def open_login(name: str, services: ServicesDep) -> ProfileLoginOut:
    """그 프로필 전용 크롬을 유튜브 로그인 화면으로 연다. 로그인은 사람이 직접 한다."""
    state = services.accounts.open_window(name, url=LOGIN_URL)
    return _login_out(
        state, "로그인을 마치고 크롬 창을 닫은 다음 [로그인 확인]을 누르세요"
    )


@router.post("/profiles/{name}/open", response_model=ProfileLoginOut)
def open_youtube(name: str, services: ServicesDep) -> ProfileLoginOut:
    """그 프로필 전용 크롬으로 유튜브 첫 화면을 연다(로그아웃은 유튜브에서 사람이)."""
    state = services.accounts.open_window(name, url=HOME_URL)
    return _login_out(state, "크롬 창을 닫으면 로그인 여부를 다시 확인합니다")


@router.post("/profiles/{name}/check", response_model=ProfileLoginOut)
def check_login(name: str, services: ServicesDep) -> ProfileLoginOut:
    """창 없이 유튜브를 열어 로그인 여부와 채널 이름을 읽는다(아무것도 입력하거나 누르지 않는다)."""
    state = services.accounts.check(name)
    return _login_out(state, _check_message(state))


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
