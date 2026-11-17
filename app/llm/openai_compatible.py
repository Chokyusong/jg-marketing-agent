"""OpenAI 호환 API 공급자(R5, PLAYBOOK 12-1): OpenAI · xAI Grok · Gemini의 OpenAI 호환 주소 ·
「직접 입력」(OpenRouter · LM Studio 등). 주소(`base_url`)와 모델만 다르다.

확인한 날짜와 출처(2026-11-17, 기억이 아니라 공식 문서로 확인):
- OpenAI
  - https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
    `POST https://api.openai.com/v1/chat/completions`, 머리말 `Authorization: Bearer <키>`,
    `messages`(role system·user…), `model`, `max_completion_tokens`(`max_tokens`는 사라질 값),
    `response_format`: `text` | `json_object` | `json_schema`. 답은 `choices[0].message.content`,
    `finish_reason`: stop · length · tool_calls · content_filter.
  - https://developers.openai.com/api/reference/resources/models/methods/list
    `GET https://api.openai.com/v1/models` → `{"object": "list", "data": [{"id", "created",
    "object": "model", "owned_by"}]}`.
- xAI Grok — https://docs.x.ai/openapi.json (공식 OpenAPI 문서, 2026-11-17 받아 확인)
  - 주소 `https://api.x.ai/v1`(https://docs.x.ai/docs/api-reference 예제), `Bearer` 키.
  - `POST /v1/chat/completions`: `max_completion_tokens`(`max_tokens`는 DEPRECATED),
    `response_format` `{ "type": "json_object" }` 또는 `json_schema`.
  - `GET /v1/models` → `ListModelsResponse {data: [Model], object: "list"}`.
- Gemini — https://aistudio.google.com/docs/openai
  (ai.google.dev/gemini-api/docs/openai에서 옮겨 감)
  - 주소 `https://generativelanguage.googleapis.com/v1beta/openai/`, `Authorization: Bearer <키>`,
    `.../chat/completions`, 모델 목록 `.../models`(예제가 `model.id`를 읽는다).
  - 이 문서에는 `max_tokens`·`max_completion_tokens`·`response_format`의 json_object 지원이 적혀
    있지 않다 → Gemini에는 둘 다 보내지 않는다
    (config.yaml의 `max_tokens_field: ""`, `json_mode` 없음).

문서로 확인하지 못해 넣지 않은 것: 회사마다 다른 오류 본문 모양(코드로는 HTTP 상태만 본다),
`temperature`(추론 모델이 기본값 밖의 값을 거절할 수 있어 보내지 않는다), 키 형식.

JSON: 문서로 지원이 확인된 곳(OpenAI·xAI)만 `response_format: {"type": "json_object"}`를 싣고,
그 값 때문에 400이 오면 한 번 빼고 다시 보낸다. 어느 쪽이든 `base.py`의 공통 확인(JSON 꺼내기 ·
스키마 확인 · 한 번 다시 시키기)을 거친다.

`health()`는 바깥에 요청하지 않는다(아래 줄이 30초마다 묻는다 — 요금·한도를 쓰지 않게).
[연결 확인]은 모델 목록 조회(`list_models`, 글 생성 없음)로 한다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

import httpx

from app.errors import AppError, ErrorKind, redact
from app.llm.base import JSONSchema, LLMHealth, TextJSONLLM, schema_text

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10.0
LIST_TIMEOUT_SECONDS = 15.0
# 추론 모델은 생각에 쓴 토큰도 이 한도에 든다(OpenAI 문서). 짧은 JSON이어도 넉넉히 둔다
MIN_COMPLETION_TOKENS = 4096
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_local_url(url: str) -> bool:
    """이 PC 안의 주소인지.

    LM Studio 같은 「직접 입력」이 127.0.0.1이면 영상 자료가 밖으로 안 나간다."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in LOCAL_HOSTS


def http_problem(status: int, *, label: str, detail: str, key_hint: str = "API 키") -> AppError:
    """HTTP 상태 → 오류 종류(API 키 방식 공통). 문구에는 그 AI 이름을 넣는다."""
    if status in (401, 403):
        return AppError(
            ErrorKind.LLM_AUTH,
            detail=detail,
            message=f"{label}이(가) 이 {key_hint}를 받아 주지 않았습니다.",
            action=(
                f"설정 화면의 「AI」에서 {label} {key_hint}를 다시 넣고 "
                "[연결 확인]을 눌러 주세요."
            ),
        )
    if status == 429:
        return AppError(
            ErrorKind.LLM_RATE_LIMITED,
            detail=detail,
            message=(
                f"{label}의 요청 한도에 걸렸습니다"
                "(너무 자주 보냈거나 쓸 수 있는 양을 다 썼습니다)."
            ),
            action=(
                f"잠시 뒤 다시 시도해 주세요. 계속되면 {label}의 요금·사용량 화면을 "
                "확인해 주세요."
            ),
        )
    if status == 404:
        return AppError(
            ErrorKind.LLM_MODEL_MISSING,
            detail=detail,
            message=f"{label}에서 이 모델(또는 주소)을 찾지 못했습니다.",
            action="설정 화면의 「AI」에서 [모델 불러오기]로 받은 목록의 모델을 골라 주세요.",
        )
    return AppError(
        ErrorKind.LLM_ERROR,
        detail=detail,
        message=f"{label}이(가) 오류를 돌려줬습니다(HTTP {status}).",
        action="잠시 뒤 다시 시도해 주세요. 계속되면 다른 모델을 골라 보세요.",
    )


def network_problem(exc: Exception, *, label: str, detail: str) -> AppError:
    if isinstance(exc, httpx.TimeoutException):
        return AppError(
            ErrorKind.LLM_TIMEOUT,
            detail=detail,
            message=f"{label}의 답이 시간 안에 오지 않았습니다.",
            action="잠시 뒤 다시 시도해 주세요.",
        )
    return AppError(
        ErrorKind.LLM_DOWN,
        detail=detail,
        message=f"{label}에 연결하지 못했습니다.",
        action=(
            "인터넷 연결(「직접 입력」이면 주소와 그 프로그램이 켜져 있는지)을 확인한 뒤 "
            "다시 시도해 주세요."
        ),
    )


def _error_text(res: httpx.Response) -> str:
    """오류 본문에서 짧은 설명만(OpenAI 꼴 `{"error": {"message"}}` 또는 `{"error": "..."}`)."""
    try:
        data = res.json()
    except ValueError:
        return res.text[:200]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or "")[:200]
    if isinstance(err, str):
        return err[:200]
    return ""


class OpenAICompatibleClient(TextJSONLLM):
    """`POST {base_url}/chat/completions` 한 번에 답 하나."""

    warmup_supported = False  # 미리 불러오기는 Ollama만

    def __init__(
        self,
        *,
        provider: str,
        label: str,
        base_url: str,
        model: str,
        api_key: str | None,
        key_optional: bool = False,
        json_mode: bool = False,
        max_tokens_field: str = "max_completion_tokens",
        timeout_seconds: float = 180.0,
        transport: httpx.BaseTransport | None = None,
        secrets: Iterable[str] = (),
    ) -> None:
        self.provider = provider
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.local = is_local_url(self.base_url)
        self._key = api_key or None
        self.key_optional = key_optional
        self.json_mode = json_mode
        self.max_tokens_field = max_tokens_field
        self.timeout_seconds = float(timeout_seconds)
        self._secrets = tuple(s for s in (*secrets, api_key or "") if s)
        self._http = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(self.timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
        )

    # ------------------------------------------------------------ 바깥 호출

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def _detail(self, what: str) -> str:
        return redact(f"{self.provider} · {self.model or '모델 없음'}: {what}", self._secrets)

    def problem(self) -> AppError | None:
        """요청 없이 알 수 있는 준비 문제(키 없음 · 주소 없음 · 모델 안 고름)."""
        if not self.base_url:
            return AppError(
                ErrorKind.LLM_SETTINGS_INVALID,
                detail=self._detail("주소 없음"),
                message=f"{self.label}의 주소가 아직 없습니다.",
                action="설정 화면의 「AI」에서 주소(예: http://127.0.0.1:1234/v1)를 넣어 주세요.",
            )
        if not self._key and not self.key_optional:
            return AppError(
                ErrorKind.LLM_AUTH,
                detail=self._detail("키 없음"),
                message=f"{self.label} API 키가 아직 없습니다.",
                action=f"설정 화면의 「AI」에서 {self.label} API 키를 넣어 주세요.",
            )
        if not self.model:
            return AppError(
                ErrorKind.LLM_MODEL_MISSING,
                detail=self._detail("모델 없음"),
                message=f"{self.label}에서 쓸 모델을 아직 고르지 않았습니다.",
                action="설정 화면의 「AI」에서 [모델 불러오기]를 누르고 모델을 골라 주세요.",
            )
        return None

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise network_problem(
                exc, label=self.label, detail=self._detail(type(exc).__name__)
            ) from exc

    def chat_body(
        self, *, system: str, user: str, schema: JSONSchema, max_tokens: int, json_mode: bool
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"{user}\n\n다음 JSON 스키마에 맞는 JSON 객체 하나만 답하세요.\n"
                    f"{schema_text(schema)}",
                },
            ],
        }
        if self.max_tokens_field:
            body[self.max_tokens_field] = max(int(max_tokens), MIN_COMPLETION_TOKENS)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _complete(
        self, *, system: str, user: str, schema: JSONSchema, temperature: float, max_tokens: int
    ) -> str:
        problem = self.problem()
        if problem is not None:
            raise problem
        json_mode = self.json_mode
        for _ in range(2):
            body = self.chat_body(
                system=system, user=user, schema=schema, max_tokens=max_tokens, json_mode=json_mode
            )
            res = self._send("POST", f"{self.base_url}/chat/completions", json=body)
            if res.status_code == 400 and json_mode:
                # 모델이 JSON 모드를 받지 않는다 → 빼고 한 번 더(공통 확인이 JSON을 본다)
                log.info("%s: JSON 모드를 받지 않아 빼고 다시 보냅니다", self.provider)
                json_mode = False
                continue
            if res.status_code >= 400:
                text = redact(_error_text(res), self._secrets)
                raise http_problem(
                    res.status_code,
                    label=self.label,
                    detail=self._detail(f"HTTP {res.status_code} {text}"),
                )
            try:
                data = res.json()
            except ValueError as exc:
                raise AppError(
                    ErrorKind.LLM_ERROR, detail=self._detail("JSON이 아닌 응답")
                ) from exc
            choices = data.get("choices") if isinstance(data, dict) else None
            first = choices[0] if isinstance(choices, list) and choices else {}
            message = first.get("message") if isinstance(first, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            return content if isinstance(content, str) else ""
        return ""

    # ------------------------------------------------------------ 규격

    def health(self) -> LLMHealth:
        """바깥에 묻지 않는다: 키·주소가 있으면 reachable, 모델을 골랐으면 installed."""
        ready = bool(self.base_url) and (self.has_key or self.key_optional)
        return LLMHealth(self.provider, self.model, ready, ready and bool(self.model), self.local)

    def list_models(self) -> list[dict[str, Any]]:
        """`GET {base_url}/models`의 `data[].id`(글 생성 없음, [연결 확인]·[모델 불러오기]).

        실패하면 그 이유의 `AppError`를 던진다(키 거부 · 한도 · 인터넷)."""
        if not self.base_url:
            raise self.problem() or AppError(ErrorKind.LLM_SETTINGS_INVALID)
        if not self._key and not self.key_optional:
            raise self.problem() or AppError(ErrorKind.LLM_AUTH)
        res = self._send("GET", f"{self.base_url}/models", timeout=LIST_TIMEOUT_SECONDS)
        if res.status_code >= 400:
            text = redact(_error_text(res), self._secrets)
            raise http_problem(
                res.status_code,
                label=self.label,
                detail=self._detail(f"HTTP {res.status_code} {text}"),
            )
        try:
            data = res.json()
        except ValueError as exc:
            raise AppError(ErrorKind.LLM_ERROR, detail=self._detail("JSON이 아닌 응답")) from exc
        items = data.get("data") if isinstance(data, dict) else None
        out = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                out.append({"name": str(item["id"]).strip(), "size": None})
        return out

    def warmup(self) -> float:
        return 0.0  # 미리 불러올 것이 없다(바깥 서비스)

    def close(self) -> None:
        self._http.close()
