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
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"  # 모델 확정은 5단계 끝(D3). 그때까지 가장 가벼운 일반 모델
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# D4 기본값(PLAYBOOK 2절): 대표가 정하지 않으면 이 한 줄만 운명원에 대한 사실로 쓴다
DEFAULT_BRAND_FACTS = ("운명원은 연애 사주 상담을 하는 곳이다",)


@dataclass(frozen=True)
class DiscoverSettings:
    query: str = "연애 고민"
    max_results: int = 12


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
    )
