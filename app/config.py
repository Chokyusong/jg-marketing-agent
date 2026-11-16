"""설정 읽기: 비밀값은 `.env`(또는 환경 변수), 규칙은 `config.yaml`.

- 키가 없어도 앱은 뜬다. YouTube를 부를 때 `missing_key` 오류로 알려 준다.
- 키 값은 `repr`·로그에 나오지 않는다. 쓰는 곳은 `app/youtube/client.py` 하나다.
- 환경 변수가 `.env`보다 우선한다(테스트·일회성 실행에서 덮어쓰기 쉽게).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DB_PATH = ROOT / "data" / "app.sqlite3"

SECRET_ENV_NAMES = ("YOUTUBE_API_KEY",)
DEFAULT_CONTEXT_CHARS = 6000


@dataclass(frozen=True)
class DiscoverSettings:
    query: str = "연애 고민"
    max_results: int = 12


@dataclass(frozen=True)
class Settings:
    """앱 전체가 쓰는 설정. `rules`는 config.yaml 원본(dict)이다."""

    discover: DiscoverSettings
    daily_max_comments: int
    rules: dict[str, Any] = field(repr=False)
    db_path: Path = DEFAULT_DB_PATH
    transcript_provider: str = "manual"  # manual | unofficial (D1 기본: manual만)
    context_chars: int = DEFAULT_CONTEXT_CHARS  # 모델에 넣을 영상 자료 길이 한도
    youtube_api_key: str | None = field(default=None, repr=False)

    @property
    def youtube_key_configured(self) -> bool:
        return bool(self.youtube_api_key)

    def secret_values(self) -> list[str]:
        """로그·오류 문구에서 가려야 할 값들."""
        return [v for v in (self.youtube_api_key,) if v]


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
        youtube_api_key=_clean(env.get("YOUTUBE_API_KEY")),
    )
