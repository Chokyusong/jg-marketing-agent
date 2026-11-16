"""LLM 등록부: `config.yaml`의 `llm.active` 이름으로 공급자를 만든다(DESIGN 5.2.1).

`app/llm/` 밖에서 공급자 모듈(예: `app.llm.ollama`)을 직접 import하지 않는다. 다른 공급자는
12단계에서 `_FACTORIES`에 한 줄씩 더한다.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.config import ProviderSettings, Settings
from app.errors import AppError, ErrorKind
from app.llm.base import LLMClient

Factory = Callable[[Settings, ProviderSettings, httpx.BaseTransport | None], LLMClient]


def _build_ollama(
    settings: Settings, provider: ProviderSettings, transport: httpx.BaseTransport | None
) -> LLMClient:
    from app.llm.ollama import OllamaClient

    llm = settings.llm
    # 주소·모델은 .env(OLLAMA_BASE_URL, OLLAMA_MODEL). providers 항목에 적으면 그것이 먼저다
    return OllamaClient(
        provider=provider.name,
        model=str(provider.options.get("model") or llm.ollama_model),
        base_url=str(provider.options.get("base_url") or llm.ollama_base_url),
        timeout_seconds=llm.timeout_seconds,
        cold_timeout_seconds=llm.cold_timeout_seconds,
        num_ctx=llm.num_ctx,
        keep_alive=llm.keep_alive,
        transport=transport,
        secrets=settings.secret_values(),
    )


_FACTORIES: dict[str, Factory] = {
    "ollama": _build_ollama,
}


def supported_types() -> tuple[str, ...]:
    return tuple(_FACTORIES)


def build_llm(settings: Settings, *, transport: httpx.BaseTransport | None = None) -> LLMClient:
    """고른 공급자(`llm.active`)를 만든다. 없거나 모르는 종류면 `llm_provider_unknown`."""
    llm = settings.llm
    provider = llm.active_provider
    if provider is None:
        names = ", ".join(llm.providers) or "없음"
        raise AppError(
            ErrorKind.LLM_PROVIDER_UNKNOWN,
            detail=f"llm.active '{llm.active}'이(가) llm.providers에 없습니다(있는 이름: {names}).",
        )
    factory = _FACTORIES.get(provider.type)
    if factory is None:
        raise AppError(
            ErrorKind.LLM_PROVIDER_UNKNOWN,
            detail=(
                f"'{provider.name}'의 종류 '{provider.type}'는 아직 지원하지 않는 공급자입니다"
                f"(지금 쓸 수 있는 종류: {', '.join(supported_types())})."
            ),
        )
    return factory(settings, provider, transport)
