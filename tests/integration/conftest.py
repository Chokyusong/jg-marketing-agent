"""통합 테스트 도우미: 가짜 키, YouTube 가짜 응답, 임시 DB로 만든 앱."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from yt_helpers import Clock, make_fake_key

from app.config import load_settings
from app.main import create_app


@pytest.fixture
def fake_key() -> str:
    return make_fake_key()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_settings(tmp_db_path: Path, make_config) -> Callable[..., Any]:
    def _make(key: str | None, overrides: dict[str, Any] | None = None):
        environ = {"YOUTUBE_API_KEY": key} if key else {}
        return load_settings(
            make_config(overrides), env_path=None, db_path=tmp_db_path, environ=environ
        )

    return _make


@pytest.fixture
def make_client(make_settings, clock) -> Callable[..., TestClient]:
    """사용: client = make_client(mock, key=fake_key)"""

    def _make(mock=None, *, key: str | None = None, overrides=None) -> TestClient:
        settings = make_settings(key, overrides)
        app = create_app(settings, transport=mock.transport if mock else None, clock=clock)
        return TestClient(app)

    return _make

