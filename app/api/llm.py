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


def _provider_models(services: Services, name: str) -> LLMModelsOut:
    llm_cfg = services.settings.llm
    provider = llm_cfg.providers.get(name)
    if provider is None:
        raise AppError(ErrorKind.LLM_PROVIDER_UNKNOWN, detail=f"'{name}'은(는) 목록에 없습니다.")
    current = llm_cfg.model_for(name)
    if provider.type == "cli":  # 목록을 주는 명령이 없다 → 직접 적는다
        return LLMModelsOut(
            reachable=True, current=current, current_installed=bool(current), items=[],
            provider=name, manual_only=True,
        )
    client = ai_choice.client_for(services, name)
    try:
        if provider.type == "ollama":
            return _ollama_models(client, current).model_copy(update={"provider": name})
        try:
            found = client.list_models()  # type: ignore[attr-defined]
        except AppError as exc:
            return LLMModelsOut(
                reachable=False, current=current, current_installed=False, items=[],
                provider=name, error=_problem(exc),
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
    return LLMModelsOut(
        reachable=True, current=current, current_installed=any(i.current for i in items),
        items=items, provider=name,
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
