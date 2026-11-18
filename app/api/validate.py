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
    """글 하나를 V1~V14로 검사한다. 대조 자료는 그 영상의 맥락(제목·설명·자막·댓글)이다.

    이전 글 비교(V11)는 다른 영상에서 승인한 초안들과 한다(5단계부터 DB에서 꺼낸다).
    C1: 그 영상의 지금 초안의 근거 구절(V6), 분석의 핵심 말(V7)·고민 한 줄(V13)로 검사한다 —
    사람이 고친 글을 저장할 때(`PATCH /api/drafts/{id}`)와 같은 기준이다.
    """
    quote, key_phrases, concern = services.drafts.check_basis(body.video_id)
    result = services.checks.check(
        body.video_id,
        body.text,
        previous_texts=services.drafts.previous_texts(body.video_id),
        disclose=body.disclose,
        evidence_quote=quote,
        key_phrases=key_phrases or None,
        concern=concern,
        story=services.drafts.is_story,
    )
    return ValidationOut.from_validation(result, services.checks.rules)
