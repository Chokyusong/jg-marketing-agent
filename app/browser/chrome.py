"""크롬 찾기, 프로필 폴더, 실제 유튜브(assist) 열기 — 8단계(DESIGN 6.1 · 6.3).

이 모듈은 실제 유튜브 화면을 **조작하지 않는다.** assist는 크롬 프로그램을 프로필 폴더와 영상 주소로
실행하는 것이 전부다(자동화 도구 없이, 셸 없이 인자 목록으로). 붙여넣기와 게시는 사람이 한다.
Playwright는 이 모듈에서 쓰지 않는다(테스트 페이지 자동 실행은 `app/browser/sandbox_driver.py`).

- 프로필 폴더: `<profiles_root>/profile-1` …(`ProfileService`의 폴더 이름). 기본 위치는
  `%LOCALAPPDATA%/JGMarketingAgent/profiles`(저장소 밖). 없으면 만든다.
- 같은 프로필 폴더를 다른 크롬이 쓰고 있으면 크롬이 폴더 안 `lockfile`을 잠가 둔다. 열기 전에
  그것을 보고 "그 프로필의 크롬 창을 닫아 주세요"로 알린다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.errors import AppError, ErrorKind

# Chrome은 이 이름의 파일을 프로필 폴더(user-data-dir) 바로 안에 만들고, 켜져 있는 동안 잠가 둔다.
LOCK_FILE = "lockfile"

Launcher = Callable[[Sequence[str]], Any]  # 인자 목록을 받아 프로세스(Popen 같은 것)를 돌려준다


def chrome_candidates(environ: dict[str, str] | None = None) -> list[Path]:
    """Windows에서 크롬이 흔히 설치되는 곳(사용자 설치 → 전체 설치)."""
    env = os.environ if environ is None else environ
    out: list[Path] = []
    for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramW6432"):
        base = env.get(var) or env.get(var.upper())
        if base:
            path = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if path not in out:
                out.append(path)
    return out


def _registry_chrome() -> Path | None:  # pragma: no cover - Windows 레지스트리
    if sys.platform != "win32":
        return None
    import winreg

    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "")
        except OSError:
            continue
        if value:
            return Path(str(value).strip('"'))
    return None


def find_chrome(
    configured: str | None = None,
    *,
    environ: dict[str, str] | None = None,
    exists: Callable[[Path], bool] = Path.is_file,
    registry: Callable[[], Path | None] = _registry_chrome,
) -> Path | None:
    """설정한 경로(있으면) → 흔한 설치 위치 → 레지스트리 순으로 chrome.exe를 찾는다."""
    if configured:
        path = Path(configured)
        return path if exists(path) else None
    for path in chrome_candidates(environ):
        if exists(path):
            return path
    found = registry()
    if found is not None and exists(found):
        return found
    return None


def profile_dir(root: Path, folder: str) -> Path:
    """프로필 폴더 경로. 폴더 이름은 `profile-<번호>`만 받는다(바깥 글로 경로를 만들지 않게)."""
    if not folder.startswith("profile-") or not folder[len("profile-") :].isdigit():
        raise ValueError(f"프로필 폴더 이름이 아님: {folder!r}")
    return Path(root) / folder


def ensure_profile_dir(root: Path, folder: str) -> Path:
    path = profile_dir(root, folder)
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_in_use(path: Path) -> bool:
    """다른 크롬이 이 프로필 폴더를 쓰고 있는지. 크롬이 잠가 둔 `lockfile`을 열어 본다.

    Windows에서 크롬은 이 파일을 공유 없이 열어 두므로, 다른 프로세스가 열려고 하면 거절된다.
    파일이 없거나 열리면 쓰는 크롬이 없다고 본다.
    """
    lock = Path(path) / LOCK_FILE
    if not lock.exists():
        return False
    if sys.platform != "win32":  # pragma: no cover - 이 프로젝트는 Windows에서 돈다
        return False
    try:
        fd = os.open(lock, os.O_RDWR)
    except PermissionError:
        return True
    except OSError:
        return False
    os.close(fd)
    return False


def require_profile_free(path: Path) -> None:
    if profile_in_use(path):
        raise AppError(ErrorKind.PROFILE_IN_USE, detail=f"프로필 폴더 {Path(path).name}")


def window_arg(position: tuple[int, int]) -> str:
    x, y = position
    return f"--window-position={int(x)},{int(y)}"


def assist_args(
    chrome: Path,
    user_data_dir: Path,
    url: str,
    window_position: tuple[int, int] | None,
    window_size: tuple[int, int] | None = None,
) -> list[str]:
    """실제 유튜브를 사람에게 열어 주는 크롬 실행 인자. 자동화 옵션은 하나도 넣지 않는다.

    2026-11-17: 위치·크기는 `app/browser/placement.py`가 정한다(모르면 빼고 크롬이 정한다).
    자동화 연결이 없으므로 연 뒤 확인·바로잡기는 하지 않는다."""
    args = [str(chrome), f"--user-data-dir={user_data_dir}"]
    if window_position is not None:
        args.append(window_arg(window_position))
    if window_size is not None:
        args.append(f"--window-size={int(window_size[0])},{int(window_size[1])}")
    return args + ["--no-first-run", "--no-default-browser-check", "--new-window", url]


def popen_launcher(args: Sequence[str]) -> subprocess.Popen[bytes]:
    """셸 없이 인자 목록으로 크롬을 실행한다(주소에 들어간 글자가 명령으로 해석되지 않게)."""
    return subprocess.Popen(  # noqa: S603 - 인자 목록, shell=False
        list(args),
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def stop_process(proc: Any, timeout: float = 5.0) -> None:
    """우리가 실행한 크롬 프로세스를 닫는다(이미 끝났으면 아무것도 안 한다)."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout)
        except Exception:
            proc.kill()
    except Exception:  # 닫는 중의 오류는 무시(프로그램 종료를 막지 않게)
        pass
