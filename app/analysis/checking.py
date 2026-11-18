"""규칙 검사 서비스(6단계): 영상 자료를 꺼내 `validator.validate`에 넘긴다.

판정은 전부 `validator.py`(순수 함수)에 있다. 여기서는 대조 자료(3단계 `search_text`)와
설정(표기·브랜드·글자 수·brand.facts·추가 표현)을 모아 줄 뿐이다.
AI가 쓴 초안(5단계)과 사람이 고친 글이 같은 길을 지난다.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analysis.context import ContextService
from app.analysis.validator import Validation, ValidatorRules, validate


class CheckService:
    def __init__(
        self,
        context: ContextService,
        *,
        rules: ValidatorRules,
        brand_facts: Sequence[str],
    ) -> None:
        self.context = context
        self.rules = rules
        self.brand_facts = tuple(brand_facts)

    def check(
        self,
        video_id: str,
        text: str,
        *,
        previous_texts: Sequence[str] = (),
        evidence_quote: str | None = None,
        disclose: bool = True,
    ) -> Validation:
        """영상의 맥락이 아직 없으면 만들어서(인기 댓글 1단위) 대조한다.

        `previous_texts`(V11)는 이전에 승인·게시한 글. `evidence_quote`(V6)는 초안이 짚은 구절
        (AI의 `used_quote`). `disclose`(R3)는 광고 표기를 켰는지 — 끄면 V4가 「표기 끔」으로
        통과한다(어떤 영상이든).
        """
        context = self.context.current(video_id)
        return validate(
            text,
            context_text=self.context.search_text(context),
            rules=self.rules,
            brand_facts=self.brand_facts,
            previous_texts=list(previous_texts),
            evidence_quote=evidence_quote,
            disclosure_required=disclose,
        )
