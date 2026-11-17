"""설정 API. 9단계의 읽기 전용 `GET /api/settings`에 R2의 저장·바로 적용을 더했다.

R2(프로그램 안에서 설정):
- `GET /api/settings`: 지금 값과 함께 편집에 필요한 값
  (`edit`: 지금 값·기본값·바꾼 칸·범위·고르는 값).
- `PUT /api/settings`(부분 저장) · `POST /api/settings/reset`([기본값으로], 키는 남긴다).
  칸별 검증(`app/user_settings.validate`): 잘못된 칸과 이유를 `fields`에 담아 422로 돌려준다.
  저장하면 바로 적용(`ServiceHolder.update_settings` — 서비스 묶음을 새 설정으로 다시 만든다).
  게시 중이면 `settings_busy`("지금 게시 중입니다. 끝난 뒤 다시 저장해 주세요").
- `PUT`·`DELETE /api/settings/youtube-key`: 키를 DPAPI로 암호화해 저장 / 지운다. 응답에는 키가 없다
  (「저장됨」 여부와 어디서 왔는지만).
  `POST /api/settings/youtube-key/test`: 1단위짜리 호출로 연결 확인.
- `GET /api/screens`: 크롬 창을 띄울 모니터 목록(9단계 `read_monitors`). 고르면 그 모니터의 안전한
  위치(왼쪽 위에서 60,60)를 계산해 `browser.window_position`에 저장한다(좌표를 직접 치지 않는다).

9단계부터:
- 비밀값(YouTube 키, LLM 키)은 있는지 없는지만. PC의 경로(프로필 폴더 위치, 크롬 위치, DB 위치),
  LLM 주소도 싣지 않는다(공개 저장소 규칙, AGENTS.md).
- 모델을 부르지 않는다(Ollama가 꺼져 있어도 바로 답한다). AI가 켜져 있는지는 `GET /api/status`.
- 크롬 창 위치는 설정값과, 지금 모니터 배치에서 실제로 띄울 위치를 함께 준다(화면 밖이면 바꾼 값).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.api.ai_choice import kind_of, label_of, readiness, sends_to
from app.api.deps import ServiceHolder, Services, get_services
from app.api.status import _problem
from app.browser.chrome import profile_dir
from app.browser.placement import AUTO, plan_window
from app.browser.screens import find_choice, screen_choices
from app.config import (
    DEFAULT_OLLAMA_MODEL,
    LLM_KEY_TYPES,
    ProviderSettings,
    Settings,
    load_settings,
    reload_settings,
)
from app.errors import ERROR_TEXTS, AppError, ErrorKind
from app.schemas import (
    TARGET_LABELS,
    ChoiceOut,
    KeyTestOut,
    LLMKeyIn,
    LLMKeyOut,
    QuotaOut,
    ScreenOut,
    ScreensOut,
    SettingsBrowserOut,
    SettingsCommentOut,
    SettingsDiscoverOut,
    SettingsEditOut,
    SettingsLLMOut,
    SettingsOut,
    SettingsProfileOut,
    SettingsUpdateIn,
    SettingsYouTubeOut,
    YouTubeKeyIn,
    YouTubeKeyOut,
)
from app.user_settings import (
    COMPUTED_FIELDS,
    FIELDS,
    TYPING_SPEED_LABELS,
    SecretStoreUnavailable,
    UserStore,
    key_shape_ok,
    llm_key_shape_ok,
    validate,
)

router = APIRouter(prefix="/api", tags=["settings"])

# 값은 저장하지만 동작에는 아직 쓰지 않는 칸(화면에 「곧 적용」). R3에서 광고 표기 기본값과
# 게시 직전 확인을 게시에 연결해 지금은 비어 있다(응답 모양은 그대로 둔다)
APPLIES_LATER: list[str] = []


def _xy(point: tuple[int, int] | None) -> str | None:
    return f"{point[0]},{point[1]}" if point else None


def llm_settings(services: Services) -> SettingsLLMOut:
    cfg = services.settings.llm
    provider = cfg.active_provider
    llm = services.llm
    return SettingsLLMOut(
        active=cfg.active,
        type=provider.type if provider else "",
        model=(llm.model if llm is not None else "")
        if provider is None or provider.type == "ollama"
        else cfg.model_for(provider.name),
        local=bool(llm.local) if llm is not None else True,
        timeout_seconds=cfg.timeout_seconds,
        keep_alive=cfg.keep_alive,
        context_chars=services.settings.context_chars,
        error=_problem(services.llm_error) if services.llm_error else None,
        cold_timeout_seconds=cfg.cold_timeout_seconds,
        warmup_on_start=cfg.warmup_on_start,
        recommended_model=DEFAULT_OLLAMA_MODEL,
        label=label_of(provider, cfg.active),
        kind=kind_of(provider),  # type: ignore[arg-type]
        sends_to=sends_to(provider),
    )


def window_plan(services: Services):
    """지금 모니터로 크롬 창을 띄울 곳(설정 화면 한 줄 「지금은 모니터 2(위쪽)에 뜹니다」)."""
    b = services.settings.browser
    monitors = services.monitors()
    app = services.app_monitor(monitors) if monitors else None
    plan = plan_window(monitors, screen=b.window_screen, legacy=b.window_position,
                       app_monitor=app)
    return plan, bool([m for m in monitors if m.valid])


def browser_settings(services: Services) -> SettingsBrowserOut:
    b = services.settings.browser
    plan, checked = window_plan(services)
    target = services.settings.default_target
    screen = b.window_screen or ("" if b.window_position is not None else AUTO)
    note = plan.note if checked else "모니터 정보를 읽지 못해 설정값 그대로"
    if plan.mode == "legacy" and not plan.adjusted:
        note = "화면 안"
    return SettingsBrowserOut(
        default_target=target,  # type: ignore[arg-type]
        default_target_label=TARGET_LABELS.get(target, target),
        headless=b.headless,
        window_position=_xy(b.window_position) or "",
        window_position_used=_xy(plan.position),
        window_position_adjusted=plan.adjusted,
        window_position_checked=checked,
        window_position_note=note,
        window_screen=screen,
        window_auto=plan.mode == "auto",
        window_where=plan.where_text,
        window_size_used=f"{plan.size[0]}×{plan.size[1]}" if plan.size else "",
        window_fell_back=plan.fell_back,
        typing_delay_ms=list(b.typing_delay_ms),
        chrome_found=services.find_chrome() is not None,
        playwright_ready=services.jobs.playwright_ready(),
    )


def _holder(request: Request) -> ServiceHolder:
    return request.app.state.services


def effective_values(s: Settings) -> dict[str, Any]:
    """지금 쓰는 값(칸 이름 → 값). 키 값은 들어가지 않는다."""
    comment = s.rules.get("comment") or {}
    return {
        "llm.model": s.llm.ollama_model,
        "comment.min_chars": int(comment.get("min_chars", 40)),
        "comment.max_chars": int(comment.get("max_chars", 120)),
        "comment.brand": str(comment.get("brand", "운명원")),
        "brand.facts": list(s.brand_facts),
        "comment.disclosure": str(comment.get("disclosure", "[광고]")),
        "comment.disclose_default": s.disclose_default,
        "comment.ai_review": s.ai_review,
        "limits.daily_max_comments": s.daily_max_comments,
        "posting.confirm_before_post": s.confirm_before_post,
        "browser.typing_speed": s.typing_speed,
        "browser.window_screen": s.window_screen or "",
        "browser.window_position": _xy(s.browser.window_position) or "",
        "discover.query": s.discover.query,
        "discover.max_results": s.discover.max_results,
        "discover.exclude_shorts": s.discover.exclude_shorts,
        "discover.shorts_under_seconds": s.discover.shorts_under_seconds,
        # R4
        "transcript.auto": s.transcript_provider == "auto",
        "llm.warmup_on_start": s.llm.warmup_on_start,
        "rising.query": s.rising.query,
        "rising.min_views": s.rising.min_views,
        "rising.max_views": s.rising.max_views,
        "rising.min_views_per_hour": s.rising.min_views_per_hour,
        # R5: 글 쓰는 AI, AI별 모델, 「직접 입력」 주소(키는 싣지 않는다)
        "llm.active": s.llm.active,
        "llm.models": dict(s.llm.models),
        "llm.base_urls": dict(s.llm.base_urls),
    }


def _defaults(s: Settings) -> Settings:
    return reload_settings(s, use_user=False) if s.source is not None else s


def _store(s: Settings) -> UserStore | None:
    return s.source.store() if s.source is not None else None


def key_out(s: Settings) -> YouTubeKeyOut:
    store = _store(s)
    return YouTubeKeyOut(
        key_configured=s.youtube_key_configured,
        key_source=s.youtube_key_source,  # type: ignore[arg-type]
        can_store_key=bool(store and store.protector.available),
    )


def edit_view(s: Settings) -> SettingsEditOut:
    return SettingsEditOut(
        values=effective_values(s),
        defaults=effective_values(_defaults(s)),
        changed=sorted(k for k in s.user_values if k in FIELDS),
        ranges={k: [int(f.lo or 0), int(f.hi or 0)] for k, f in FIELDS.items() if f.kind == "int"},
        typing_speeds=[ChoiceOut(value=k, label=v) for k, v in TYPING_SPEED_LABELS.items()],
        store_ready=_store(s) is not None,
        applies_later=APPLIES_LATER,
    )


def settings_view(request: Request, services: Services) -> SettingsOut:
    s = services.settings
    comment = s.rules.get("comment") or {}
    root = s.browser.profiles_root
    key = key_out(s)
    return SettingsOut(
        version=str(request.app.version),
        stage=int(getattr(request.app.state, "stage", 0)),
        comment=SettingsCommentOut(
            min_chars=int(comment.get("min_chars", 40)),
            max_chars=int(comment.get("max_chars", 120)),
            disclosure=str(comment.get("disclosure", "[광고]")),
            brand=str(comment.get("brand", "운명원")),
        ),
        brand_facts=list(s.brand_facts),
        daily_max_comments=s.daily_max_comments,
        profiles=[
            SettingsProfileOut(
                name=p.name, folder=p.folder, ready=profile_dir(root, p.folder).is_dir()
            )
            for p in services.profiles.list_profiles()
        ],
        llm=llm_settings(services),
        browser=browser_settings(services),
        youtube=SettingsYouTubeOut(
            key_configured=s.youtube_key_configured,
            quota=QuotaOut(**services.quota.summary()),
            key_source=key.key_source,
            can_store_key=key.can_store_key,
        ),
        discover=SettingsDiscoverOut(
            query=s.discover.query,
            max_results=s.discover.max_results,
            exclude_shorts=s.discover.exclude_shorts,
            shorts_under_seconds=s.discover.shorts_under_seconds,
        ),
        transcript_provider=s.transcript_provider,
        edit=edit_view(s),
    )


@router.get("/settings", response_model=SettingsOut)
def settings(request: Request, services: Annotated[Services, Depends(get_services)]) -> SettingsOut:
    return settings_view(request, services)


def _invalid(fields: dict[str, str]) -> AppError:
    return AppError(ErrorKind.SETTINGS_INVALID, extra={"fields": fields})


@router.put("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdateIn, request: Request) -> SettingsOut:
    """바꾼 칸만 보내도 된다. 잘못된 칸이 하나라도 있으면 아무것도 저장하지 않는다."""
    holder = _holder(request)
    services = holder.get()
    current = services.settings
    store = _store(current)
    if store is None or current.source is None:
        raise AppError(ErrorKind.SETTINGS_NO_STORE)
    changes = dict(body.values)
    computed: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in COMPUTED_FIELDS:
        if name in changes:
            errors[name] = "바꿀 수 없는 칸입니다(크롬 창을 띄울 화면을 고르면 정해집니다)"
            changes.pop(name)
    if "browser.window_screen" in changes:
        screen_id = str(changes.pop("browser.window_screen") or "")
        choice = find_choice(screen_choices(services.monitors()), screen_id)
        if screen_id == AUTO:  # 「자동 (권장)」: 옛 좌표는 지운다(기본값과 같아 파일에서 빠진다)
            computed["browser.window_screen"] = AUTO
            computed["browser.window_position"] = ""
        elif choice is None:
            errors["browser.window_screen"] = "연결된 모니터에서 골라 주세요"
        else:
            computed["browser.window_screen"] = choice.id
            computed["browser.window_position"] = _xy(choice.position)
    clean, problems = validate(changes, effective_values(current))
    errors.update(problems)
    if not errors:
        errors.update(_check_llm(services, store, clean))
    if errors:
        raise _invalid(errors)
    defaults = effective_values(_defaults(current))
    candidate = {**store.read_values(), **clean, **computed}
    # 기본값과 같은 칸은 파일에 두지 않는다(나중에 config.yaml 기본값이 바뀌면 따라가게)
    candidate = {k: v for k, v in candidate.items() if defaults.get(k) != v}
    src = current.source
    try:  # 저장하기 전에 새 값으로 설정이 제대로 읽히는지 본다
        load_settings(
            src.config_path, src.env_path, db_path=src.db_path, environ=src.environ,
            user_dir=src.user_dir, protector=src.protector, user_values=candidate,
        )
    except ValueError as exc:
        raise _invalid({"_": str(exc)}) from None

    def write(st: UserStore) -> None:
        try:
            if candidate:
                st.write_values(candidate)
            else:
                st.clear_values()
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    holder.update_settings(write)
    return settings_view(request, holder.get())


def _merged(stored: Any, sent: dict[str, str]) -> dict[str, str]:
    """AI별 값은 보낸 이름만 바꾼다. 빈 글은 그 이름을 지운다."""
    out = {str(k): str(v) for k, v in (stored.items() if isinstance(stored, dict) else [])}
    for name, value in sent.items():
        if value:
            out[name] = value
        else:
            out.pop(name, None)
    return out


def _check_llm(services: Services, store: UserStore, clean: dict[str, Any]) -> dict[str, str]:
    """R5: AI 칸을 저장 전에 본다. `clean`의 AI별 값은 저장된 값과 합친 것으로 바꿔 둔다."""
    from app.api.ai_choice import _cli_state

    llm = services.settings.llm
    errors: dict[str, str] = {}
    stored = store.read_values()
    for name in ("llm.models", "llm.base_urls"):
        if name not in clean:
            continue
        unknown = [k for k in clean[name] if k not in llm.providers]
        if unknown:
            errors[name] = f"목록에 없는 AI입니다: {', '.join(sorted(unknown))}"
            continue
        if name == "llm.base_urls":
            fixed = [k for k in clean[name] if not llm.providers[k].options.get("editable_url")]
            if fixed:
                errors[name] = "주소를 바꿀 수 없는 AI입니다(「직접 입력」만 주소를 적습니다)"
                continue
        clean[name] = _merged(stored.get(name), clean[name])
    if errors or "llm.active" not in clean:
        return errors
    active = str(clean["llm.active"])
    provider = llm.providers.get(active)
    if provider is None:
        return {"llm.active": "목록에 없는 AI입니다"}
    from app.llm.registry import supported_types

    if provider.type not in supported_types():
        return {"llm.active": "아직 쓸 수 없는 종류의 AI입니다"}
    verified, installed = (True, True)
    if provider.type == "cli":
        verified, installed = _cli_state(services, active)
    models = clean.get("llm.models", llm.models)
    urls = clean.get("llm.base_urls", llm.base_urls)
    reason = readiness(
        services.settings, provider, models=models, base_urls=urls,
        installed=installed, verified=verified,
    )
    if reason:
        errors["llm.active"] = reason
    return errors


@router.post("/settings/reset", response_model=SettingsOut)
def reset_settings(request: Request) -> SettingsOut:
    """[기본값으로]: 바꾼 값을 모두 지우고 config.yaml 값으로. 저장한 API 키는 남긴다."""
    holder = _holder(request)

    def clear(st: UserStore) -> None:
        try:
            st.clear_values()
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    holder.update_settings(clear)
    return settings_view(request, holder.get())


# ---------------------------------------------------------------- 유튜브 API 키


@router.put("/settings/youtube-key", response_model=YouTubeKeyOut)
def save_youtube_key(body: YouTubeKeyIn, request: Request) -> YouTubeKeyOut:
    key = body.key.strip()
    if not key_shape_ok(key):
        raise AppError(ErrorKind.KEY_BAD_SHAPE)
    holder = _holder(request)
    if not holder.store().protector.available:
        raise AppError(ErrorKind.SECRET_STORE_UNAVAILABLE)

    def write(st: UserStore) -> None:
        try:
            st.write_key(key)
        except SecretStoreUnavailable:
            raise AppError(ErrorKind.SECRET_STORE_UNAVAILABLE) from None
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    return key_out(holder.update_settings(write))


@router.delete("/settings/youtube-key", response_model=YouTubeKeyOut)
def delete_youtube_key(request: Request) -> YouTubeKeyOut:
    """프로그램에 저장한 키를 지운다(개발용 .env의 키는 그대로 — 응답의 key_source로 알린다)."""
    holder = _holder(request)

    def remove(st: UserStore) -> None:
        try:
            st.delete_key()
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    return key_out(holder.update_settings(remove))


_KEY_TEST = {
    ErrorKind.MISSING_KEY: ("no_key", "아직 API 키가 없습니다."),
    ErrorKind.KEY_REJECTED: ("rejected", "유튜브가 이 키를 받아 주지 않았습니다."),
    ErrorKind.QUOTA_EXCEEDED: (
        "quota",
        "키는 맞지만 오늘 쓸 수 있는 양을 다 썼습니다. 한국 시간 오후 4~5시쯤 다시 채워집니다.",
    ),
    ErrorKind.NETWORK: ("network", "인터넷에 연결하지 못해 확인하지 못했습니다."),
}


@router.post("/settings/youtube-key/test", response_model=KeyTestOut)
def test_youtube_key(services: Annotated[Services, Depends(get_services)]) -> KeyTestOut:
    """1단위짜리 호출로 키가 통하는지 본다(검색 100단위를 쓰지 않는다). 결과를 쉬운 말로."""
    try:
        services.videos.client.ping()
    except AppError as exc:
        result, message = _KEY_TEST.get(exc.kind, ("error", "유튜브에서 알 수 없는 답이 왔습니다."))
        action = ERROR_TEXTS[exc.kind].action
        if exc.kind is ErrorKind.MISSING_KEY:
            action = "위 칸에 API 키를 넣고 [키 저장]을 누르세요."
        elif exc.kind is ErrorKind.NETWORK:
            action = "인터넷 연결을 확인한 뒤 다시 [연결 확인]을 눌러 주세요."
        return KeyTestOut(
            ok=False,
            result=result,  # type: ignore[arg-type]
            message=message,
            action=action,
            quota=QuotaOut(**services.quota.summary()),
        )
    return KeyTestOut(
        ok=True,
        result="ok",
        message="연결됐습니다. 유튜브가 키를 받아 줬습니다.",
        quota=QuotaOut(**services.quota.summary()),
    )


# ---------------------------------------------------------------- R5: AI API 키(AI마다 따로)


def _key_provider(s: Settings, name: str) -> ProviderSettings:
    provider = s.llm.providers.get(name)
    if provider is None or provider.type not in LLM_KEY_TYPES:
        raise AppError(
            ErrorKind.SETTINGS_INVALID, extra={"fields": {"key": "API 키를 넣을 수 없는 AI입니다"}}
        )
    return provider


def llm_key_out(s: Settings, name: str) -> LLMKeyOut:
    store = _store(s)
    return LLMKeyOut(
        name=name,
        key_configured=bool(s.llm.api_keys.get(name)),
        key_source=s.llm.key_sources.get(name),  # type: ignore[arg-type]
        can_store_key=bool(store and store.protector.available),
    )


@router.put("/settings/llm-key/{name}", response_model=LLMKeyOut)
def save_llm_key(name: str, body: LLMKeyIn, request: Request) -> LLMKeyOut:
    """그 AI의 API 키를 사용자 폴더에 암호화해 저장하고 바로 적용한다. 응답에는 키가 없다."""
    holder = _holder(request)
    provider = _key_provider(holder.settings, name)
    label = str(provider.options.get("label") or name)
    key = body.key.strip()
    if not llm_key_shape_ok(key):
        raise AppError(
            ErrorKind.KEY_BAD_SHAPE,
            action=f"{label}에서 복사한 키를 앞뒤 빈칸 없이 그대로 붙여 넣어 주세요.",
        )
    if not holder.store().protector.available:
        raise AppError(
            ErrorKind.SECRET_STORE_UNAVAILABLE,
            action=f"개발용 .env 파일의 {provider.api_key_env or 'API 키 칸'}에 키를 넣고 "
            "프로그램을 다시 켜 주세요.",
        )

    def write(st: UserStore) -> None:
        try:
            st.write_llm_key(name, key)
        except SecretStoreUnavailable:
            raise AppError(ErrorKind.SECRET_STORE_UNAVAILABLE) from None
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    return llm_key_out(holder.update_settings(write), name)


@router.delete("/settings/llm-key/{name}", response_model=LLMKeyOut)
def delete_llm_key(name: str, request: Request) -> LLMKeyOut:
    """프로그램에 저장한 그 AI의 키를 지운다(.env의 키는 그대로 — key_source로 알린다)."""
    holder = _holder(request)
    _key_provider(holder.settings, name)

    def remove(st: UserStore) -> None:
        try:
            st.delete_llm_key(name)
        except OSError:
            raise AppError(ErrorKind.SETTINGS_WRITE_FAILED) from None

    return llm_key_out(holder.update_settings(remove), name)


# ---------------------------------------------------------------- 모니터


@router.get("/screens", response_model=ScreensOut)
def screens(services: Annotated[Services, Depends(get_services)]) -> ScreensOut:
    position = services.settings.browser.window_position
    items = [
        ScreenOut(
            id=c.id,
            label=c.label,
            left=c.left,
            top=c.top,
            width=c.width,
            height=c.height,
            primary=c.primary,
            position=_xy(c.position) or "",
            current=c.current,
        )
        for c in screen_choices(services.monitors(), position)
    ]
    plan, _checked = window_plan(services)
    b = services.settings.browser
    screen = b.window_screen or ("" if b.window_position is not None else AUTO)
    auto_plan = plan_window(services.monitors(), screen=AUTO,
                            app_monitor=services.app_monitor(services.monitors()))
    return ScreensOut(
        checked=bool(items), window_position=_xy(position) or "", items=items,
        screen=screen, where=plan.where_text, auto_where=auto_plan.where_text,
        note=plan.note,
    )
