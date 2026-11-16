"""자막 공급자 공통 규격(DESIGN 5.1).

공식 Data API로는 남의 영상 자막을 내려받을 수 없다. R4(과제: "AI가 자막(없으면 제목·설명)…")부터
기본은 **자동으로 읽기**(`auto`, `app/transcript/auto.py`)이고, 사람이 붙여 넣은 자막(`manual`)이
있으면 그것이 먼저다. 설정 `transcript.provider`: `auto`(기본, 자동으로 읽고 못 읽으면 제목·설명) |
`manual`(붙여 넣은 자막만, 「자막 자동으로 읽기」 끔). 옛 값 `unofficial`은 만들지 않은 공급자라
`transcript_provider_off` 오류를 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.errors import AppError, ErrorKind

TranscriptSource = Literal["manual", "auto", "unofficial"]
KNOWN_PROVIDERS = ("manual", "auto", "unofficial")
AVAILABLE_PROVIDERS = ("manual", "auto")  # R4: 자동으로 읽기(auto)가 기본


@dataclass(frozen=True)
class Transcript:
    text: str
    source: TranscriptSource
    language: str | None = None  # 붙여 넣은 자막은 언어를 모른다. 자동은 유튜브의 언어 코드(ko 등)
    generated: bool | None = None  # 자동: 유튜브 자동 생성 자막인지(붙여 넣은 자막은 None)


class TranscriptProvider(Protocol):
    name: TranscriptSource

    def fetch(self, video_id: str) -> Transcript | None:
        """자막이 있으면 돌려주고, 없으면 None."""
        ...


def check_provider_setting(provider: str) -> None:
    """설정의 `transcript.provider`가 지금 쓸 수 있는 값인지 확인한다."""
    if provider in AVAILABLE_PROVIDERS:
        return
    if provider in KNOWN_PROVIDERS:
        detail = f"transcript.provider={provider}: 대표 결정(D1) 전이라 만들지 않았음"
    else:
        detail = f"transcript.provider={provider}: 알 수 없는 값(auto 또는 manual)"
    raise AppError(ErrorKind.TRANSCRIPT_PROVIDER_OFF, detail=detail)
