"""Ollama 공급자 — `POST /api/chat` 한 번에 JSON 하나(DESIGN 5.2, 5.2.1).

요청 모양은 기억이 아니라 공식 문서와 이 PC의 실제 응답으로 확인했다(2026-11-16).

- 문서
  - https://docs.ollama.com/api/chat — `format`은 "`json` or a JSON schema", `options`에
    `temperature`·`num_ctx`·`num_predict`, `keep_alive`(예: `5m`, `0`이면 바로 내림),
    `think`는 불리언 또는 모델이 정한 이름. `false` = 생각 출력 없음. 생각은 `message.thinking`,
    답은 `message.content`.
  - https://docs.ollama.com/capabilities/thinking — 끄는 값은 `think: false`. 끌 수 없는 모델은
    가장 낮은 단계로 돈다. `/api/show`의 `thinking.values`가 있으면 그 값만 받는다.
  - https://docs.ollama.com/capabilities/structured-outputs — 스키마를 `format`에, 프롬프트에도
    스키마를 글로 넣으면 좋다.
  - https://docs.ollama.com/api-reference/show-model-details.md — `POST /api/show {model}` →
    `capabilities`(문자열 목록, 예 completion·thinking·vision),
    선택 항목 `thinking{values, default}`.
  - https://docs.ollama.com/api/errors.md — 오류 본문 `{"error": "..."}`, 404 = 모델 없음.
  - https://github.com/ollama/ollama/blob/main/docs/api.md — `messages`가 빈 목록이면 모델을
    불러 두기만 한다(`done_reason: "load"`), 거기에 `keep_alive: 0`이면 내린다.
- 이 PC(Ollama 0.34.0, 127.0.0.1:11434)에서 실제로 본 것
  - `/api/show` `capabilities`: qwen2.5:7b `[completion, tools]`,
    qwen3.8:27b·qwen3.6:latest `[completion, vision, tools, thinking]`.
    세 모델 모두 `thinking` 객체는 없다(그래서 기능 목록의 thinking으로 판단한다).
  - 없는 모델: `/api/show`·`/api/chat` 모두 HTTP 404 `{"error":"model 'nope:1b' not found"}`.
  - `/api/chat`에 `format`(스키마)·`stream: false`를 주면 `message.content`가 JSON 글 하나.
    생각 기능이 없는 qwen2.5:7b에 `think: false`를 줘도 200이지만,
    기능 목록에 thinking이 있을 때만 싣는다.

연결 오류·시간 초과·404는 `AppError`(llm_down·llm_timeout·llm_model_missing)로 바꾼다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

import httpx

from app.errors import AppError, ErrorKind, redact
from app.llm.base import JSONSchema, LLMHealth, TextJSONLLM, schema_text

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
HEALTH_TIMEOUT_SECONDS = 3.0


def same_model(a: str, b: str) -> bool:
    """`qwen3.6`과 `qwen3.6:latest`를 같은 모델로 본다."""

    def norm(name: str) -> str:
        name = name.strip().lower()
        return name if ":" in name else f"{name}:latest"

    return norm(a) == norm(b)


class OllamaClient(TextJSONLLM):
    local = True

    def __init__(
        self,
        *,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        provider: str = "ollama",
        timeout_seconds: float = 180.0,
        num_ctx: int = 8192,
        keep_alive: str | int = "30m",
        transport: httpx.BaseTransport | None = None,
        secrets: Iterable[str] = (),
    ) -> None:
        self.provider = provider
        self._secrets = tuple(secrets)  # 오류 문구·로그에 찍기 전에 가릴 값(설정의 비밀값 전부)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.num_ctx = int(num_ctx)
        self.keep_alive = keep_alive
        self._http = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=httpx.Timeout(self.timeout_seconds, connect=HEALTH_TIMEOUT_SECONDS),
        )
        self._capabilities: frozenset[str] | None = None
        self._think_values: list[Any] | None = None  # /api/show의 thinking.values(있을 때만)

    # ------------------------------------------------------------ 바깥 호출

    def _detail(self, what: str) -> str:
        return redact(f"{self.provider} · {self.model} · {self.base_url}: {what}", self._secrets)

    def _post(self, path: str, body: dict[str, Any], *, timeout: float | None = None) -> Any:
        try:
            res = self._http.post(path, json=body, timeout=timeout or httpx.USE_CLIENT_DEFAULT)
        except httpx.TimeoutException as exc:
            raise AppError(ErrorKind.LLM_TIMEOUT, detail=self._detail(type(exc).__name__)) from exc
        except httpx.TransportError as exc:
            raise AppError(ErrorKind.LLM_DOWN, detail=self._detail(type(exc).__name__)) from exc
        message = _error_text(res)
        if res.status_code == 404:
            raise AppError(ErrorKind.LLM_MODEL_MISSING, detail=self._detail(message))
        if res.status_code >= 400:
            log.warning(
                "ollama %s HTTP %s: %s", path, res.status_code, redact(message, self._secrets)
            )
            raise AppError(
                ErrorKind.LLM_ERROR, detail=self._detail(f"HTTP {res.status_code} {message}")
            )
        try:
            return res.json()
        except ValueError as exc:
            raise AppError(ErrorKind.LLM_ERROR, detail=self._detail("JSON이 아닌 응답")) from exc

    def capabilities(self) -> frozenset[str]:
        """`/api/show`의 기능 목록(한 번 읽어 둔다). 모델이 없으면 `llm_model_missing`."""
        if self._capabilities is None:
            data = self._post("/api/show", {"model": self.model}, timeout=30.0)
            caps = data.get("capabilities") if isinstance(data, dict) else None
            self._capabilities = frozenset(str(c) for c in caps or [])
            thinking = data.get("thinking") if isinstance(data, dict) else None
            self._think_values = thinking.get("values") if isinstance(thinking, dict) else None
        return self._capabilities

    def think_option(self) -> bool | None:
        """생각 출력 기능이 있으면 `False`(끄기), 없으면 `None`(싣지 않음)."""
        caps = self.capabilities()
        values = self._think_values
        if values is not None:
            # [false]만 있으면 생각 기능이 없는 모델. 그 밖에는 false를 준다(끌 수 없는 모델은
            # 문서대로 가장 낮은 단계로 돈다)
            return None if not values or values == [False] else False
        return False if "thinking" in caps else None

    def chat_body(
        self, *, system: str, user: str, schema: JSONSchema, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    # 문서 권장: 스키마를 format에 주고, 프롬프트에도 글로 넣는다
                    "content": f"{user}\n\n다음 JSON 스키마에 맞는 JSON 객체 하나만 답하세요.\n"
                    f"{schema_text(schema)}",
                },
            ],
            "stream": False,
            "format": schema,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens,
            },
            "keep_alive": self.keep_alive,
        }
        think = self.think_option()
        if think is not None:
            body["think"] = think
        return body

    # ------------------------------------------------------------ 규격

    def _complete(
        self, *, system: str, user: str, schema: JSONSchema, temperature: float, max_tokens: int
    ) -> str:
        body = self.chat_body(
            system=system, user=user, schema=schema, temperature=temperature, max_tokens=max_tokens
        )
        data = self._post("/api/chat", body)
        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else ""

    def health(self) -> LLMHealth:
        """서버에 닿는지(`/api/tags`), 설정한 모델이 설치돼 있는지. 짧게 기다린다."""
        try:
            res = self._http.get("/api/tags", timeout=HEALTH_TIMEOUT_SECONDS)
            res.raise_for_status()
            models = res.json().get("models") or []
        except (httpx.HTTPError, ValueError, AttributeError):
            return LLMHealth(self.provider, self.model, False, False, self.local)
        names = [str(m.get("name") or m.get("model") or "") for m in models if isinstance(m, dict)]
        installed = any(same_model(n, self.model) for n in names)
        return LLMHealth(self.provider, self.model, True, installed, self.local)

    def list_models(self) -> list[dict[str, Any]] | None:
        """이 PC의 Ollama에 설치된 모델(`/api/tags`): 이름과 크기(바이트). 닿지 않으면 None."""
        try:
            res = self._http.get("/api/tags", timeout=HEALTH_TIMEOUT_SECONDS)
            res.raise_for_status()
            models = res.json().get("models") or []
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
        out = []
        for m in models:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or m.get("model") or "").strip()
            if name:
                size = m.get("size")
                out.append({"name": name, "size": int(size) if isinstance(size, int) else None})
        return out

    def warmup(self) -> float:
        """빈 `messages`로 모델을 불러 둔다(`keep_alive` 동안 머문다). 걸린 초를 돌려준다."""
        started = time.monotonic()
        self.capabilities()
        self._post(
            "/api/chat",
            {"model": self.model, "messages": [], "stream": False, "keep_alive": self.keep_alive},
        )
        return round(time.monotonic() - started, 2)

    def unload(self) -> None:
        """모델을 메모리에서 내린다(`keep_alive: 0`). 비교 스크립트가 모델을 바꿀 때 쓴다."""
        self._post(
            "/api/chat", {"model": self.model, "messages": [], "stream": False, "keep_alive": 0}
        )

    def close(self) -> None:
        self._http.close()


def _error_text(res: httpx.Response) -> str:
    try:
        data = res.json()
    except ValueError:
        return res.text[:200]
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return data["error"][:200]
    return ""
