"""LLM 라우터: `POST /api/llm/warmup`(모델 미리 불러 두기),
`GET /api/llm/models`(R2 모델 고르기), `GET /api/llm/loaded`(R4 모델이 메모리에 있는지).

R5: `GET /api/llm/providers`(고를 수 있는 AI 목록과 준비 상태),
`POST /api/llm/providers/{name}/test`([연결 확인] — 요금이 들지 않는 호출),
`GET /api/llm/models?provider=<이름>`(그 AI의 모델 목록. 인자가 없으면 전과 같이 Ollama).
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api import ai_choice
from app.api.deps import Services, get_services
from app.api.status import _problem
from app.errors import AppError, ErrorKind
from app.schemas import (
    LLMLoadedOut,
    LLMModelOut,
    LLMModelsOut,
    LLMProviderOut,
    LLMProvidersOut,
    LLMTestOut,
    WarmupOut,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

# 코드용·임베딩용 모델은 댓글 쓰기에 맞지 않아 목록 아래로 내린다(보이기는 한다)
_CODE = re.compile(r"(coder|code|starcoder|codellama|devstral|codestral)", re.I)
_EMBED = re.compile(r"(embed|bge|minilm|nomic)", re.I)


def model_kind(name: str) -> str:
    base = name.split(":", 1)[0]
    if _EMBED.search(base):
        return "embed"
    if _CODE.search(base):
        return "code"
    return "general"


def _same(a: str, b: str) -> bool:
    def norm(n: str) -> str:
        n = n.strip().lower()
        return n if ":" in n else f"{n}:latest"

    return norm(a) == norm(b)


@router.post("/warmup", response_model=WarmupOut)
def warmup(services: Annotated[Services, Depends(get_services)]) -> WarmupOut:
    llm = services.require_llm()
    seconds = llm.warmup()
    return WarmupOut(provider=llm.provider, model=llm.model, seconds=seconds)


@router.get("/loaded", response_model=LLMLoadedOut)
def loaded(services: Annotated[Services, Depends(get_services)]) -> LLMLoadedOut:
    """모델이 지금 메모리에 올라가 있는지. 모델을 부르지 않는다(②칸의 「불러오는 중」 안내)."""
    llm = services.require_llm()
    check = getattr(llm, "is_loaded", None)
    state = check() if callable(check) else None
    cold = getattr(llm, "cold_timeout_seconds", services.settings.llm.cold_timeout_seconds)
    return LLMLoadedOut(provider=llm.provider, model=llm.model, loaded=state,
                        cold_timeout_seconds=float(cold))


@router.get("/providers", response_model=LLMProvidersOut)
def providers(services: Annotated[Services, Depends(get_services)]) -> LLMProvidersOut:
    """고를 수 있는 AI와 준비 상태(키가 있는지, 설치됐는지). 바깥에 묻지 않는다."""
    return ai_choice.providers_view(services)


@router.post("/providers/{name}/test", response_model=LLMTestOut)
def test_provider(name: str, services: Annotated[Services, Depends(get_services)]) -> LLMTestOut:
    """[연결 확인]. 글을 만들지 않는다(API 키 AI는 모델 목록, 프로그램은 로그인 상태 명령)."""
    return ai_choice.check_provider(services, name)


@router.post("/providers/{name}/login", response_model=LLMProviderOut)
def open_program_login(
    name: str, services: Annotated[Services, Depends(get_services)]
) -> LLMProviderOut:
    """[로그인하기]: 그 프로그램의 자기 로그인 명령을 보이는 명령 창으로 연다(2026-11-17).

    로그인은 사람이 그 창에서 한다. 창이 닫히면 로그인 상태 명령으로 한 번 저절로 묻는다."""
    ai_choice.open_program_login(services, name)
    provider = services.settings.llm.providers[name]
    return ai_choice.provider_view(services, provider)


# 추천 목록은 문서로 확인한 이름이지만 계정에 따라 못 쓰는 것이 있다(Codex 실측, 2026-11-17)
NOTE_ACCOUNT = "계정에 따라 쓸 수 없는 모델이 있을 수 있습니다"
NOTE_FALLBACK = f"목록을 받아 오지 못해 추천 목록을 보입니다 · {NOTE_ACCOUNT}"
NOTE_NO_LIST = "목록을 받아 오지 못했습니다 · 「직접 입력…」으로 적을 수 있습니다"
NOTE_NO_KEY = f"{NOTE_ACCOUNT}. 키를 넣으면 쓸 수 있는 목록을 받아 옵니다"
NOTE_PROGRAM_FAILED = (
    "그 프로그램에서 모델 목록을 받아 오지 못했습니다 · "
    "「기본값」이나 「직접 입력…」을 고를 수 있습니다"
)


def _fallback(recommended: list[str], *, no_key: bool = False, program: bool = False) -> dict:
    """받아 오지 못했을 때: 추천 목록이 있으면 그것, 없으면 「직접 입력…」만(2026-11-17)."""
    if not recommended:
        return {"recommended": [], "source": "none",
                "note": NOTE_PROGRAM_FAILED if program else NOTE_NO_LIST}
    return {"recommended": recommended, "source": "recommended",
            "note": NOTE_NO_KEY if no_key else NOTE_FALLBACK}


def _program_models(services: Services, name: str, current: str,
                    recommended: list[str]) -> LLMModelsOut:
    """로그인된 프로그램: 목록 명령이 있으면(Codex `debug models`) 받아 오고, 없으면 추천 목록."""
    base = {"provider": name, "manual_only": True, "current": current}
    client = ai_choice.client_for(services, name)
    try:
        try:
            found = client.list_models()  # type: ignore[attr-defined]
        except AppError as exc:
            return LLMModelsOut(reachable=False, current_installed=False, items=[],
                                error=_problem(exc), **base, **_fallback(recommended, program=True))
    finally:
        if client is not services.llm:
            client.close()
    if found is None:  # 목록 명령이 없다(Claude Code) → 추천 목록 · 직접 입력
        return LLMModelsOut(
            reachable=True, current_installed=bool(current), items=[], recommended=recommended,
            source="recommended" if recommended else "none", **base,
        )
    items = [LLMModelOut(name=m["name"], kind="general", label=m.get("label"),
                         current=m["name"] == current) for m in found]  # 그 프로그램이 준 순서
    if not items:
        return LLMModelsOut(reachable=True, current_installed=False, items=[], **base,
                            **_fallback(recommended, program=True))
    return LLMModelsOut(reachable=True, current_installed=any(i.current for i in items),
                        items=items, recommended=recommended, **base)


def _provider_models(services: Services, name: str) -> LLMModelsOut:
    llm_cfg = services.settings.llm
    provider = llm_cfg.providers.get(name)
    if provider is None:
        raise AppError(ErrorKind.LLM_PROVIDER_UNKNOWN, detail=f"'{name}'은(는) 목록에 없습니다.")
    current = llm_cfg.model_for(name)
    recommended = ai_choice.recommended_models(provider)
    if provider.type == "cli":
        return _program_models(services, name, current, recommended)
    client = ai_choice.client_for(services, name)
    try:
        if provider.type == "ollama":
            out = _ollama_models(client, current).model_copy(
                update={"provider": name, "recommended": recommended})
            if not out.reachable:
                out = out.model_copy(update=_fallback(recommended))
            return out
        try:
            found = client.list_models()  # type: ignore[attr-defined]
        except AppError as exc:
            no_key = exc.kind == ErrorKind.LLM_AUTH and not llm_cfg.api_keys.get(name)
            return LLMModelsOut(
                reachable=False, current=current, current_installed=False, items=[],
                provider=name, error=_problem(exc), **_fallback(recommended, no_key=no_key),
            )
    finally:
        if client is not services.llm:
            client.close()
    items = [
        LLMModelOut(
            name=m["name"], kind="general", label=m.get("label"), current=m["name"] == current
        )
        for m in found
    ]
    items.sort(key=lambda i: i.name.lower())
    if not items:  # 닿았지만 빈 목록: 추천 목록으로
        return LLMModelsOut(
            reachable=True, current=current, current_installed=False, items=[],
            provider=name, **_fallback(recommended),
        )
    return LLMModelsOut(
        reachable=True, current=current, current_installed=any(i.current for i in items),
        items=items, provider=name, recommended=recommended,
    )


@router.get("/models", response_model=LLMModelsOut)
def models(
    services: Annotated[Services, Depends(get_services)],
    provider: Annotated[str | None, Query(max_length=40)] = None,
) -> LLMModelsOut:
    """이 PC의 Ollama에 설치된 모델. 일반 모델이 위, 코드용·임베딩용은 아래.

    모델을 부르지 않는다. R5: `?provider=<이름>`이면 그 AI의 목록(글 생성 없음).
    """
    if provider:
        return _provider_models(services, provider)
    llm_cfg = services.settings.llm
    active = llm_cfg.active_provider
    if active is not None and active.type == "ollama":
        return _ollama_models(services.llm, llm_cfg.ollama_model)
    # 다른 AI를 쓰는 중에도 인자 없는 요청은 전과 같이 이 PC의 Ollama 목록
    name = next((n for n, p in llm_cfg.providers.items() if p.type == "ollama"), None)
    if name is None:
        return LLMModelsOut(
            reachable=False, current=llm_cfg.ollama_model, current_installed=False, items=[]
        )
    return _provider_models(services, name).model_copy(update={"provider": ""})


def _ollama_models(llm, current: str) -> LLMModelsOut:
    lister = getattr(llm, "list_models", None)
    found = lister() if callable(lister) else None
    if found is None:
        return LLMModelsOut(reachable=False, current=current, current_installed=False, items=[])
    order = {"general": 0, "code": 1, "embed": 2}
    items = [
        LLMModelOut(
            name=m["name"],
            kind=model_kind(m["name"]),  # type: ignore[arg-type]
            size_gb=round(m["size"] / 1e9, 1) if m.get("size") else None,
            current=_same(m["name"], current),
        )
        for m in found
    ]
    items.sort(key=lambda i: (order[i.kind], i.name.lower()))
    return LLMModelsOut(
        reachable=True,
        current=current,
        current_installed=any(i.current for i in items),
        items=items,
    )
