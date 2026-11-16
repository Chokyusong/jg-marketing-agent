"""영상 맥락 분석(PLAYBOOK 5단계): 주제·고민 한 줄·톤·시청자 니즈·근거 구절.

- 모델에게는 3단계 `prompt_text`(한도 안으로 맞춘 글)를 준다.
- 모델이 고른 근거 구절은 **V6과 같은 기준**(`quote_in_context`)으로 영상 자료 전체(`search_text`)와
  대조해, 자료에 없는 것은 버린다. 남은 구절은 가능하면 자료의 원문 그대로로 바꾸고, 출처는
  코드가 자료에서 찾아 정한다(모델이 적은 출처보다 먼저).
- 근거가 하나도 남지 않으면 버린 사유를 넣어 한 번 더 시킨다.
- 실제 데이터 보정(2026-11-16): 연애 고민을 찾지 못하면(모델이 `has_love_concern: false`로 답하거나,
  다시 시켜도 대조 뒤 남은 근거가 0개) 제목으로 때우지 않고 `no_love_concern` 오류로 멈춘다.
  설명란·댓글의 광고·협찬·이벤트 응모 글은 근거로 받지 않는다(`is_promo`).

LLM은 `LLMClient` 규격(`generate_json`)만 쓴다. 어느 공급자인지 모른다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.analysis.context import VideoContext
from app.analysis.validator import find_evidence, normalize, quote_in_context
from app.errors import AppError, ErrorKind
from app.llm import prompts
from app.llm.base import LLMClient

MAX_EVIDENCE = 4
MAX_QUOTE_CHARS = 40  # 이보다 긴 구절은 댓글(120자)에 담기 어렵다 → 원문 안의 한 마디로 줄인다
_CLAUSE = re.compile(
    r"[,.!?…·;]\s*|\s(?:그런데|근데|하지만|그러다\s?보니)\s|(?<=는데)\s|(?<=은데)\s|(?<=니까)\s"
)
# 초안 근거 고르는 순서: 자막 > 제목 > (연애 고민을 말하는) 댓글 > 설명. 설명란은 광고·협찬 글이
# 섞여 있기 쉬워 맨 뒤다(실제 데이터 보정).
SOURCE_ORDER = ("transcript", "title", "comment", "description")
# 광고·협찬·이벤트 응모 글의 표시. 이런 말이 든 구절은 영상의 연애 고민 근거가 될 수 없다.
# ('이벤트'는 '생일 이벤트', '구독'은 '구독자 사연'처럼 연애 이야기에도 나와서 그대로 넣지 않았다)
PROMO_MARKERS = (
    "협찬", "광고", "유료 광고", "응모", "할인", "쿠폰", "구매", "주문", "최저가", "증정", "당첨",
    "구독 부탁", "구독과", "구독하고", "구독 눌러", "좋아요와", "http", "www.", "링크",
)


def is_promo(quote: str) -> bool:
    """광고·협찬·이벤트 응모·구독 유도로 보이는 구절인지(근거에서 뺀다)."""
    text = quote.lower()
    return any(marker in text for marker in PROMO_MARKERS)


@dataclass(frozen=True)
class Evidence:
    quote: str
    source: str  # transcript | title | description | comment

    @property
    def source_label(self) -> str:
        return prompts.SOURCE_LABELS.get(self.source, self.source)

    def to_dict(self) -> dict[str, str]:
        return {"quote": self.quote, "source": self.source}


@dataclass(frozen=True)
class Analysis:
    video_id: str
    topic: str
    concern: str
    tone: str
    viewer_needs: str
    evidence: tuple[Evidence, ...]
    dropped: tuple[str, ...] = ()  # 자료에 없어서 버린 근거 구절(모델이 지어낸 것)
    model: str = ""
    created_at: str = ""
    fallback: bool = False  # (예전) 근거가 모두 버려져 제목을 근거로 썼는지. 이제는 늘 거짓
    has_love_concern: bool = True
    love_reason: str = ""  # 모델이 적은 판단 까닭 한 줄

    def to_prompt(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "concern": self.concern,
            "tone": self.tone,
            "viewer_needs": self.viewer_needs,
        }


@dataclass
class _Parts:
    """출처별 영상 자료(정리한 글)."""

    by_source: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def of(cls, context: VideoContext) -> _Parts:
        video = context.video.video
        parts = cls()
        parts.by_source = {
            "transcript": [context.transcript_text] if context.transcript_text else [],
            "title": [video.title],
            "description": [video.description] if video.description else [],
            "comment": [c.text for c in context.comments],
        }
        return parts

    def locate(self, quote: str, hint: str = "") -> str | None:
        """구절이 그대로(정리 후) 들어 있는 출처. 모델이 적은 출처(`hint`)를 먼저 본다."""
        quote_n = normalize(quote)
        if not quote_n:
            return None
        order = [hint] if hint in self.by_source else []
        order += [s for s in ("transcript", "comment", "description", "title") if s != hint]
        for source in order:
            if any(quote_n in normalize(text) for text in self.by_source[source]):
                return source
        return None


def _clean(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def shorten_quote(quote: str, limit: int = MAX_QUOTE_CHARS) -> str:
    """긴 구절은 원문 안에서 쉼표·마침표로 끊은 마디 중 가장 긴 것(한도 안, 6자 이상)으로 줄인다.

    줄인 것도 원문의 일부라 영상 자료에 그대로 있다. 마디가 모두 길면 한도 근처 띄어쓰기에서 자른다.
    """
    quote = quote.strip()
    if len(quote) <= limit:
        return quote
    pieces = [p.strip() for p in _CLAUSE.split(quote) if p and p.strip()]
    fits = [p for p in pieces if len(p) <= limit and len(normalize(p)) >= 6]
    if fits:
        return max(fits, key=len)
    cut = quote[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space >= limit // 2 else cut).strip()


def check_evidence(
    raw: Any, context: VideoContext, search_text: str
) -> tuple[list[Evidence], list[str]]:
    """모델이 준 근거 목록 → (자료에 있는 것, 버린 구절). 같은 구절은 하나만 남긴다."""
    parts = _Parts.of(context)
    kept: list[Evidence] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        quote = _clean(item.get("quote"), 300).strip("'\"‘’“”「」")
        hint = str(item.get("source") or "")
        if not quote:
            continue
        if not quote_in_context(quote, search_text) or is_promo(quote):
            dropped.append(quote)
            continue
        # 자료의 원문 그대로로 바꾼다(문장부호·띄어쓰기가 달라도 같은 말이면)
        found = find_evidence(quote, search_text)
        if found and len(normalize(found)) >= len(normalize(quote)):
            quote = _clean(found, 300)
            quote = shorten_quote(quote)
        key = normalize(quote)
        if key in seen:
            continue
        seen.add(key)
        source = parts.locate(quote, hint) or (hint if hint in prompts.SOURCES else "transcript")
        kept.append(Evidence(quote=quote, source=source))
    return kept[:MAX_EVIDENCE], dropped


def has_love_concern(data: dict[str, Any]) -> bool:
    """모델 답의 `has_love_concern`. 빠졌으면(예전 모양의 답) 참으로 본다(근거 대조가 받친다)."""
    value = data.get("has_love_concern", True)
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "아니오", "")
    return bool(value)


def _no_concern(reason: str) -> AppError:
    return AppError(ErrorKind.NO_LOVE_CONCERN, detail=_clean(reason, 120))


def analyze(
    context: VideoContext,
    llm: LLMClient,
    *,
    prompt_text: str,
    search_text: str,
    created_at: str = "",
) -> Analysis:
    """분석 한 번(필요하면 근거만 한 번 더). 연결 오류 등은 `AppError`로 그대로 올라간다.

    연애 고민이 없으면 `AppError(no_love_concern)`: 모델이 `has_love_concern: false`라 했거나,
    다시 시켜도 대조 뒤 남은 근거가 0개일 때. 초안을 만들지 않는다.
    """
    system, user = prompts.analysis_messages(prompt_text)
    data = _ask(llm, system, user)
    if not has_love_concern(data):
        raise _no_concern(str(data.get("reason") or "모델이 연애 고민 없음으로 답함"))
    evidence, dropped = check_evidence(data.get("evidence"), context, search_text)
    if not evidence:
        system, user = prompts.analysis_messages(
            prompt_text, retry_note=prompts.analysis_retry_note(dropped)
        )
        data2 = _ask(llm, system, user)
        if not has_love_concern(data2):
            raise _no_concern(str(data2.get("reason") or "모델이 연애 고민 없음으로 답함"))
        evidence, dropped2 = check_evidence(data2.get("evidence"), context, search_text)
        dropped += dropped2
        if not evidence:
            raise _no_concern(f"영상 자료와 맞는 연애 고민 근거가 없음(버린 근거 {len(dropped)}개)")
        data = data2
    return Analysis(
        video_id=context.video_id,
        topic=_clean(data.get("topic"), 60),
        concern=_clean(data.get("concern"), 120),
        tone=_clean(data.get("tone"), 60),
        viewer_needs=_clean(data.get("viewer_needs"), 120),
        evidence=tuple(evidence),
        dropped=tuple(dict.fromkeys(dropped)),
        model=str(getattr(llm, "model", "") or ""),
        created_at=created_at,
        fallback=False,
        has_love_concern=True,
        love_reason=_clean(data.get("reason"), 120),
    )


def _ask(llm: LLMClient, system: str, user: str) -> dict[str, Any]:
    return llm.generate_json(
        system=system,
        user=user,
        schema=prompts.ANALYSIS_SCHEMA,
        temperature=prompts.ANALYSIS_TEMPERATURE,
        max_tokens=prompts.ANALYSIS_MAX_TOKENS,
    )


def pick_evidence(evidence: Sequence[Evidence], avoid_quotes: Sequence[str] = ()) -> Evidence:
    """초안에 쓸 근거 하나: 피할 구절이 아닌 것 중 자막 > 제목 > 댓글 > 설명 순(같으면 모델 순서).

    모두 이미 썼으면 가장 앞의 것을 다시 쓴다(초안 문장은 V11·프롬프트로 달라진다).
    """
    avoid = {normalize(q) for q in avoid_quotes if q}
    rank = {s: i for i, s in enumerate(SOURCE_ORDER)}
    ordered = sorted(
        enumerate(evidence), key=lambda pair: (rank.get(pair[1].source, 9), pair[0])
    )
    for _, item in ordered:
        if normalize(item.quote) not in avoid:
            return item
    return ordered[0][1]
