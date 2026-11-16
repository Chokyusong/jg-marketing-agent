"""LLM 라우터: `POST /api/llm/warmup` — 시연 전에 모델을 미리 불러 둔다(버튼은 9단계)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.schemas import WarmupOut

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/warmup", response_model=WarmupOut)
def warmup(services: Annotated[Services, Depends(get_services)]) -> WarmupOut:
    llm = services.require_llm()
    seconds = llm.warmup()
    return WarmupOut(provider=llm.provider, model=llm.model, seconds=seconds)
