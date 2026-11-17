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
from app.schemas import (
    FirstRunPathOut,
    InstallGuideOut,
    LLMProviderOut,
    LLMProvidersOut,
    LLMTestOut,
)

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
    program_extra: dict[str, Any] = {}
    if provider.type == "cli":
        verified, installed = _cli_state(services, name)
        program_extra = _program_view(services, provider, verified=verified, installed=installed)
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
        **program_extra,
    )


def _program_view(
    services: Services, provider: ProviderSettings, *, verified: bool, installed: bool
) -> dict[str, Any]:
    """로그인된 프로그램 한 줄에 더하는 것: 로그인 상태·창, [설치 방법 보기], 물리지 않은 까닭."""
    from app.llm.cli_guides import GUIDES, NOT_WIRED, NOT_WIRED_PAGE
    from app.llm.cli_login import LOGIN_COMMANDS

    program = str(provider.options.get("program") or provider.name)
    view = services.cli_logins.view(provider.name)
    guide = GUIDES.get(program)
    out: dict[str, Any] = {
        "logged_in": view.logged_in if installed else None,
        "login_asked": view.asked if installed else False,
        "login_window_open": view.window_open,
        "login_checking": view.checking,
        "can_open_login": verified and installed and program in LOGIN_COMMANDS,
        "install_guide": InstallGuideOut(
            command=guide.command, page=guide.page, shell=guide.shell, notes=list(guide.notes),
            checked=guide.checked,
        ) if guide and verified else None,
    }
    if not verified:
        out["not_wired_notes"] = list(NOT_WIRED.get(program, ()))
        out["not_wired_page"] = NOT_WIRED_PAGE.get(program, "")
    return out


def providers_view(services: Services) -> LLMProvidersOut:
    llm = services.settings.llm
    items = [provider_view(services, p) for p in llm.providers.values()]
    return LLMProvidersOut(
        active=llm.active,
        items=items,
        kinds=[{"value": k, "label": v} for k, v in KIND_LABELS.items()],
        first_run=first_run_paths(items),
    )


def first_run_paths(items: list[LLMProviderOut]) -> list[FirstRunPathOut]:
    """처음 켠 PC에서 AI를 붙이는 세 길(권하는 순서): 구독 프로그램 → API 키 → Ollama.

    「무료」는 공식 가격 페이지에 무료 등급이 적힌 곳(Gemini API)에만 쓴다
    (app/llm/cli_guides.py)."""
    from app.llm.cli_guides import (
        FIRST_RUN_KEY_CHECKED,
        FIRST_RUN_KEY_NAME,
        FIRST_RUN_KEY_PAGE,
        OLLAMA_NOTE,
        OLLAMA_PAGE,
    )

    by_name = {p.name: p for p in items}
    programs = [p.name for p in items if p.kind == "program" and p.verified]
    labels = " · ".join(by_name[n].label for n in programs)
    key_ai = by_name.get(FIRST_RUN_KEY_NAME)
    ollama = [p.name for p in items if p.type == "ollama"]
    paths = [
        FirstRunPathOut(
            key="program", title=f"구독 중인 프로그램으로 ({labels})",
            detail="이미 ChatGPT·Claude 유료 요금제를 쓰고 있다면 그 프로그램을 설치하고 "
                   "로그인합니다. [설치 방법 보기] → [로그인하기]",
            providers=programs,
            ready=any(by_name[n].installed and by_name[n].logged_in is True for n in programs),
        ),
    ]
    if key_ai is not None:
        paths.append(FirstRunPathOut(
            key="key", title=f"API 키로 ({key_ai.label})",
            detail="세 걸음: [키 받는 페이지 열기] → 이 AI 칸에 키 붙여 넣기 → "
                   "[연결 확인]. Gemini API에는 무료 등급이 있습니다"
                   f"(공식 가격 안내, {FIRST_RUN_KEY_CHECKED} 확인. 무료 등급 자료는 "
                   "구글 제품 개선에 쓰일 수 있고, 한도는 AI Studio에서 보입니다).",
            providers=[key_ai.name], link=FIRST_RUN_KEY_PAGE, link_label="키 받는 페이지 열기",
            ready=key_ai.key_configured,
        ))
    if ollama:
        paths.append(FirstRunPathOut(
            key="ollama", title="이 PC에서 (Ollama)",
            detail=f"영상 자료가 PC 밖으로 나가지 않습니다. {OLLAMA_NOTE}",
            providers=ollama, link=OLLAMA_PAGE, link_label="Ollama 설치 안내 열기",
        ))
    return paths


# ---------------------------------------------------------------- [로그인하기](2026-11-17)


def program_login(services: Services, name: str) -> bool | None:
    """그 프로그램의 로그인 상태 명령으로 묻는다(종료 코드 0 = 로그인됨). 물을 수 없으면 None.

    그 프로그램이 저장한 로그인 정보는 읽지 않는다."""
    provider = services.settings.llm.providers.get(name)
    if provider is None or provider.type != "cli":
        return None
    client: Any = client_for(services, name)
    try:
        if not client.verified or client.executable() is None:
            return None
        return client.login_status()
    finally:
        if client is not services.llm:
            client.close()


def open_program_login(services: Services, name: str) -> Any:
    """[로그인하기]: 그 프로그램의 자기 로그인 명령을 보이는 명령 창으로 연다(셸 없이 인자 목록)."""
    from app.llm.cli_login import LOGIN_COMMANDS, login_args

    provider = services.settings.llm.providers.get(name)
    if provider is None:
        raise AppError(ErrorKind.LLM_PROVIDER_UNKNOWN, detail=f"'{name}'은(는) 목록에 없습니다.")
    label = label_of(provider)
    client: Any = client_for(services, name)
    try:
        program = getattr(client, "program", "")
        exe = client.executable() if provider.type == "cli" else None
        if provider.type != "cli" or not client.verified or program not in LOGIN_COMMANDS:
            raise AppError(ErrorKind.LLM_SETTINGS_INVALID,
                           detail=f"{name}: 로그인 창을 열지 않는 AI",
                           message=f"{label}은(는) 이 화면에서 로그인 창을 열 수 없습니다.")
        if exe is None:
            raise AppError(ErrorKind.LLM_DOWN, detail=f"{name}: 설치되지 않음",
                           message=f"{label}이(가) 이 PC에 설치돼 있지 않습니다.",
                           action="[설치 방법 보기]를 눌러 설치한 뒤 다시 눌러 주세요.")
        env = client.child_env()
    finally:
        if client is not services.llm:
            client.close()
    return services.cli_logins.open(name, login_args(program, exe), env)


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
        # 화면의 「로그인 필요」·[로그인하기]
        services.cli_logins.remember(provider.name, logged_in)
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
