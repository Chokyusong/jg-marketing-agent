"""로그인된 프로그램의 [로그인하기](2026-11-17, 아무 PC에서나 AI 연결).

설치는 돼 있는데 로그인이 안 된 프로그램(Codex · Claude Code)에 [로그인하기]를 누르면, 그 프로그램의
**자기 로그인 명령**을 보이는 명령 창으로 연다. 로그인은 사람이 그 창에서 한다.

- 셸 없이 인자 목록으로 연다(`shell=False`, 명령 글을 이어 붙이지 않는다). 실행 파일은 PATH에서
  찾은 전체 경로다. Windows에서는 새 명령 창(`CREATE_NEW_CONSOLE`)이라 사람이 보고 입력할 수 있다.
- 이 앱의 비밀값 환경 변수(API 키)는 그 창에 넘기지 않는다(`CLIClient.child_env`).
- 그 프로그램이 저장하는 로그인 정보(토큰 파일)는 **읽지 않는다.** 창이 닫히면 그 프로그램의
  로그인 상태 명령(`codex login status`, `claude auth status`)으로 한 번 저절로 묻는다
  (종료 코드 0 = 로그인됨).
- 자동 테스트는 `tests/conftest.py`가 `default_launcher`를 막는다(진짜 로그인 명령을 실행하지
  않는다).

로그인 명령(이 PC의 `--help`로 확인, 2026-11-17):
- Codex 0.152.1 `codex login --help` — 「Manage login」, 하위 명령 없이 실행하면 로그인을 시작한다.
- Claude Code 2.1.312 `claude auth login --help` — 「Sign in to your Anthropic account」
  (`--claudeai` 구독이 기본).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.browser.login import LoginWindows

log = logging.getLogger(__name__)

# 프로그램 → 그 프로그램의 로그인 명령(실행 파일 뒤에 붙는 인자). 여기 없는 프로그램은 열지 않는다
LOGIN_COMMANDS: dict[str, tuple[str, ...]] = {
    "codex": ("login",),
    "claude": ("auth", "login"),
}
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform == "win32" else 0


def login_args(program: str, exe: str) -> list[str]:
    """[로그인하기]로 여는 명령의 인자 목록(첫 칸은 PATH에서 찾은 실행 파일)."""
    if program not in LOGIN_COMMANDS:
        raise ValueError(f"로그인 창을 열지 않는 프로그램: {program}")
    return [exe, *LOGIN_COMMANDS[program]]


Launcher = Callable[[list[str], dict[str, str]], Any]


def console_launcher(args: list[str], env: dict[str, str]) -> Any:  # pragma: no cover - 실제 창
    """보이는 새 명령 창으로 연다. 셸 없이 인자 목록."""
    return subprocess.Popen(  # noqa: S603 - 셸 없음, 실행 파일은 which로 찾은 전체 경로
        args,
        cwd=tempfile.gettempdir(),
        env=env,
        shell=False,
        creationflags=NEW_CONSOLE,
    )


# 모듈 기본값. 자동 테스트는 tests/conftest.py가 막는다
default_launcher: Launcher = console_launcher


@dataclass(frozen=True)
class LoginView:
    window_open: bool  # [로그인하기]로 연 창이 아직 열려 있는지
    checking: bool  # 창이 닫혀 로그인 상태를 저절로 묻는 중인지
    logged_in: bool | None  # 마지막으로 물어본 결과(모르면 None)


class CLILogins:
    """[로그인하기] 창과 마지막 로그인 확인 결과(AI 이름별). 결과는 메모리에만 둔다."""

    def __init__(self, check: Callable[[str], bool | None] | None = None,
                 launcher: Launcher | None = None) -> None:
        self.check = check  # AI 이름 → 그 프로그램의 로그인 상태 명령 결과
        self.launcher = launcher
        self.windows = LoginWindows()
        self.windows.on_closed = self._after_close
        self._results: dict[str, bool | None] = {}
        self._lock = threading.Lock()

    def remember(self, name: str, logged_in: bool | None) -> None:
        with self._lock:
            self._results[name] = logged_in

    def view(self, name: str) -> LoginView:
        with self._lock:
            known = self._results.get(name)
        return LoginView(self.windows.is_open(name), self.windows.is_closing(name), known)

    def open(self, name: str, args: list[str], env: dict[str, str]) -> LoginView:
        """그 프로그램의 로그인 명령을 새 창으로 연다. 이미 열려 있으면 다시 열지 않는다."""
        if not self.windows.is_open(name):
            proc = (self.launcher or default_launcher)(args, env)
            self.windows.track(name, proc)
        return self.view(name)

    def _after_close(self, name: str) -> None:
        """창이 닫힌 뒤 한 번 저절로 묻는다(못 물으면 「모름」으로 둔다)."""
        result: bool | None = None
        try:
            result = self.check(name) if self.check is not None else None
        except Exception:  # noqa: BLE001 - 자동 확인이 실패해도 사람이 [연결 확인]을 누를 수 있다
            log.info("로그인 창을 닫은 뒤 자동 확인을 하지 못했습니다(%s)", name)
        self.remember(name, result)
