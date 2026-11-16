"""설정 읽기: 비밀값은 `.env`(또는 환경 변수), 규칙은 `config.yaml`.

- 키가 없어도 앱은 뜬다. YouTube를 부를 때 `missing_key` 오류로 알려 준다.
- 키 값은 `repr`·로그에 나오지 않는다. 쓰는 곳은 `app/youtube/client.py` 하나다.
- 4단계: LLM 설정은 DESIGN 5.2.1 모양(`llm.active`, `llm.providers.<이름>.type`). 옛 키
  `llm.provider: ollama`도 읽는다. `providers.*.api_key_env`에 적힌 환경 변수 이름은 비밀값 목록에
  자동으로 들어가 로그·오류 문구에서 가려진다(값을 실제로 쓰는 공급자는 12단계).
- 환경 변수가 `.env`보다 우선한다(테스트·일회성 실행에서 덮어쓰기 쉽게).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from app.analysis.validator import parse_extra_patterns

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DB_PATH = ROOT / "data" / "app.sqlite3"

SECRET_ENV_NAMES = ("YOUTUBE_API_KEY",)
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
    exclude_shorts: bool = True  # 검색 결과에서 쇼츠(61초 미만·길이 없음)를 뺀다


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
    num_ctx: int = 8192
    keep_alive: str = "30m"
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL

    @property
    def active_provider(self) -> ProviderSettings | None:
        return self.providers.get(self.active)

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
    transcript_provider: str = "manual"  # manual | unofficial (D1 기본: manual만)
    context_chars: int = DEFAULT_CONTEXT_CHARS  # 모델에 넣을 영상 자료 길이 한도
    # 6단계: 규칙 검사. brand.facts에 적힌 문장만 운명원에 대한 사실로 쓴다(DESIGN 5.5)
    brand_facts: tuple[str, ...] = DEFAULT_BRAND_FACTS
    validator_extra_patterns: tuple[tuple[str, str], ...] = ()  # (V8|V9|V10, 정규식)
    youtube_api_key: str | None = field(default=None, repr=False)
    llm: LLMSettings = field(default_factory=LLMSettings)
    # providers.*.api_key_env로 이름이 적힌 환경 변수의 값(가리기 전용, 12단계 전까지 쓰지 않음)
    llm_secret_values: tuple[str, ...] = field(default=(), repr=False)
    # 7단계: 프로필 이름(순서가 곧 폴더 번호)과 기본 게시 대상(default_target: assist → youtube)
    profiles: tuple[str, ...] = DEFAULT_PROFILES
    default_target: str = "sandbox"
    browser: BrowserSettings = field(default_factory=BrowserSettings)

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
    """`browser.default_target`: sandbox | assist(실제 유튜브, 게시 기록의 대상 이름은 youtube)."""
    raw = str((browser or {}).get("default_target") or "sandbox").strip().lower()
    target = {"assist": "youtube"}.get(raw, raw)
    if target not in POST_TARGETS:
        raise ValueError("browser.default_target은 sandbox 또는 assist여야 합니다.")
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
) -> Settings:
    """설정을 읽는다. `env_path=None`이면 `.env` 파일을 읽지 않는다."""
    rules = _read_yaml(config_path or DEFAULT_CONFIG_PATH)
    env = _read_env(env_path, environ)

    discover_raw = rules.get("discover") or {}
    discover = DiscoverSettings(
        query=str(discover_raw.get("query") or DiscoverSettings.query),
        max_results=int(discover_raw.get("max_results") or DiscoverSettings.max_results),
        exclude_shorts=bool(discover_raw.get("exclude_shorts", DiscoverSettings.exclude_shorts)),
    )
    limits = rules.get("limits") or {}
    transcript = rules.get("transcript") or {}
    llm = rules.get("llm") or {}
    validator = rules.get("validator") or {}

    llm_settings = _llm_settings(llm, env)
    llm_secrets = tuple(
        v for v in (_clean(env.get(n)) for n in llm_settings.secret_env_names) if v
    )

    if db_path is None:
        env_db = _clean(env.get("APP_DB_PATH"))
        db_path = Path(env_db) if env_db else DEFAULT_DB_PATH

    return Settings(
        discover=discover,
        daily_max_comments=int(limits.get("daily_max_comments", 10)),
        rules=rules,
        db_path=db_path,
        transcript_provider=str(transcript.get("provider") or "manual").strip().lower(),
        context_chars=int(llm.get("context_chars") or DEFAULT_CONTEXT_CHARS),
        brand_facts=_brand_facts(rules.get("brand")),
        validator_extra_patterns=parse_extra_patterns(validator.get("extra_patterns")),
        youtube_api_key=_clean(env.get("YOUTUBE_API_KEY")),
        llm=llm_settings,
        llm_secret_values=llm_secrets,
        profiles=_profiles(rules.get("profiles")),
        default_target=_default_target(rules.get("browser")),
        browser=_browser_settings(rules.get("browser"), env),
    )
