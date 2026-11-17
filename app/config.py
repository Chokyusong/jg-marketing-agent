"""설정 읽기: 사용자 설정(프로그램 안에서 바꾼 값) → 환경 변수·`.env`(개발용)
→ `config.yaml`(기본값).

- R2: 프로그램 안에서 바꾼 값과 암호화한 유튜브 API 키는 `%LOCALAPPDATA%/JGMarketingAgent`
  (`app/user_settings.py`). `load_settings(user_dir=...)`를 줄 때만 읽는다(자동 테스트가 이 PC의
  설정을 읽지 않게). 실제 프로그램은 `ServiceHolder`가 `default_user_dir()`를 준다.
  키는 저장한 키 > 환경 변수·`.env`, AI 모델은 고른 모델 > `OLLAMA_MODEL` > 코드 기본 모델.

- 키가 없어도 앱은 뜬다. YouTube를 부를 때 `missing_key` 오류로 알려 준다.
- 키 값은 `repr`·로그에 나오지 않는다. 쓰는 곳은 `app/youtube/client.py` 하나다.
- 4단계: LLM 설정은 DESIGN 5.2.1 모양(`llm.active`, `llm.providers.<이름>.type`). 옛 키
  `llm.provider: ollama`도 읽는다. `providers.*.api_key_env`에 적힌 환경 변수 이름은 비밀값 목록에
  자동으로 들어가 로그·오류 문구에서 가려진다(값을 실제로 쓰는 공급자는 12단계).
- 환경 변수가 `.env`보다 우선한다(테스트·일회성 실행에서 덮어쓰기 쉽게).
- R5: 글 쓰는 AI(`llm.active`), AI마다 고른 모델(`llm.models`),
  「직접 입력」 주소(`llm.base_urls`)는
  프로그램 설정에서 읽는다. API 키는 AI마다 따로 암호화해 둔 것(`llm_keys/<이름>.bin`) >
  `.env`(`api_key_env`가 가리키는 이름, 개발용) 순서. 어느 쪽이든 키 값은 비밀값 목록에 들어가
  로그·오류 문구에서 가려진다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from app.analysis.validator import parse_extra_patterns
from app.user_settings import Protector, UserStore, apply_overlay, typing_speed_of

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DB_PATH = ROOT / "data" / "app.sqlite3"

SECRET_ENV_NAMES = ("YOUTUBE_API_KEY",)
# R5: API 키를 쓰는 AI 종류(app/llm/registry.py와 같은 이름). 키는 AI마다 따로 저장한다
LLM_KEY_TYPES = ("openai_compatible", "anthropic")
DEFAULT_CONTEXT_CHARS = 6000
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
# D3(5단계 끝): 초안 비교에서 3번 안 통과율이 가장 높은 모델(docs/MODEL_EVAL.md).
# 대표가 초안을 읽고 .env의 OLLAMA_MODEL로 바꿀 수 있다
DEFAULT_OLLAMA_MODEL = "qwen3.8:27b"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# D4 기본값(PLAYBOOK 2절): 대표가 정하지 않으면 이 한 줄만 운명원에 대한 사실로 쓴다
DEFAULT_BRAND_FACTS = ("운명원은 연애 사주 상담을 하는 곳이다",)
# 7단계: 과제 설정 예시의 프로필 이름(화면 이름. 폴더 이름은 profile-1… — app/ops/profiles.py)
DEFAULT_PROFILES = ("유튜브1", "유튜브2", "유튜브3")
POST_TARGETS = ("sandbox", "youtube")  # 게시 대상: 통제된 테스트 페이지 / 실제 유튜브(사람이 게시)
# 8단계: 브라우저 연결(DESIGN 6.3). 창 위치 기본은 2번 모니터(AGENTS.md 창 규칙)
DEFAULT_WINDOW_POSITION = (60, -1060)
DEFAULT_TYPING_DELAY_MS = (60, 160)
PROFILES_DIR_ENV = "JG_PROFILES_DIR"  # 프로필 폴더 위치를 바꿀 때(테스트·다른 PC). 비우면 아래 기본


def default_profiles_root(environ: dict[str, str] | None = None) -> Path:
    """`%LOCALAPPDATA%/JGMarketingAgent/profiles`. 저장소 안에 두지 않는다(DESIGN 6.3)."""
    env = os.environ if environ is None else environ
    base = _clean(env.get("LOCALAPPDATA")) or str(Path.home() / "AppData" / "Local")
    return Path(base) / "JGMarketingAgent" / "profiles"


@dataclass(frozen=True)
class BrowserSettings:
    """`browser` 절(8단계). 창은 기본으로 보이게(headless 거짓) 띄우고 위치는 2번 모니터."""

    headless: bool = False
    window_position: tuple[int, int] = DEFAULT_WINDOW_POSITION
    typing_delay_ms: tuple[int, int] = DEFAULT_TYPING_DELAY_MS
    chrome_path: str | None = None  # 비우면 설치된 크롬을 찾는다(app/browser/chrome.py)
    profiles_root: Path = field(default_factory=default_profiles_root)
    # 실패한 작업의 화면 캡처(`<작업ID>.png`). 저장소 안이지만 .gitignore가 막는다
    screenshot_dir: Path = ROOT / "error_screenshots"


@dataclass(frozen=True)
class DiscoverSettings:
    query: str = "연애 고민"
    max_results: int = 12
    exclude_shorts: bool = True  # 검색 결과에서 쇼츠(아래 길이 미만·길이 없음)를 뺀다
    # R2: 쇼츠로 볼 길이(초). 이보다 짧은 영상을 쇼츠로 본다. 유튜브 쇼츠는 3분까지라 181(3분 이하)
    shorts_under_seconds: int = 181


@dataclass(frozen=True)
class RisingSettings:
    """`rising` 절(R4, 가점): 뜨기 직전 영상. 조회수 범위와 시간당 조회수 하한."""

    query: str = "연애"
    min_views: int = 1000
    max_views: int = 5000
    min_views_per_hour: int = 150


@dataclass(frozen=True)
class ProviderSettings:
    """`llm.providers.<이름>` 한 항목. `options`는 type·api_key_env를 뺀 나머지 원본."""

    name: str
    type: str
    api_key_env: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMSettings:
    active: str = "ollama"
    providers: dict[str, ProviderSettings] = field(
        default_factory=lambda: {"ollama": ProviderSettings("ollama", "ollama")}
    )
    timeout_seconds: float = 180.0
    # R4: 모델이 아직 메모리에 없을 때(처음 불러올 때) 그 요청만 기다리는 시간과,
    # 프로그램을 켤 때 미리 불러 둘지
    cold_timeout_seconds: float = 420.0
    warmup_on_start: bool = True
    num_ctx: int = 8192
    keep_alive: str = "30m"
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    # R5: 프로그램 설정에서 고른 AI별 모델·주소, AI별 API 키와 그 출처(program | dev_file)
    models: dict[str, str] = field(default_factory=dict)
    base_urls: dict[str, str] = field(default_factory=dict)
    api_keys: dict[str, str] = field(default_factory=dict, repr=False)
    key_sources: dict[str, str] = field(default_factory=dict)

    @property
    def active_provider(self) -> ProviderSettings | None:
        return self.providers.get(self.active)

    def model_for(self, name: str) -> str:
        """그 AI에 쓸 모델: 프로그램에서 고른 것 > config.yaml의 model > 빈 글(고르지 않음).

        Ollama는 따로(`ollama_model`: 고른 모델 > .env의 OLLAMA_MODEL > 코드 기본값)."""
        provider = self.providers.get(name)
        if provider is not None and provider.type == "ollama":
            return str(provider.options.get("model") or self.ollama_model)
        chosen = (self.models.get(name) or "").strip()
        if chosen:
            return chosen
        return str((provider.options.get("model") if provider else "") or "").strip()

    def base_url_for(self, name: str) -> str:
        provider = self.providers.get(name)
        chosen = (self.base_urls.get(name) or "").strip()
        if chosen and provider is not None and provider.options.get("editable_url"):
            return chosen
        return str((provider.options.get("base_url") if provider else "") or "").strip()

    @property
    def secret_env_names(self) -> tuple[str, ...]:
        return tuple(p.api_key_env for p in self.providers.values() if p.api_key_env)


@dataclass(frozen=True)
class Settings:
    """앱 전체가 쓰는 설정. `rules`는 config.yaml 원본(dict)이다."""

    discover: DiscoverSettings
    daily_max_comments: int
    rules: dict[str, Any] = field(repr=False)
    db_path: Path = DEFAULT_DB_PATH
    # R4: auto(자막 자동으로 읽기, 기본) | manual(직접 넣은 자막만).
    # 옛 값 unofficial은 오류로 알린다
    transcript_provider: str = "auto"
    transcript_timeout_seconds: float = 10.0
    rising: RisingSettings = field(default_factory=RisingSettings)
    context_chars: int = DEFAULT_CONTEXT_CHARS  # 모델에 넣을 영상 자료 길이 한도
    # 6단계: 규칙 검사. brand.facts에 적힌 문장만 운명원에 대한 사실로 쓴다(DESIGN 5.5)
    brand_facts: tuple[str, ...] = DEFAULT_BRAND_FACTS
    validator_extra_patterns: tuple[tuple[str, str], ...] = ()  # (V8|V9|V10, 정규식)
    youtube_api_key: str | None = field(default=None, repr=False)
    llm: LLMSettings = field(default_factory=LLMSettings)
    # providers.*.api_key_env로 이름이 적힌 환경 변수의 값(가리기 전용, 12단계 전까지 쓰지 않음)
    llm_secret_values: tuple[str, ...] = field(default=(), repr=False)
    # 7단계: 프로필 이름(순서가 곧 폴더 번호)과 기본 게시 방식(R3: 실제 게시 youtube가 기본,
    # 연습 모드는 sandbox. 옛 이름 assist도 youtube로 읽는다)
    profiles: tuple[str, ...] = DEFAULT_PROFILES
    default_target: str = "youtube"
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    # R2에서 저장, R3에서 동작에 쓴다: 광고 표기 기본값(초안의 「광고 표기 붙이기」 처음 상태)과
    # 게시 직전 확인(켜면 입력 뒤 [게시]를 한 번 더 눌러야 게시). 옛 키 own_video_ids는 읽지 않는다
    disclose_default: bool = True
    confirm_before_post: bool = False
    typing_speed: str = "normal"  # slow | normal | fast (browser.typing_delay_ms와 같은 뜻)
    window_screen: str | None = None  # 크롬 창을 띄울 모니터 ID(고른 적이 없으면 None)
    youtube_key_source: str | None = None  # program(프로그램에 저장) | dev_file(.env·환경 변수)
    user_values: dict[str, Any] = field(default_factory=dict, repr=False)  # 사용자가 바꾼 칸
    source: LoadSource | None = field(default=None, repr=False, compare=False)

    @property
    def youtube_key_configured(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def secret_env_names(self) -> tuple[str, ...]:
        """비밀값으로 다루는 환경 변수 이름들(고정 목록 + 설정의 api_key_env)."""
        names = list(SECRET_ENV_NAMES)
        names += [n for n in self.llm.secret_env_names if n not in names]
        return tuple(names)

    def secret_values(self) -> list[str]:
        """로그·오류 문구에서 가려야 할 값들."""
        return [v for v in (self.youtube_api_key, *self.llm_secret_values) if v]


@dataclass(frozen=True)
class LoadSource:
    """설정을 다시 읽을 때 쓰는 인자(저장 직후 바로 적용 — `reload_settings`)."""

    config_path: Path | None
    env_path: Path | None
    db_path: Path | None
    environ: dict[str, str] | None
    user_dir: Path | None
    protector: Protector | None

    def store(self) -> UserStore | None:
        return UserStore(self.user_dir, self.protector) if self.user_dir is not None else None


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"설정 파일이 없습니다: {path.name}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일 형식이 잘못됐습니다: {path.name}")
    return data


def _read_env(env_path: Path | None, environ: dict[str, str] | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_path is not None and env_path.exists():
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    values.update(os.environ if environ is None else environ)
    return values


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _brand_facts(brand: Any) -> tuple[str, ...]:
    """`brand.facts`(문장 목록). 항목이 없으면 D4 기본값 한 줄, 빈 목록이면 사실 없음."""
    if not isinstance(brand, dict) or "facts" not in brand:
        return DEFAULT_BRAND_FACTS
    raw = brand.get("facts")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("brand.facts는 문장 목록이어야 합니다.")
    return tuple(str(f).strip() for f in raw if str(f).strip())


def _profiles(raw: Any) -> tuple[str, ...]:
    """`profiles`(이름 목록). 없으면 과제 예시 세 개. 빈 이름·같은 이름은 켤 때 알린다."""
    if raw is None:
        return DEFAULT_PROFILES
    if not isinstance(raw, list) or not raw:
        raise ValueError("profiles는 이름 목록이어야 합니다(예: [유튜브1, 유튜브2, 유튜브3]).")
    names = tuple(str(n).strip() for n in raw)
    if any(not n for n in names):
        raise ValueError("profiles에 빈 이름이 있습니다.")
    if len(set(names)) != len(names):
        raise ValueError("profiles에 같은 이름이 두 번 있습니다.")
    return names


def _default_target(browser: Any) -> str:
    """`browser.default_target`: youtube(실제 게시, 기본) | sandbox(연습 모드).

    옛 이름 assist·youtube_auto도 실제 게시(youtube)로 읽는다."""
    raw = str((browser or {}).get("default_target") or "youtube").strip().lower()
    target = {"assist": "youtube", "youtube_auto": "youtube"}.get(raw, raw)
    if target not in POST_TARGETS:
        raise ValueError("browser.default_target은 youtube 또는 sandbox여야 합니다.")
    return target


def _window_position(raw: Any) -> tuple[int, int]:
    """`"60,-1060"` 또는 `[60, -1060]` → (60, -1060)."""
    if raw is None or raw == "":
        return DEFAULT_WINDOW_POSITION
    parts = raw.split(",") if isinstance(raw, str) else raw
    try:
        x, y = (int(str(v).strip()) for v in parts)
    except (TypeError, ValueError):
        raise ValueError(
            'browser.window_position은 "x,y" 모양이어야 합니다(예: "60,-1060").'
        ) from None
    return x, y


def _typing_delay(raw: Any) -> tuple[int, int]:
    """`[60, 160]`(글자마다 기다리는 밀리초의 최소·최대). 숫자 하나면 고정."""
    if raw is None:
        return DEFAULT_TYPING_DELAY_MS
    values = raw if isinstance(raw, list) else [raw]
    try:
        nums = [int(v) for v in values]
    except (TypeError, ValueError):
        raise ValueError("browser.typing_delay_ms는 [최소, 최대] 밀리초여야 합니다.") from None
    if len(nums) == 1:
        nums = nums * 2
    if len(nums) != 2 or nums[0] < 0 or nums[1] < nums[0] or nums[1] > 5000:
        raise ValueError("browser.typing_delay_ms는 [최소, 최대] 밀리초여야 합니다(0~5000).")
    return nums[0], nums[1]


def _browser_settings(raw: Any, env: dict[str, str]) -> BrowserSettings:
    raw = raw if isinstance(raw, dict) else {}
    headless = raw.get("headless", False)
    if not isinstance(headless, bool):
        raise ValueError("browser.headless는 true 또는 false여야 합니다.")
    root = _clean(env.get(PROFILES_DIR_ENV))
    return BrowserSettings(
        headless=headless,
        window_position=_window_position(raw.get("window_position")),
        typing_delay_ms=_typing_delay(raw.get("typing_delay_ms")),
        chrome_path=_clean(str(raw.get("chrome_path") or "")),
        profiles_root=Path(root) if root else default_profiles_root(env),
        screenshot_dir=Path(str(raw["screenshot_dir"]))
        if raw.get("screenshot_dir")
        else BrowserSettings.screenshot_dir,
    )


def _llm_settings(raw: Any, env: dict[str, str]) -> LLMSettings:
    """`llm` 절을 읽는다. 옛 모양 `llm.provider: ollama`는 `active: ollama`로 본다.

    `providers`에 아직 구현하지 않은 종류가 있어도 여기서는 막지 않는다(고른 것만
    `app/llm/registry.py`가 확인한다). 모양이 틀린 항목은 앱을 켤 때 한국어 오류로 알린다.
    """
    raw = raw if isinstance(raw, dict) else {}
    active = _clean(str(raw.get("active") or raw.get("provider") or "")) or "ollama"
    providers_raw = raw.get("providers")
    if providers_raw is None:
        providers_raw = {active: {"type": active}}  # 옛 설정: 이름이 곧 종류
    if not isinstance(providers_raw, dict):
        raise ValueError("llm.providers는 '이름: {type: ...}' 모양이어야 합니다.")
    providers: dict[str, ProviderSettings] = {}
    for name, item in providers_raw.items():
        name = str(name)
        if not isinstance(item, dict) or not _clean(str(item.get("type") or "")):
            raise ValueError(f"llm.providers.{name}에 type이 없습니다(예: {{type: ollama}}).")
        key_env = _clean(str(item.get("api_key_env") or "")) if item.get("api_key_env") else None
        if key_env is not None and not _ENV_NAME.match(key_env):
            raise ValueError(
                f"llm.providers.{name}.api_key_env에는 환경 변수 이름만 적습니다(키 값은 .env에)."
            )
        options = {k: v for k, v in item.items() if k not in ("type", "api_key_env")}
        providers[name] = ProviderSettings(
            name=name,
            type=str(item["type"]).strip().lower(),
            api_key_env=key_env,
            options=options,
        )
    return LLMSettings(
        active=active,
        providers=providers,
        timeout_seconds=float(raw.get("timeout_seconds") or LLMSettings.timeout_seconds),
        cold_timeout_seconds=float(
            raw.get("cold_timeout_seconds") or LLMSettings.cold_timeout_seconds
        ),
        warmup_on_start=_flag(raw.get("warmup_on_start", True), "llm.warmup_on_start"),
        num_ctx=int(raw.get("num_ctx") or LLMSettings.num_ctx),
        keep_alive=str(raw.get("keep_alive") or LLMSettings.keep_alive),
        ollama_base_url=_clean(env.get("OLLAMA_BASE_URL")) or DEFAULT_OLLAMA_BASE_URL,
        ollama_model=_clean(env.get("OLLAMA_MODEL")) or DEFAULT_OLLAMA_MODEL,
    )


def load_settings(
    config_path: Path | None = None,
    env_path: Path | None = DEFAULT_ENV_PATH,
    *,
    db_path: Path | None = None,
    environ: dict[str, str] | None = None,
    user_dir: Path | None = None,
    protector: Protector | None = None,
    use_user: bool = True,
    user_values: dict[str, Any] | None = None,
) -> Settings:
    """설정을 읽는다. `env_path=None`이면 `.env` 파일을 읽지 않는다.

    `user_dir`를 주면 그 폴더의 사용자 설정과 저장한 키를 먼저 쓴다. `use_user=False`면
    폴더는 기억하되 값은 읽지 않는다(기본값 보기). `user_values`를 주면 파일 대신 그 값으로 읽는다
    (저장하기 전에 새 값으로 설정이 제대로 읽히는지 미리 볼 때).
    """
    source = LoadSource(
        config_path, env_path, db_path, dict(environ) if environ is not None else None,
        Path(user_dir) if user_dir is not None else None, protector,
    )
    base_rules = _read_yaml(config_path or DEFAULT_CONFIG_PATH)
    env = _read_env(env_path, environ)
    store = source.store() if use_user else None
    if user_values is None:
        user_values = store.read_values() if store is not None else {}
    rules = apply_overlay(base_rules, user_values)

    discover_raw = rules.get("discover") or {}
    discover = DiscoverSettings(
        query=str(discover_raw.get("query") or DiscoverSettings.query),
        max_results=int(discover_raw.get("max_results") or DiscoverSettings.max_results),
        exclude_shorts=bool(discover_raw.get("exclude_shorts", DiscoverSettings.exclude_shorts)),
        shorts_under_seconds=int(
            discover_raw.get("shorts_under_seconds") or DiscoverSettings.shorts_under_seconds
        ),
    )
    limits = rules.get("limits") or {}
    transcript = rules.get("transcript") or {}
    llm = rules.get("llm") or {}
    validator = rules.get("validator") or {}

    llm_settings = _llm_settings(llm, env)
    chosen_model = _clean(str(user_values.get("llm.model") or ""))
    if chosen_model:  # 프로그램에서 고른 모델이 .env의 OLLAMA_MODEL보다 먼저
        llm_settings = replace(llm_settings, ollama_model=chosen_model)
    llm_settings = _llm_user_values(llm_settings, user_values, env, store)
    llm_secrets = tuple(
        dict.fromkeys(
            [v for v in (_clean(env.get(n)) for n in llm_settings.secret_env_names) if v]
            + [v for v in llm_settings.api_keys.values() if v]
        )
    )

    if db_path is None:
        env_db = _clean(env.get("APP_DB_PATH"))
        db_path = Path(env_db) if env_db else DEFAULT_DB_PATH

    stored_key = store.read_key() if store is not None else None
    env_key = _clean(env.get("YOUTUBE_API_KEY"))
    youtube_key = stored_key or env_key
    key_source = "program" if stored_key else ("dev_file" if env_key else None)
    comment = rules.get("comment") or {}
    posting = rules.get("posting") or {}
    browser = _browser_settings(rules.get("browser"), env)
    window_screen = _clean(str((rules.get("browser") or {}).get("window_screen") or ""))

    return Settings(
        discover=discover,
        daily_max_comments=int(limits.get("daily_max_comments", 10)),
        rules=rules,
        db_path=db_path,
        transcript_provider=_transcript_provider(transcript),
        transcript_timeout_seconds=float(transcript.get("timeout_seconds") or 10.0),
        rising=_rising_settings(rules.get("rising")),
        context_chars=int(llm.get("context_chars") or DEFAULT_CONTEXT_CHARS),
        brand_facts=_brand_facts(rules.get("brand")),
        validator_extra_patterns=parse_extra_patterns(validator.get("extra_patterns")),
        youtube_api_key=youtube_key,
        llm=llm_settings,
        llm_secret_values=llm_secrets,
        profiles=_profiles(rules.get("profiles")),
        default_target=_default_target(rules.get("browser")),
        browser=browser,
        disclose_default=_flag(comment.get("disclose_default", True), "comment.disclose_default"),
        confirm_before_post=_flag(
            posting.get("confirm_before_post", False), "posting.confirm_before_post"
        ),
        typing_speed=typing_speed_of(browser.typing_delay_ms),
        window_screen=window_screen,
        youtube_key_source=key_source,
        user_values=user_values,
        source=source,
    )


def _llm_user_values(
    llm: LLMSettings, user_values: dict[str, Any], env: dict[str, str], store: UserStore | None
) -> LLMSettings:
    """R5: AI별 모델·주소와 키. 키는 프로그램에 저장한 것 > .env(개발용)."""
    models_raw = user_values.get("llm.models")
    urls_raw = user_values.get("llm.base_urls")
    models = {
        str(k): str(v).strip()
        for k, v in (models_raw.items() if isinstance(models_raw, dict) else [])
        if k in llm.providers and str(v).strip()
    }
    urls = {
        str(k): str(v).strip()
        for k, v in (urls_raw.items() if isinstance(urls_raw, dict) else [])
        if k in llm.providers and str(v).strip()
    }
    keys: dict[str, str] = {}
    sources: dict[str, str] = {}
    for name, provider in llm.providers.items():
        if provider.type not in LLM_KEY_TYPES:
            continue
        stored = store.read_llm_key(name) if store is not None else None
        env_key = _clean(env.get(provider.api_key_env)) if provider.api_key_env else None
        if stored:
            keys[name], sources[name] = stored, "program"
        elif env_key:
            keys[name], sources[name] = env_key, "dev_file"
    return replace(llm, models=models, base_urls=urls, api_keys=keys, key_sources=sources)


def _transcript_provider(raw: Any) -> str:
    """`transcript.provider`(auto | manual)와 설정 화면의 「자막 자동으로 읽기」(`transcript.auto`).

    켬/끔을 저장했으면 그것이 먼저다(auto ↔ manual). 그 밖의 값(옛 unofficial 등)은 그대로 두어
    맥락을 만들 때 알기 쉬운 오류로 알린다.
    """
    raw = raw if isinstance(raw, dict) else {}
    provider = str(raw.get("provider") or "auto").strip().lower()
    flag = raw.get("auto")
    if isinstance(flag, bool) and provider in ("auto", "manual"):
        provider = "auto" if flag else "manual"
    return provider


def _rising_settings(raw: Any) -> RisingSettings:
    raw = raw if isinstance(raw, dict) else {}
    out = RisingSettings(
        query=str(raw.get("query") or RisingSettings.query).strip() or RisingSettings.query,
        min_views=int(raw.get("min_views", RisingSettings.min_views)),
        max_views=int(raw.get("max_views", RisingSettings.max_views)),
        min_views_per_hour=int(raw.get("min_views_per_hour", RisingSettings.min_views_per_hour)),
    )
    if out.min_views < 0 or out.max_views < out.min_views or out.min_views_per_hour < 0:
        raise ValueError("rising의 조회수 범위가 잘못됐습니다(0 ≤ min_views ≤ max_views).")
    return out


def _flag(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name}는 true 또는 false여야 합니다.")
    return value


def reload_settings(settings: Settings, *, use_user: bool = True) -> Settings:
    """같은 인자로 설정을 다시 읽는다(저장 직후 바로 적용). 인자를 모르면 기본으로 읽는다."""
    src = settings.source
    if src is None:
        return load_settings()
    return load_settings(
        src.config_path, src.env_path, db_path=src.db_path, environ=src.environ,
        user_dir=src.user_dir, protector=src.protector, use_user=use_user,
    )
