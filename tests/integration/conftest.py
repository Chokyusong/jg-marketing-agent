"""통합 테스트 도우미: 가짜 키, YouTube 가짜 응답, 임시 DB로 만든 앱."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from yt_helpers import Clock, make_fake_key

from app.config import load_settings
from app.main import create_app
from app.user_settings import Protector


def _fake_protect(data: bytes) -> bytes:
    """가짜 암호화(테스트용): 글자를 뒤집고 바이트를 바꾼다. 평문이 그대로 남지 않는다."""
    return b"FAKE1" + bytes(b ^ 0x5A for b in reversed(data))


def _fake_unprotect(blob: bytes) -> bytes:
    assert blob.startswith(b"FAKE1")
    return bytes(b ^ 0x5A for b in blob[5:])[::-1]


FAKE_PROTECTOR = Protector(protect=_fake_protect, unprotect=_fake_unprotect)


@pytest.fixture
def user_dir(tmp_path: Path) -> Path:
    """R2: 사용자 설정 폴더(이 PC의 %LOCALAPPDATA%를 건드리지 않게 임시 폴더)."""
    return tmp_path / "user"


@pytest.fixture
def protector() -> Protector:
    return FAKE_PROTECTOR


@pytest.fixture
def fake_key() -> str:
    return make_fake_key()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_settings(
    tmp_db_path: Path, tmp_path: Path, make_config, user_dir, protector
) -> Callable[..., Any]:
    """8단계: 프로필 폴더와 화면 캡처는 임시 폴더로(이 PC의 %LOCALAPPDATA%를 건드리지 않게).

    R2: 사용자 설정 폴더도 임시 폴더, 키 암호화는 가짜(`protector` 고정값으로 바꿀 수 있다).
    """

    def _make(key: str | None, overrides: dict[str, Any] | None = None):
        environ = {"YOUTUBE_API_KEY": key} if key else {}
        environ["JG_PROFILES_DIR"] = str(tmp_path / "profiles")
        merged = dict(overrides or {})
        browser = dict(merged.get("browser") or {})
        browser.setdefault("screenshot_dir", str(tmp_path / "error_screenshots"))
        merged["browser"] = browser
        return load_settings(
            make_config(merged), env_path=None, db_path=tmp_db_path, environ=environ,
            user_dir=user_dir, protector=protector,
        )

    return _make


def _ollama_off(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Ollama 꺼짐(테스트 기본값)", request=request)


OLLAMA_OFF = httpx.MockTransport(_ollama_off)


@pytest.fixture
def make_client(make_settings, clock) -> Callable[..., TestClient]:
    """사용: client = make_client(mock, key=fake_key)

    LLM(Ollama) 호출은 따로 `llm=`로 준다(`MockHTTP`). 주지 않으면 「Ollama 꺼짐」으로 본다 —
    자동 테스트가 이 PC의 진짜 Ollama를 부르지 않게.
    """

    def _make(
        mock=None, *, key: str | None = None, overrides=None, llm=None, browser_hooks=None,
        on_build=None,
    ) -> TestClient:
        settings = make_settings(key, overrides)
        app = create_app(
            settings,
            transport=mock.transport if mock else None,
            llm_transport=llm.transport if llm else OLLAMA_OFF,
            clock=clock,
            browser_hooks=browser_hooks,
            on_build=on_build,
        )
        return TestClient(app)

    return _make

