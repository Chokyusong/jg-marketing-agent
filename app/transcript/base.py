"""자막 공급자 공통 규격(DESIGN 5.1).

공식 Data API로는 남의 영상 자막을 내려받을 수 없다. 그래서 기본 공급자는 사용자가 붙여 넣은
자막(`manual`)이다. 비공식 조회(`unofficial`)는 대표 결정 D1이 "허용"일 때만 만든다 — 지금은
없고, 설정에서 고르면 `transcript_provider_off` 오류를 낸다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.errors import AppError, ErrorKind

TranscriptSource = Literal["manual", "unofficial"]
KNOWN_PROVIDERS = ("manual", "unofficial")
AVAILABLE_PROVIDERS = ("manual",)  # D1 기본값: 수동 붙여넣기만


@dataclass(frozen=True)
class Transcript:
    text: str
    source: TranscriptSource
    language: str | None = None  # 붙여 넣은 자막은 언어를 모른다


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
        detail = f"transcript.provider={provider}: 알 수 없는 값(manual 또는 unofficial)"
    raise AppError(ErrorKind.TRANSCRIPT_PROVIDER_OFF, detail=detail)
