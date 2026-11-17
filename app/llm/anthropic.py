"""Claude API 공급자(R5, PLAYBOOK 12-2) — `POST /v1/messages` 한 번에 답 하나.

확인한 날짜와 출처(2026-11-17, 기억이 아니라 문서로 확인):
- Claude Code에 들어 있는 `claude-api` 스킬(2.1.325)의 `curl/examples.md`·`shared/models.md`·
  `shared/error-codes.md`·`shared/api-version-migration.md`(공식 문서
  https://platform.claude.com/docs 를 옮긴 것):
  - `POST https://api.anthropic.com/v1/messages`, 머리말 `x-api-key: <키>`,
    `anthropic-version: 2026-10-21`, `content-type: application/json`.
    본문 `model`, `max_tokens`, `system`, `messages: [{"role": "user", "content": ...}]`.
    답은 `content[]` 중 `type == "text"`인 블록의 `text`, `stop_reason`(end_turn · max_tokens ·
    refusal …).
  - API 버전 2026-10-21에서는 `temperature`·`top_p`·`top_k`를 보내면 400 → 보내지 않는다.
    최근 모델은 생각(thinking)이 늘 켜져 있고 생각한 토큰도 `max_tokens`에 든다 → 넉넉히 둔다.
  - 모델 목록 `GET /v1/models` → `data[].id`·`display_name`(모델 이름을 코드에 박지 않는다).
  - 오류: 401 authentication_error, 403 permission_error, 429 rate_limit_error,
    529 overloaded_error, 402 billing_error.
- 공식 파이썬 SDK(`anthropic`) 대신 httpx로 직접 부른다: 이 앱의 다른 공급자(Ollama·OpenAI 호환)와
  같은 방식으로 `mock_http`(httpx.MockTransport) 테스트를 하고, 의존성을 늘리지 않기 위해서다
  (SDK 1.x는 httpx가 아니라 httpx2 위에 있다).

문서로 확인하지 못해 넣지 않은 것: 구조화 출력(`output_config.format`)은 스키마 조건(모든 키
필수·additionalProperties false 등)이 이 앱 스키마와 맞는지 확인하지 않아 쓰지 않는다 →
프롬프트에 스키마를 넣고 `base.py`의 공통 확인으로 본다. 모델 목록의 쪽 넘기기 인자도 쓰지 않는다
(첫 쪽만 받는다).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from app.errors import AppError, ErrorKind, redact
from app.llm.base import JSONSchema, LLMHealth, TextJSONLLM, schema_text
from app.llm.openai_compatible import (
    CONNECT_TIMEOUT_SECONDS,
    LIST_TIMEOUT_SECONDS,
    MIN_COMPLETION_TOKENS,
    _error_text,
    http_problem,
    network_problem,
)

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2026-10-21"


class AnthropicClient(TextJSONLLM):
    local = False
    warmup_supported = False
    bad_output_action = (
        "다시 시도해 주세요. 계속되면 설정 화면의 「AI」에서 다른 모델이나 다른 AI를 골라 주세요."
    )

    def __init__(
        self,
        *,
        provider: str,
        label: str,
        model: str,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 180.0,
        transport: httpx.BaseTransport | None = None,
        secrets: Iterable[str] = (),
    ) -> None:
        self.provider = provider
        self.label = label
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._key = api_key or None
        self.timeout_seconds = float(timeout_seconds)
        self._secrets = tuple(s for s in (*secrets, api_key or "") if s)
        self._http = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(self.timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS),
        )

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._key or "",
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _detail(self, what: str) -> str:
        return redact(f"{self.provider} · {self.model or '모델 없음'}: {what}", self._secrets)

    def problem(self) -> AppError | None:
        if not self._key:
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

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            res = self._http.request(
                method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
            )
        except httpx.HTTPError as exc:
            raise network_problem(
                exc, label=self.label, detail=self._detail(type(exc).__name__)
            ) from exc
        if res.status_code >= 400:
            text = redact(_error_text(res), self._secrets)
            detail = self._detail(f"HTTP {res.status_code} {text}")
            if res.status_code == 529:  # overloaded_error: 잠시 뒤 다시
                raise AppError(
                    ErrorKind.LLM_RATE_LIMITED,
                    detail=detail,
                    message=f"{self.label}이(가) 지금 붐벼 답하지 못했습니다.",
                    action="잠시 뒤 다시 시도해 주세요.",
                )
            raise http_problem(res.status_code, label=self.label, detail=detail)
        return res

    def chat_body(
        self, *, system: str, user: str, schema: JSONSchema, max_tokens: int
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": max(int(max_tokens), MIN_COMPLETION_TOKENS),
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": f"{user}\n\n다음 JSON 스키마에 맞는 JSON 객체 하나만 답하세요.\n"
                    f"{schema_text(schema)}",
                }
            ],
        }

    def _complete(
        self, *, system: str, user: str, schema: JSONSchema, temperature: float, max_tokens: int
    ) -> str:
        problem = self.problem()
        if problem is not None:
            raise problem
        body = self.chat_body(system=system, user=user, schema=schema, max_tokens=max_tokens)
        res = self._send("POST", "/v1/messages", json=body)
        try:
            data = res.json()
        except ValueError as exc:
            raise AppError(ErrorKind.LLM_ERROR, detail=self._detail("JSON이 아닌 응답")) from exc
        blocks = data.get("content") if isinstance(data, dict) else None
        texts = [
            str(b.get("text") or "")
            for b in (blocks if isinstance(blocks, list) else [])
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "".join(texts)

    def health(self) -> LLMHealth:
        """바깥에 묻지 않는다(아래 줄이 30초마다 묻는다).

        키가 있으면 reachable, 모델을 골랐으면 installed."""
        return LLMHealth(
            self.provider, self.model, self.has_key, self.has_key and bool(self.model), False
        )

    def list_models(self) -> list[dict[str, Any]]:
        """`GET /v1/models`(글 생성 없음). 실패하면 그 이유의 `AppError`."""
        if not self._key:
            raise self.problem() or AppError(ErrorKind.LLM_AUTH)
        res = self._send("GET", "/v1/models", timeout=LIST_TIMEOUT_SECONDS)
        try:
            data = res.json()
        except ValueError as exc:
            raise AppError(ErrorKind.LLM_ERROR, detail=self._detail("JSON이 아닌 응답")) from exc
        items = data.get("data") if isinstance(data, dict) else None
        out = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                out.append(
                    {
                        "name": str(item["id"]).strip(),
                        "label": str(item.get("display_name") or "").strip() or None,
                        "size": None,
                    }
                )
        return out

    def warmup(self) -> float:
        return 0.0

    def close(self) -> None:
        self._http.close()
