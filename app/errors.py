"""공통 오류 종류와 사용자에게 보일 한국어 문구.

오류 문구에는 API 키를 넣지 않는다. 바깥에서 받은 글(예: YouTube 오류 메시지)은
`detail`에만 담고, 담기 전에 `redact()`로 키를 가린다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ErrorKind(StrEnum):
    # YouTube 6종 (DESIGN 7절)
    MISSING_KEY = "missing_key"
    KEY_REJECTED = "key_rejected"
    QUOTA_EXCEEDED = "quota_exceeded"
    COMMENTS_DISABLED = "comments_disabled"
    VIDEO_NOT_FOUND = "video_not_found"
    NETWORK = "network"
    # 그 밖
    YOUTUBE_ERROR = "youtube_error"  # 위 6종에 들지 않는 YouTube 오류
    INVALID_URL = "invalid_url"
    # 3단계: 자막
    TRANSCRIPT_EMPTY = "transcript_empty"
    TRANSCRIPT_TOO_LONG = "transcript_too_long"
    TRANSCRIPT_PROVIDER_OFF = "transcript_provider_off"
    # 4단계: LLM(Ollama 등). 공급자 이름은 문구에 넣지 않고 detail에 담는다
    LLM_DOWN = "llm_down"
    LLM_MODEL_MISSING = "llm_model_missing"
    LLM_TIMEOUT = "llm_timeout"
    LLM_BAD_OUTPUT = "llm_bad_output"
    LLM_ERROR = "llm_error"  # 위 넷에 들지 않는 LLM 서버 오류
    LLM_PROVIDER_UNKNOWN = "llm_provider_unknown"  # llm.active가 providers에 없거나 종류를 모름


@dataclass(frozen=True)
class ErrorText:
    message: str
    action: str
    http_status: int


ERROR_TEXTS: dict[ErrorKind, ErrorText] = {
    ErrorKind.MISSING_KEY: ErrorText(
        "YouTube API 키가 설정되지 않았습니다.",
        ".env 파일에 YOUTUBE_API_KEY를 넣고 서버를 다시 켜 주세요.",
        503,
    ),
    ErrorKind.KEY_REJECTED: ErrorText(
        "YouTube가 API 키를 받아 주지 않았습니다.",
        "Google Cloud 콘솔에서 키가 맞는지, YouTube Data API v3가 켜져 있는지 확인해 주세요.",
        502,
    ),
    ErrorKind.QUOTA_EXCEEDED: ErrorText(
        "오늘 쓸 수 있는 YouTube API 할당량을 다 썼습니다.",
        "한국 시각 오후 4~5시(태평양 자정)에 다시 채워집니다. 그 전에는 저장된 목록을 써 주세요.",
        429,
    ),
    ErrorKind.COMMENTS_DISABLED: ErrorText(
        "이 영상은 댓글이 막혀 있습니다.",
        "다른 영상을 골라 주세요.",
        409,
    ),
    ErrorKind.VIDEO_NOT_FOUND: ErrorText(
        "영상을 찾지 못했습니다. 삭제됐거나 비공개일 수 있습니다.",
        "주소를 다시 확인하거나 다른 영상을 골라 주세요.",
        404,
    ),
    ErrorKind.NETWORK: ErrorText(
        "YouTube에 연결하지 못했습니다.",
        "인터넷 연결을 확인하고 잠시 뒤 다시 시도해 주세요.",
        502,
    ),
    ErrorKind.YOUTUBE_ERROR: ErrorText(
        "YouTube에서 알 수 없는 오류가 왔습니다.",
        "잠시 뒤 다시 시도해 주세요. 계속되면 서버 로그의 오류 이유를 확인해 주세요.",
        502,
    ),
    ErrorKind.INVALID_URL: ErrorText(
        "유튜브 영상 주소로 읽을 수 없습니다.",
        "https://www.youtube.com/watch?v=... 또는 https://youtu.be/... 형태로 넣어 주세요.",
        422,
    ),
    ErrorKind.TRANSCRIPT_EMPTY: ErrorText(
        "붙여 넣은 자막이 비어 있습니다.",
        "유튜브 영상 아래 '스크립트 표시'에서 자막을 복사해 붙여 넣어 주세요.",
        422,
    ),
    ErrorKind.TRANSCRIPT_TOO_LONG: ErrorText(
        "붙여 넣은 자막이 너무 깁니다(최대 20,000자).",
        "앞뒤의 필요 없는 부분을 지우고 20,000자 안으로 줄여 다시 저장해 주세요.",
        422,
    ),
    ErrorKind.TRANSCRIPT_PROVIDER_OFF: ErrorText(
        "설정한 자막 출처를 쓸 수 없습니다. 비공식 자막 조회는 켜져 있지 않습니다.",
        "config.yaml의 transcript.provider를 manual로 바꾸고 서버를 다시 켜 주세요. "
        "자막은 02칸 「자막 붙여넣기」로 넣을 수 있습니다.",
        503,
    ),
    ErrorKind.LLM_DOWN: ErrorText(
        "AI 모델 서버(Ollama)에 연결하지 못했습니다.",
        "Ollama 앱을 켜거나 터미널에서 `ollama serve`를 실행한 뒤 다시 시도해 주세요. "
        "주소가 다르면 .env의 OLLAMA_BASE_URL을 확인해 주세요.",
        503,
    ),
    ErrorKind.LLM_MODEL_MISSING: ErrorText(
        "설정한 AI 모델이 이 PC에 설치돼 있지 않습니다.",
        "터미널에서 `ollama pull <모델 이름>`으로 받거나, `ollama list`에 있는 이름을 "
        ".env의 OLLAMA_MODEL에 넣고 프로그램을 다시 켜 주세요.",
        503,
    ),
    ErrorKind.LLM_TIMEOUT: ErrorText(
        "AI 모델의 답이 시간 안에 오지 않았습니다.",
        "큰 모델은 처음 불러올 때 몇 분 걸릴 수 있습니다. 잠시 뒤 다시 시도하거나, "
        "config.yaml의 llm.timeout_seconds를 늘리거나, 더 작은 모델을 써 주세요.",
        504,
    ),
    ErrorKind.LLM_BAD_OUTPUT: ErrorText(
        "AI 모델이 정해진 모양(JSON)으로 답하지 않았습니다. 한 번 다시 시켜도 같았습니다.",
        "다시 시도해 주세요. 계속되면 다른 모델을 .env의 OLLAMA_MODEL에 넣어 보세요.",
        502,
    ),
    ErrorKind.LLM_ERROR: ErrorText(
        "AI 모델 서버가 오류를 돌려줬습니다.",
        "잠시 뒤 다시 시도해 주세요. 계속되면 Ollama 로그와 그래픽 메모리 여유를 확인해 주세요.",
        502,
    ),
    ErrorKind.LLM_PROVIDER_UNKNOWN: ErrorText(
        "설정한 AI 공급자를 쓸 수 없습니다.",
        "config.yaml의 llm.active를 llm.providers에 있는 이름으로 바꿔 주세요. "
        "지금 쓸 수 있는 종류(type)는 ollama입니다.",
        503,
    ),
}


class AppError(Exception):
    """사용자에게 보일 수 있는 오류. 응답 본문은 `to_dict()`."""

    def __init__(self, kind: ErrorKind, *, detail: str = "") -> None:
        self.kind = ErrorKind(kind)
        text = ERROR_TEXTS[self.kind]
        self.message = text.message
        self.action = text.action
        self.http_status = text.http_status
        self.detail = detail
        super().__init__(f"{self.kind}: {self.message}")

    def to_dict(self) -> dict[str, str]:
        data = {"kind": str(self.kind), "message": self.message, "action": self.action}
        if self.detail:
            data["detail"] = self.detail
        return data


_KEY_PARAM = re.compile(r"(?i)(\bkey=)[^&\s'\"]+")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """주소의 `key=` 값과 주어진 비밀값을 `***`로 바꾼다."""
    text = _KEY_PARAM.sub(r"\1***", text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text
