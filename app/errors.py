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
