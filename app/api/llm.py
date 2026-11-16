"""LLM 라우터: `POST /api/llm/warmup`(모델 미리 불러 두기),
`GET /api/llm/models`(R2 모델 고르기), `GET /api/llm/loaded`(R4 모델이 메모리에 있는지)."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.schemas import LLMLoadedOut, LLMModelOut, LLMModelsOut, WarmupOut

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


@router.get("/models", response_model=LLMModelsOut)
def models(services: Annotated[Services, Depends(get_services)]) -> LLMModelsOut:
    """이 PC의 Ollama에 설치된 모델. 일반 모델이 위, 코드용·임베딩용은 아래.

    모델을 부르지 않는다.
    """
    current = services.settings.llm.ollama_model
    llm = services.llm
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
