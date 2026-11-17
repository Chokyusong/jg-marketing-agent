"""LLM 등록부: `config.yaml`의 `llm.active` 이름으로 공급자를 만든다(DESIGN 5.2.1).

`app/llm/` 밖에서 공급자 모듈(예: `app.llm.ollama`)을 직접 import하지 않는다. 종류마다
`_FACTORIES`에 한 줄씩 있다(R5: ollama · openai_compatible · anthropic · cli).
설정 화면은 고른 AI가 아닌 다른 AI도 [연결 확인]·[모델 불러오기]를 하므로 `build_provider`로
이름을 골라 만든다.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.config import ProviderSettings, Settings
from app.errors import AppError, ErrorKind
from app.llm.base import LLMClient

Factory = Callable[[Settings, ProviderSettings, httpx.BaseTransport | None], LLMClient]


def _label(provider: ProviderSettings) -> str:
    return str(provider.options.get("label") or provider.name)


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


def _build_openai_compatible(
    settings: Settings, provider: ProviderSettings, transport: httpx.BaseTransport | None
) -> LLMClient:
    from app.llm.openai_compatible import OpenAICompatibleClient

    llm = settings.llm
    opts = provider.options
    field_name = opts.get("max_tokens_field", "max_completion_tokens")
    return OpenAICompatibleClient(
        provider=provider.name,
        label=_label(provider),
        base_url=llm.base_url_for(provider.name),
        model=llm.model_for(provider.name),
        api_key=llm.api_keys.get(provider.name),
        key_optional=bool(opts.get("key_optional")),
        json_mode=bool(opts.get("json_mode")),
        max_tokens_field=str(field_name or ""),
        timeout_seconds=llm.timeout_seconds,
        transport=transport,
        secrets=settings.secret_values(),
    )


def _build_anthropic(
    settings: Settings, provider: ProviderSettings, transport: httpx.BaseTransport | None
) -> LLMClient:
    from app.llm.anthropic import DEFAULT_BASE_URL, AnthropicClient

    llm = settings.llm
    return AnthropicClient(
        provider=provider.name,
        label=_label(provider),
        model=llm.model_for(provider.name),
        api_key=llm.api_keys.get(provider.name),
        base_url=llm.base_url_for(provider.name) or DEFAULT_BASE_URL,
        timeout_seconds=llm.timeout_seconds,
        transport=transport,
        secrets=settings.secret_values(),
    )


def _build_cli(
    settings: Settings, provider: ProviderSettings, transport: httpx.BaseTransport | None
) -> LLMClient:
    from app.llm.cli import CLIClient

    llm = settings.llm
    return CLIClient(
        provider=provider.name,
        label=_label(provider),
        program=str(provider.options.get("program") or provider.name),
        model=llm.model_for(provider.name),
        timeout_seconds=llm.timeout_seconds,
        hidden_env=settings.secret_env_names,  # 이 앱의 키는 자식 프로그램에 넘기지 않는다
        secrets=settings.secret_values(),
    )


_FACTORIES: dict[str, Factory] = {
    "ollama": _build_ollama,
    "openai_compatible": _build_openai_compatible,
    "anthropic": _build_anthropic,
    "cli": _build_cli,
}


def supported_types() -> tuple[str, ...]:
    return tuple(_FACTORIES)


def build_provider(
    settings: Settings, name: str, *, transport: httpx.BaseTransport | None = None
) -> LLMClient:
    """이름으로 공급자 하나를 만든다(고른 AI가 아니어도).

    없거나 모르는 종류면 `llm_provider_unknown`."""
    llm = settings.llm
    provider = llm.providers.get(name)
    if provider is None:
        names = ", ".join(llm.providers) or "없음"
        raise AppError(
            ErrorKind.LLM_PROVIDER_UNKNOWN,
            detail=f"llm.active '{name}'이(가) llm.providers에 없습니다(있는 이름: {names}).",
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


def build_llm(settings: Settings, *, transport: httpx.BaseTransport | None = None) -> LLMClient:
    """고른 공급자(`llm.active`)를 만든다. 없거나 모르는 종류면 `llm_provider_unknown`."""
    return build_provider(settings, settings.llm.active, transport=transport)
