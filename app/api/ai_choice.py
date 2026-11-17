"""R5: 설정 화면 「AI」의 목록 · 준비 상태 · 연결 확인(설정 API와 LLM API가 함께 쓴다).

- 목록과 준비 상태는 바깥에 묻지 않는다(키·주소·모델이 있는지, 프로그램이 설치돼 있는지만).
- [연결 확인]만 바깥에 묻는다: API 키 AI는 모델 목록(`GET /models`, 글 생성 없음 — 요금이 들지
  않는 호출), 로그인된 프로그램은 그 프로그램의 로그인 상태 명령, Ollama는 이 PC 안의 목록.
- 키 값·주소는 싣지 않는다(키는 있는지와 어디서 왔는지만).
"""

from __future__ import annotations

from typing import Any

from app.api.deps import Services
from app.config import LLM_KEY_TYPES, ProviderSettings, Settings
from app.errors import AppError, ErrorKind
from app.llm.base import LLMClient
from app.llm.registry import build_provider
from app.schemas import LLMProviderOut, LLMProvidersOut, LLMTestOut

KIND_OF_TYPE = {"ollama": "local", "openai_compatible": "api", "anthropic": "api", "cli": "program"}
KIND_LABELS = {"local": "이 PC에서", "api": "API 키로", "program": "로그인된 프로그램으로"}


def label_of(provider: ProviderSettings | None, name: str = "") -> str:
    if provider is None:
        return name
    return str(provider.options.get("label") or provider.name)


def kind_of(provider: ProviderSettings | None) -> str:
    return KIND_OF_TYPE.get(provider.type, "api") if provider is not None else "local"


def sends_to(provider: ProviderSettings | None) -> str:
    if provider is None:
        return ""
    return str(provider.options.get("sends_to") or label_of(provider))


def needs_key(provider: ProviderSettings) -> bool:
    return provider.type in LLM_KEY_TYPES and not provider.options.get("key_optional")


def is_local(settings: Settings, provider: ProviderSettings) -> bool:
    if provider.type == "ollama":
        return True
    if provider.type == "openai_compatible":
        from app.llm.openai_compatible import is_local_url

        return is_local_url(settings.llm.base_url_for(provider.name))
    return False


def _cli_state(services: Services, name: str) -> tuple[bool, bool]:
    """(확인한 프로그램인지, 설치돼 있는지). PATH에서 찾기만 하고 실행하지 않는다."""
    client: Any = client_for(services, name)
    try:
        verified = bool(getattr(client, "verified", False))
        return verified, verified and client.executable() is not None
    finally:
        if client is not services.llm:
            client.close()


def _program_lists_models(provider: ProviderSettings) -> bool:
    """그 프로그램에 모델 목록 명령이 있는지(Codex `debug models`). 실행하지 않는다."""
    from app.llm.cli import SPECS

    spec = SPECS.get(str(provider.options.get("program") or provider.name))
    return bool(spec and spec.verified and spec.models_args)


def readiness(
    settings: Settings,
    provider: ProviderSettings,
    *,
    models: dict[str, str] | None = None,
    base_urls: dict[str, str] | None = None,
    installed: bool = True,
    verified: bool = True,
) -> str | None:
    """고를 수 없으면 그 이유(쉬운 한국어), 고를 수 있으면 None.

    `models`·`base_urls`는 저장하려는 값(주지 않으면 지금 값)."""
    llm = settings.llm
    name = provider.name
    if provider.type == "cli":
        if not verified:
            return "이 PC에서 안전하게 실행하는 방법을 확인하지 못해 아직 연결하지 않았습니다."
        if not installed:
            return "이 PC에 설치되지 않았습니다."
        return None
    if provider.type == "ollama":
        return None
    opts = provider.options
    if opts.get("editable_url"):
        urls = base_urls if base_urls is not None else llm.base_urls
        if not (urls.get(name) or str(opts.get("base_url") or "")):
            return "주소를 먼저 넣어 주세요."
    if needs_key(provider) and not llm.api_keys.get(name):
        return "API 키를 먼저 넣어 주세요."
    chosen = models if models is not None else llm.models
    if not (chosen.get(name) or str(opts.get("model") or "")):
        return "쓸 모델을 먼저 골라 주세요."
    return None


DEFAULT_MODEL_LABEL = "기본값 (그 프로그램이 정한 모델)"


def recommended_models(provider: ProviderSettings) -> list[str]:
    """config.yaml `llm.providers.<이름>.models`(공식 문서로 확인한 이름만 적는 추천 목록)."""
    raw = provider.options.get("models")
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            continue
        name = str(item).strip()
        if name and len(name) <= 200 and name not in out:
            out.append(name)
    return out


def client_for(services: Services, name: str) -> LLMClient:
    """그 이름의 공급자. 지금 쓰는 AI면 그것을, 아니면 새로 만든다(쓴 뒤 닫는다)."""
    if services.llm is not None and services.settings.llm.active == name:
        return services.llm
    return build_provider(services.settings, name, transport=services.llm_transport)


def provider_view(services: Services, provider: ProviderSettings) -> LLMProviderOut:
    settings = services.settings
    llm = settings.llm
    name = provider.name
    store = settings.source.store() if settings.source is not None else None
    verified, installed = True, True
    if provider.type == "cli":
        verified, installed = _cli_state(services, name)
    key_type = provider.type in LLM_KEY_TYPES
    return LLMProviderOut(
        name=name,
        label=label_of(provider),
        type=provider.type,
        kind=kind_of(provider),  # type: ignore[arg-type]
        active=llm.active == name,
        local=is_local(settings, provider),
        sends_to=sends_to(provider),
        model=llm.model_for(name),
        needs_key=needs_key(provider),
        key_allowed=key_type,
        key_configured=bool(llm.api_keys.get(name)) if key_type else False,
        key_source=llm.key_sources.get(name),  # type: ignore[arg-type]
        can_store_key=bool(key_type and store and store.protector.available),
        url_editable=bool(provider.options.get("editable_url")),
        models_listable=provider.type != "cli",
        installed=installed,
        verified=verified,
        unavailable_reason=readiness(settings, provider, installed=installed, verified=verified),
        recommended_models=recommended_models(provider),
        default_label=DEFAULT_MODEL_LABEL if provider.type == "cli" else "",
        models_from_program=provider.type == "cli" and _program_lists_models(provider),
    )


def providers_view(services: Services) -> LLMProvidersOut:
    llm = services.settings.llm
    return LLMProvidersOut(
        active=llm.active,
        items=[provider_view(services, p) for p in llm.providers.values()],
        kinds=[{"value": k, "label": v} for k, v in KIND_LABELS.items()],
    )


# ---------------------------------------------------------------- [연결 확인]

_TEST = {
    ErrorKind.LLM_RATE_LIMITED: "rate_limited",
    ErrorKind.LLM_DOWN: "network",
    ErrorKind.LLM_TIMEOUT: "network",
    ErrorKind.LLM_SETTINGS_INVALID: "no_url",
    ErrorKind.LLM_MODEL_MISSING: "error",
}


def _fail(result: str, err: AppError | None, message: str = "", action: str = "") -> LLMTestOut:
    return LLMTestOut(
        ok=False,
        result=result,  # type: ignore[arg-type]
        message=message or (err.message if err else ""),
        action=action or (err.action if err else ""),
    )


def check_provider(services: Services, name: str) -> LLMTestOut:
    llm = services.settings.llm
    provider = llm.providers.get(name)
    if provider is None:
        raise AppError(ErrorKind.LLM_PROVIDER_UNKNOWN, detail=f"'{name}'은(는) 목록에 없습니다.")
    label = label_of(provider)
    client = client_for(services, name)
    try:
        return _test(services, provider, client, label)
    finally:
        if client is not services.llm:
            client.close()


def _test(services: Services, provider: ProviderSettings, client: Any, label: str) -> LLMTestOut:
    if provider.type == "ollama":
        health = client.health()
        if not health.reachable:
            return _fail("network", AppError(ErrorKind.LLM_DOWN))
        return LLMTestOut(ok=True, result="ok", message=f"{label}에 연결됐습니다(이 PC 안).")
    if provider.type == "cli":
        if not client.verified:
            return _fail("not_wired", None, f"{label}은(는) 아직 연결하지 않았습니다.",
                         "다른 AI를 골라 주세요.")
        if client.executable() is None:
            return _fail("not_installed", None, f"{label}이(가) 이 PC에 설치돼 있지 않습니다.",
                         f"{label}을(를) 설치하고 로그인한 뒤 다시 [연결 확인]을 눌러 주세요.")
        version = client.version()
        logged_in = client.login_status()
        if logged_in is False:
            return _fail("not_logged_in", None, f"{label}에 로그인돼 있지 않습니다.",
                         client.spec.login_hint)
        where = f" · {version}" if version else ""
        if logged_in:
            message = f"{label}이(가) 설치돼 있고 로그인돼 있습니다{where}."
        else:
            message = f"{label}이(가) 설치돼 있습니다{where}. 로그인 여부는 확인하지 못했습니다."
        return LLMTestOut(ok=True, result="ok", version=version, message=message)
    # API 키 AI: 모델 목록(글을 만들지 않는 호출)으로 키가 통하는지 본다
    problem = client.problem()
    if problem is not None and problem.kind is not ErrorKind.LLM_MODEL_MISSING:
        if problem.kind is ErrorKind.LLM_AUTH:
            return _fail("no_key", problem)
        return _fail(_TEST.get(problem.kind, "error"), problem)
    try:
        found = client.list_models()
    except AppError as exc:
        if exc.kind is ErrorKind.LLM_AUTH:
            return _fail("rejected", exc)
        return _fail(_TEST.get(exc.kind, "error"), exc)
    return LLMTestOut(
        ok=True, result="ok", models=len(found),
        message=f"연결됐습니다. {label}이(가) 키를 받아 줬습니다(모델 {len(found)}개).",
    )
