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
    """글 하나를 규칙 검사(V1~V6·V8~V11)로 검사한다. 대조 자료는 그 영상의 맥락(제목·설명·
    자막·댓글).

    이전 글 비교(V11)는 다른 영상에서 승인·게시한 글과 한다. 근거 구절(V6)은 그 영상의 지금
    초안이 짚은 구절 — 사람이 고친 글을 저장할 때(`PATCH /api/drafts/{id}`)와 같은 기준이다.
    """
    quote = services.drafts.check_basis(body.video_id)
    result = services.checks.check(
        body.video_id,
        body.text,
        previous_texts=services.drafts.previous_texts(body.video_id),
        disclose=body.disclose,
        evidence_quote=quote,
    )
    return ValidationOut.from_validation(result, services.checks.rules)
