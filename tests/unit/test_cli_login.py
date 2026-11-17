"""[로그인하기](2026-11-17): 그 프로그램의 자기 로그인 명령을 보이는 창으로 열고,
닫히면 저절로 묻는다.

진짜 로그인 명령은 실행하지 않는다(가짜 창).
"""

from __future__ import annotations

import threading

import pytest

from app.llm import cli_login
from app.llm.cli_login import CLILogins, login_args


class FakeWindow:
    """닫힐 때까지 `wait()`가 기다리는 가짜 명령 창."""

    def __init__(self) -> None:
        self.closed = threading.Event()

    def poll(self):
        return 0 if self.closed.is_set() else None

    def wait(self):
        self.closed.wait(5)
        return 0

    def close(self) -> None:
        self.closed.set()


def test_login_commands_are_the_programs_own_and_an_argument_list():
    exe = r"C:\Tools\codex.exe"
    assert login_args("codex", exe) == [exe, "login"]
    assert login_args("claude", r"C:\Tools\claude.exe") == [r"C:\Tools\claude.exe", "auth", "login"]
    for program in ("gemini", "powershell", "cmd"):
        with pytest.raises(ValueError):
            login_args(program, "x")


def test_windows_open_a_new_visible_console_without_a_shell():
    import sys

    if sys.platform == "win32":
        import subprocess

        assert cli_login.NEW_CONSOLE == subprocess.CREATE_NEW_CONSOLE


def test_tests_cannot_open_a_real_login_window():
    with pytest.raises(AssertionError, match="진짜 로그인 명령"):
        cli_login.default_launcher(["codex", "login"], {})


def test_window_close_triggers_one_automatic_check():
    asked: list[str] = []
    done = threading.Event()

    def check(name):
        asked.append(name)
        done.set()
        return True

    window = FakeWindow()
    seen = {}

    def launcher(args, env):
        seen["args"], seen["env"] = args, env
        return window

    logins = CLILogins(check=check, launcher=launcher)
    view = logins.open("claude-cli", ["claude.exe", "auth", "login"], {"PATH": "x"})
    assert view.window_open and view.logged_in is None
    assert seen["args"] == ["claude.exe", "auth", "login"] and seen["env"] == {"PATH": "x"}
    # 열려 있는 동안 다시 눌러도 창을 하나 더 열지 않는다
    logins.open("claude-cli", ["claude.exe", "auth", "login"], {})
    window.close()
    assert done.wait(5)
    for _ in range(100):
        if not logins.view("claude-cli").checking:
            break
        threading.Event().wait(0.02)
    view = logins.view("claude-cli")
    assert asked == ["claude-cli"] and view.logged_in is True and not view.window_open


def test_failed_automatic_check_leaves_unknown():
    done = threading.Event()

    def check(name):
        done.set()
        raise RuntimeError("boom")

    window = FakeWindow()
    logins = CLILogins(check=check, launcher=lambda a, e: window)
    logins.remember("codex-cli", False)
    logins.open("codex-cli", ["codex.exe", "login"], {})
    window.close()
    assert done.wait(5)
    for _ in range(100):
        if not logins.view("codex-cli").checking:
            break
        threading.Event().wait(0.02)
    assert logins.view("codex-cli").logged_in is None
