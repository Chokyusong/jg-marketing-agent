"""공통 오류 종류와 사용자에게 보일 한국어 문구.

오류 문구에는 API 키를 넣지 않는다. 바깥에서 받은 글(예: YouTube 오류 메시지)은
`detail`에만 담고, 담기 전에 `redact()`로 키를 가린다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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
    # R5: 다른 AI(API 키·로그인된 프로그램). 키 거부·로그인 안 됨 / 요청 한도
    LLM_AUTH = "llm_auth"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_SETTINGS_INVALID = "llm_settings_invalid"  # 고를 수 없는 AI(설치 안 됨·키 없음 등)
    # 5단계: 초안
    DRAFT_NOT_FOUND = "draft_not_found"
    DRAFT_NOT_PASSED = "draft_not_passed"  # 규칙 검사에 걸린 초안은 승인하지 않는다(409)
    DRAFT_SUPERSEDED = "draft_superseded"  # 새 초안이나 다른 승인으로 밀려난 초안
    # 실제 데이터 보정(2026-11-16): 영상 자료에 연애 고민이 없으면 초안을 만들지 않는다
    NO_LOVE_CONCERN = "no_love_concern"
    # 7단계: 운영 규칙(영상당 1개 · 하루 상한 · 승인한 초안만)
    ALREADY_COMMENTED = "already_commented"
    DAILY_LIMIT_REACHED = "daily_limit_reached"
    DRAFT_NOT_APPROVED = "draft_not_approved"
    PROFILE_UNKNOWN = "profile_unknown"  # config.yaml의 profiles에 없는 이름
    # 8단계: 브라우저 연결(게시 작업)
    JOB_BUSY = "job_busy"  # 한 번에 작업 하나
    JOB_NOT_FOUND = "job_not_found"
    JOB_WRONG_STATE = "job_wrong_state"  # 지금 단계에서 할 수 없는 일(예: 입력 중에 게시 승인)
    CHROME_NOT_FOUND = "chrome_not_found"
    PLAYWRIGHT_MISSING = "playwright_missing"
    PROFILE_IN_USE = "profile_in_use"  # 같은 프로필 폴더를 다른 크롬이 쓰고 있다
    SCREENSHOT_NOT_FOUND = "screenshot_not_found"
    # R2: 프로그램 안의 설정과 프로필 로그인
    SETTINGS_INVALID = "settings_invalid"  # 칸별 이유는 응답의 fields
    SETTINGS_BUSY = "settings_busy"  # 게시 중에는 저장(서비스 다시 만들기)을 하지 않는다
    SETTINGS_WRITE_FAILED = "settings_write_failed"
    SETTINGS_NO_STORE = "settings_no_store"  # 저장할 폴더가 정해지지 않음(테스트에서만)
    SECRET_STORE_UNAVAILABLE = "secret_store_unavailable"  # Windows가 아니라 키를 암호화할 수 없음
    KEY_BAD_SHAPE = "key_bad_shape"
    PROFILE_CHECK_BUSY = "profile_check_busy"  # 게시 중(다른 확인 중·닫는 중)에는 확인 안 함
    PROFILE_CHECK_FAILED = "profile_check_failed"
    # R3: 실제 게시 시작 전 확인 — 최근 로그인 확인에서 로그인 안 됨으로 나온 프로필
    PROFILE_NOT_SIGNED_IN = "profile_not_signed_in"
    # R4: 뜨기 직전 영상은 초안까지만(과제 가점: "초안까지만")
    RISING_DRAFT_ONLY = "rising_draft_only"


@dataclass(frozen=True)
class ErrorText:
    message: str
    action: str
    http_status: int


ERROR_TEXTS: dict[ErrorKind, ErrorText] = {
    ErrorKind.MISSING_KEY: ErrorText(
        "유튜브 API 키가 아직 없습니다.",
        "설정 화면의 「유튜브 연결」에 API 키를 넣고 저장해 주세요. 저장하면 바로 쓸 수 있습니다.",
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
        "config.yaml의 transcript.provider를 auto(자동으로 읽기) 또는 manual(직접 넣기)로 바꾸고 "
        "프로그램을 다시 켜 주세요. 자막은 ②칸 「자막 직접 넣기」로도 넣을 수 있습니다.",
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
        "설정 화면의 「AI」에서 쓸 AI를 다시 골라 주세요. "
        "(개발용: config.yaml의 llm.active를 llm.providers에 있는 이름으로)",
        503,
    ),
    ErrorKind.LLM_AUTH: ErrorText(
        "AI 서비스가 이 키(또는 로그인)를 받아 주지 않았습니다.",
        "설정 화면의 「AI」에서 API 키를 다시 넣거나, 그 프로그램에서 다시 로그인한 뒤 "
        "[연결 확인]을 눌러 주세요.",
        502,
    ),
    ErrorKind.LLM_RATE_LIMITED: ErrorText(
        "AI 서비스의 요청 한도에 걸렸습니다(너무 자주 보냈거나 쓸 수 있는 양을 다 썼습니다).",
        "잠시 뒤 다시 시도해 주세요. 계속되면 그 서비스의 요금·사용량 화면을 확인해 주세요.",
        429,
    ),
    ErrorKind.LLM_SETTINGS_INVALID: ErrorText(
        "이 AI는 아직 쓸 수 없습니다.",
        "설정 화면의 「AI」에서 준비 상태를 확인해 주세요.",
        422,
    ),
    ErrorKind.DRAFT_NOT_FOUND: ErrorText(
        "초안을 찾지 못했습니다.",
        "영상을 다시 고르고 [분석하고 초안 만들기]를 눌러 주세요.",
        404,
    ),
    ErrorKind.DRAFT_NOT_PASSED: ErrorText(
        "규칙 검사를 통과하지 못한 초안은 승인할 수 없습니다.",
        "빨갛게 표시된 항목을 고친 뒤 다시 승인해 주세요.",
        409,
    ),
    ErrorKind.DRAFT_SUPERSEDED: ErrorText(
        "더 새 초안이 있어 이 초안은 고치거나 승인할 수 없습니다.",
        "화면을 새로 고치고 지금 보이는 초안으로 진행해 주세요.",
        409,
    ),
    ErrorKind.NO_LOVE_CONCERN: ErrorText(
        "이 영상 자료에서 연애 고민을 찾지 못했습니다.",
        "자막을 붙여 넣고 다시 분석하거나 다른 영상을 골라 주세요. "
        "설명란이 광고·협찬 위주인 영상일 수 있습니다.",
        422,
    ),
    ErrorKind.ALREADY_COMMENTED: ErrorText(
        "이미 댓글을 단 영상입니다. 영상 하나에는 댓글을 하나만 답니다.",
        "①에서 다른 영상을 골라 주세요. 게시가 실패한 영상만 다시 시도할 수 있습니다.",
        409,
    ),
    ErrorKind.DAILY_LIMIT_REACHED: ErrorText(
        "오늘 달 수 있는 댓글 수(하루 상한)를 다 썼습니다.",
        "한국 시각 자정이 지나면 다시 달 수 있습니다. 실패한 게시는 상한에 세지 않습니다. "
        "상한은 설정 화면의 「게시」에서 바꿀 수 있습니다.",
        429,
    ),
    ErrorKind.DRAFT_NOT_APPROVED: ErrorText(
        "승인하지 않은 초안으로는 게시할 수 없습니다.",
        "②의 초안이 규칙 검사를 통과한 뒤 ③의 [댓글 달기]를 다시 눌러 주세요.",
        409,
    ),
    ErrorKind.PROFILE_UNKNOWN: ErrorText(
        "설정에 없는 프로필입니다.",
        "03의 사용 프로필에서 고르거나 「자동 배정」을 써 주세요. 프로필 이름은 config.yaml의 "
        "profiles에 있습니다.",
        422,
    ),
    ErrorKind.JOB_BUSY: ErrorText(
        "다른 게시 작업이 진행 중입니다. 작업은 한 번에 하나만 합니다.",
        "③의 진행 중인 게시가 끝나거나 [그만두기]를 누른 뒤 다시 시도해 주세요.",
        409,
    ),
    ErrorKind.JOB_NOT_FOUND: ErrorText(
        "게시 작업을 찾지 못했습니다. 프로그램을 다시 켰다면 이전 작업은 남지 않습니다.",
        "기록 화면에서 결과를 확인하고, 필요하면 ③에서 다시 시작해 주세요.",
        404,
    ),
    ErrorKind.JOB_WRONG_STATE: ErrorText(
        "지금 단계에서는 그 일을 할 수 없습니다.",
        "③의 진행 상태를 보고, 그 단계의 단추를 눌러 주세요.",
        409,
    ),
    ErrorKind.CHROME_NOT_FOUND: ErrorText(
        "이 PC에서 크롬(Google Chrome)을 찾지 못했습니다.",
        "크롬을 설치하거나, config.yaml의 browser.chrome_path에 chrome.exe 위치를 적고 "
        "프로그램을 다시 켜 주세요.",
        503,
    ),
    ErrorKind.PLAYWRIGHT_MISSING: ErrorText(
        "자동 입력에 필요한 도구(Playwright)가 설치돼 있지 않습니다.",
        "저장소 폴더에서 .venv\\Scripts\\python.exe -m pip install -r requirements.txt를 "
        "실행한 뒤 프로그램을 다시 켜 주세요.",
        503,
    ),
    ErrorKind.PROFILE_IN_USE: ErrorText(
        "그 프로필의 크롬 창이 이미 열려 있어 새로 열 수 없습니다.",
        "그 프로필의 크롬 창을 닫아 주세요. 닫은 뒤 다시 시도하면 됩니다.",
        409,
    ),
    ErrorKind.SCREENSHOT_NOT_FOUND: ErrorText(
        "이 작업의 화면 캡처가 없습니다.",
        "화면 캡처는 크롬 화면이 열린 뒤 실패한 작업에만 남습니다.",
        404,
    ),
    ErrorKind.SETTINGS_INVALID: ErrorText(
        "잘못된 값이 있어 저장하지 않았습니다.",
        "이유가 적힌 칸을 고친 뒤 다시 [저장]을 눌러 주세요.",
        422,
    ),
    ErrorKind.SETTINGS_BUSY: ErrorText(
        "지금 게시 중입니다. 끝난 뒤 다시 저장해 주세요.",
        "③의 게시가 끝나거나 [그만두기]를 누른 뒤 다시 [저장]을 눌러 주세요.",
        409,
    ),
    ErrorKind.SETTINGS_WRITE_FAILED: ErrorText(
        "설정을 저장하지 못했습니다.",
        "디스크 공간과 폴더 권한을 확인한 뒤 다시 [저장]을 눌러 주세요.",
        500,
    ),
    ErrorKind.SETTINGS_NO_STORE: ErrorText(
        "설정을 저장할 곳이 정해지지 않았습니다.",
        "프로그램을 껐다가 다시 켠 뒤 저장해 주세요.",
        503,
    ),
    ErrorKind.SECRET_STORE_UNAVAILABLE: ErrorText(
        "이 PC에서는 API 키를 프로그램에 저장할 수 없습니다"
        "(키를 암호화하는 기능은 Windows에만 있습니다).",
        "개발용 .env 파일의 YOUTUBE_API_KEY에 키를 넣고 프로그램을 다시 켜 주세요.",
        503,
    ),
    ErrorKind.KEY_BAD_SHAPE: ErrorText(
        "API 키 모양이 아닙니다.",
        "Google Cloud 콘솔에서 복사한 키를 앞뒤 빈칸 없이 그대로 붙여 넣어 주세요.",
        422,
    ),
    ErrorKind.PROFILE_CHECK_BUSY: ErrorText(
        "게시 중이라 지금은 로그인을 확인할 수 없습니다.",
        "게시가 끝난 뒤 [로그인 확인]을 다시 눌러 주세요.",
        409,
    ),
    ErrorKind.PROFILE_CHECK_FAILED: ErrorText(
        "로그인 여부를 확인하지 못했습니다.",
        "인터넷 연결을 확인하고 잠시 뒤 [로그인 확인]을 다시 눌러 주세요.",
        502,
    ),
    ErrorKind.PROFILE_NOT_SIGNED_IN: ErrorText(
        "이 프로필은 유튜브에 로그인돼 있지 않아 댓글을 달 수 없습니다.",
        "프로필 화면에서 그 프로필의 [로그인하기]를 눌러 로그인해 주세요. 이미 로그인했다면 "
        "[로그인 확인]을 눌러 주세요.",
        409,
    ),
    ErrorKind.RISING_DRAFT_ONLY: ErrorText(
        "뜨기 직전 영상은 초안까지만 만듭니다.",
        "댓글을 달려면 같은 영상을 [영상 불러오기]나 「영상 링크로 불러오기」로 "
        "다시 불러와 주세요.",
        409,
    ),
}


class AppError(Exception):
    """사용자에게 보일 수 있는 오류. 응답 본문은 `to_dict()`."""

    def __init__(
        self,
        kind: ErrorKind,
        *,
        detail: str = "",
        extra: dict[str, Any] | None = None,
        message: str | None = None,
        action: str | None = None,
    ) -> None:
        """R5: `message`·`action`을 주면 그 AI에 맞는 문구로 바꾼다(종류와 HTTP 상태는 그대로).

        예: Ollama 문구("Ollama를 켜세요") 대신 "OpenAI에 연결하지 못했습니다"."""
        self.kind = ErrorKind(kind)
        text = ERROR_TEXTS[self.kind]
        self.message = message or text.message
        self.action = action or text.action
        self.http_status = text.http_status
        self.detail = detail
        self.extra = dict(extra or {})  # 응답에 함께 싣는 구조화된 값(예: 걸린 검사 항목)
        super().__init__(f"{self.kind}: {self.message}")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": str(self.kind), "message": self.message, "action": self.action
        }
        if self.detail:
            data["detail"] = self.detail
        for key, value in self.extra.items():
            data.setdefault(key, value)
        return data


_KEY_PARAM = re.compile(r"(?i)(\bkey=)[^&\s'\"]+")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """주소의 `key=` 값과 주어진 비밀값을 `***`로 바꾼다."""
    text = _KEY_PARAM.sub(r"\1***", text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


# R5: 프로그램에 저장한 API 키(와 .env의 키)는 어느 로그 줄에 섞여도 가린다(`remember_log_secrets`)
_LOG_SECRETS: set[str] = set()
_BASE_FACTORY = logging.getLogRecordFactory()


def _redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _BASE_FACTORY(*args, **kwargs)
    if _LOG_SECRETS:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - 모양이 틀린 로그는 그대로 둔다
            return record
        cleaned = redact(message, _LOG_SECRETS)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
    return record


def remember_log_secrets(values: Iterable[str]) -> None:
    """이 값들이 로그에 찍히면 `***`로 바꾼다(설정을 다시 읽을 때마다 더한다)."""
    for value in values:
        if value and len(value) >= 8:
            _LOG_SECRETS.add(value)
    if logging.getLogRecordFactory() is not _redacting_factory:
        logging.setLogRecordFactory(_redacting_factory)
