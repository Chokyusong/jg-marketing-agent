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
    launcher: Callable[[Any], Any] | None = None  # 인자 목록 -> 프로세스
    playwright_ready: Callable[[], bool] | None = None
    verify_comment: Callable[[str, str], bool | None] | None = None
    approval_timeout: float | None = None
    confirm_timeout: float | None = None
    # 9단계: 모니터 목록 읽기(창 위치 확인). 비우면 Windows API(app/browser/screens.read_monitors)
    screens: Callable[[], Any] | None = None
