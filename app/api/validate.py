"""규칙 검사 API(6단계). 얇게: 입력 검증 → 서비스 → 응답."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Services, get_services
from app.schemas import ValidateIn, ValidationOut

router = APIRouter(prefix="/api", tags=["validate"])

ServicesDep = Annotated[Services, Depends(get_services)]


@router.post("/validate", response_model=ValidationOut)
def validate_text(body: ValidateIn, services: ServicesDep) -> ValidationOut:
    """글 하나를 V1~V11로 검사한다. 대조 자료는 그 영상의 맥락(제목·설명·자막·댓글)이다.

    이전 글 비교(V11)는 초안 표가 생기는 5단계부터 채운다. 지금은 빈 목록으로 검사한다.
    """
    result = services.checks.check(body.video_id, body.text, previous_texts=[])
    return ValidationOut.from_validation(result, services.checks.rules)
