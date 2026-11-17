"""브라우저 연결의 바깥 호출을 바꿔 끼우는 자리(8단계).

테스트는 가짜 크롬 실행·가짜 실행기를 넣는다.

비워 두면(None) 실제 것을 쓴다: 설치된 크롬 찾기, Playwright 실행기, `subprocess.Popen`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrowserHooks:
    chrome_finder: Callable[[], Path | None] | None = None
    driver_factory: Callable[[Any], Any] | None = None  # BrowserSettings -> BrowserDriver
    # 실제 게시(R3, 어떤 영상이든): (BrowserSettings, 이번 작업의 영상 ID) -> BrowserDriver
    youtube_driver_factory: Callable[[Any, str], Any] | None = None
    launcher: Callable[[Any], Any] | None = None  # 인자 목록 -> 프로세스(로그인 창 열기)
    playwright_ready: Callable[[], bool] | None = None
    verify_comment: Callable[[str, str], bool | None] | None = None
    approval_timeout: float | None = None  # 게시 직전 확인(켬)에서 [게시]를 기다리는 시간
    # 9단계: 모니터 목록 읽기(창 위치 확인). 비우면 Windows API(app/browser/screens.read_monitors)
    screens: Callable[[], Any] | None = None
    # 2026-11-17 창 위치 자동: 프로그램 창이 있는 모니터(모니터 목록 -> Monitor 또는 None).
    # 비우면 Windows API(app/browser/screens.app_window_monitor). 테스트는 None을 돌려 「모름」
    app_monitor: Callable[[Any], Any] | None = None
    # R2: 프로필 로그인 확인(프로필 폴더 -> LoginResult). 비우면 창 없는 크롬으로 유튜브를 읽는다
    login_checker: Callable[[Path], Any] | None = None
