"""e2e 도우미(8단계): 임시 포트로 앱 서버를 띄우고,
창 없는(headless) 설치된 크롬으로 테스트 페이지를 돌린다.

- 크롬이나 Playwright가 없으면 건너뛴다(자동 테스트는 크롬 없이도 통과해야 한다).
- 창을 띄우지 않는다(`browser.headless: true`). 주 모니터에 창이 뜨지 않는다.
- 프로필 폴더·DB·화면 캡처는 모두 임시 폴더. 이 PC의 %LOCALAPPDATA% 프로필을 건드리지 않는다.
- 실제 유튜브는 열지 않는다. 열리는 주소는 이 서버의 `/sandbox/`뿐이다(테스트가 확인한다).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import db
from app.browser.chrome import find_chrome
from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app


def _chrome() -> Path | None:
    return find_chrome()


def pytest_collection_modifyitems(config, items):
    if importlib.util.find_spec("playwright") is None:
        return  # 최상위 conftest가 이미 건너뛴다
    if _chrome() is None:
        skip = pytest.mark.skip(reason="e2e 테스트: 설치된 Google Chrome을 찾지 못함")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)


@dataclass
class LiveApp:
    base: str
    http: httpx.Client
    services: Any
    drivers: list
    db_path: Path
    profiles_root: Path
    shots: Path

    def add_approved_draft(self, video_id: str, body: str | None = None) -> tuple[int, str]:
        """영상과 승인한 초안 한 개(LLM 없이 표에 바로 넣는다)."""
        now = "2026-11-16T03:00:00+00:00"
        body = body or (f"[광고] {video_id} 영상 첫 장면 이야기에 공감해요. "
                        "운명원 잘 본다던데 한번 보고 싶어요.")
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
                "VALUES (?, ?, ?, 'search')",
                (video_id, f"테스트 영상 제목 {video_id}", now),
            )
            cur = conn.execute(
                "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
                "updated_at, approved_at) VALUES (?, ?, '{}', 1, 'approved', ?, ?, ?)",
                (video_id, body, now, now, now),
            )
            return int(cur.lastrowid), body


@pytest.fixture
def live_app(tmp_path, make_config) -> Iterator[LiveApp]:
    db_path = tmp_path / "e2e.sqlite3"
    profiles_root = tmp_path / "profiles"
    shots = tmp_path / "error_screenshots"
    config = make_config(
        {
            "limits": {"daily_max_comments": 10},
            # R3부터 기본은 [댓글 달기] 한 번으로 끝까지. 이 도우미의 시험은 [게시] 단계를 본다
            "posting": {"confirm_before_post": True},
            "browser": {
                "headless": True,  # 창 없이(주 모니터에 창을 띄우지 않는다)
                "typing_delay_ms": [5, 15],
                "screenshot_dir": str(shots),
            },
        }
    )
    settings = load_settings(
        config, env_path=None, db_path=db_path, environ={"JG_PROFILES_DIR": str(profiles_root)}
    )
    drivers: list = []

    def factory(browser_settings):
        driver = default_driver_factory(browser_settings)
        drivers.append(driver)
        return driver

    app = create_app(settings, browser_hooks=BrowserHooks(driver_factory=factory))
    server = ServerThread(app, open_listen_socket())
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
    http = httpx.Client(base_url=base, timeout=30, trust_env=False)
    services = app.state.services.get()
    try:
        yield LiveApp(base, http, services, drivers, db_path, profiles_root, shots)
    finally:
        services.jobs.shutdown(timeout=15)
        http.close()
        server.stop()
