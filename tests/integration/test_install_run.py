"""설치 파일을 실제로 실행해 갈래를 확인한다(Windows만).

창은 띄우지 않고(-NoLaunch) 키를 기다리지 않는다(-NoPause).

- 파이썬 없음: 빈 임시 폴더(경로에 띄어쓰기·한글)에 설치 파일만 복사하고,
  찾을 이름을 없는 이름으로 바꿔 넘긴다 → 종료 코드 2와 「Python 3.12가 필요합니다」.
  아무것도 받지 않고 .venv도 만들지 않는다.
- 이미 준비됨: 이 저장소(.venv가 있는 상태)에서 Install.cmd → 종료 코드 0과 「이미 준비됨」.
  .venv는 그대로.

출력은 콘솔 창이 있으면 한국어 Windows 콘솔과 같은 cp949로, 콘솔 없이 돌리면 PowerShell 부분이
UTF-8로 나온다. 줄마다 UTF-8·cp949로 풀어서(`_decode`) 한글이 그대로인지 본다.
실제 설치(패키지 내려받기)는 인터넷이 필요해 자동 테스트에 넣지 않았다
(한 번 돌린 결과는 docs/STAGES.md P단계).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 설치 파일")

FAKE = ["-PyLauncher", "jg-no-such-py-launcher", "-PythonCommand", "jg-no-such-python"]


def _run(cmd_file: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [str(cmd_file), "-NoPause", "-NoLaunch", *args],
        capture_output=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    return proc.returncode, _decode(proc.stdout) + _decode(proc.stderr)


def _decode(raw: bytes) -> str:
    """설치 파일 출력을 푼다. 콘솔 창이 있으면 cmd·PowerShell이 cp949로 내고, 콘솔 없이 돌리면
    (출력을 파일로 받는 실행 등) PowerShell 부분이 UTF-8로 나온다 — 한 출력 안에 둘이 섞일 수 있어
    줄마다 UTF-8 → cp949 차례로 풀고, 둘 다 안 되면 깨진 글자만 바꿔 넣는다(2026-11-18)."""
    lines = []
    for line in raw.splitlines(keepends=True):
        for codec in ("utf-8", "cp949"):
            try:
                lines.append(line.decode(codec))
                break
            except UnicodeDecodeError:
                continue
        else:
            lines.append(line.decode("utf-8", errors="replace"))
    return "".join(lines)


def _copy_installer(dest: Path) -> None:
    (dest / "scripts").mkdir(parents=True)
    for name in ("Install.cmd", "JG-Marketing-Agent.cmd", "requirements.txt"):
        shutil.copy2(ROOT / name, dest / name)
    for name in ("install.ps1", "install_messages.txt"):
        shutil.copy2(ROOT / "scripts" / name, dest / "scripts" / name)


@pytest.mark.parametrize("entry", ["Install.cmd", "JG-Marketing-Agent.cmd"])
def test_no_python_stops_with_korean_guide_and_exit_2(tmp_path: Path, entry: str):
    home = tmp_path / "새 폴더 (2)" / "jg agent"
    _copy_installer(home)

    code, out = _run(home / entry, *FAKE)

    assert code == 2, out
    assert "Python 3.12가 필요합니다" in out
    assert "https://www.python.org/downloads/" in out
    assert "winget install Python.Python.3.12" in out
    assert "걸린 시간:" in out
    assert not (home / ".venv").exists()  # 아무것도 만들지 않았다
    if entry == "JG-Marketing-Agent.cmd":
        assert "처음 실행입니다" in out  # 첫 실행 안내를 먼저 보여 준다


@pytest.mark.skipif(
    not (ROOT / ".venv" / "Scripts" / "pythonw.exe").exists(), reason="이 폴더에 .venv가 없다"
)
def test_already_ready_says_so_and_changes_nothing():
    venv_cfg = ROOT / ".venv" / "pyvenv.cfg"
    before = venv_cfg.stat().st_mtime

    code, out = _run(ROOT / "Install.cmd")

    assert code == 0, out
    assert "이미 준비됨" in out
    assert "pip" not in out.lower()  # 다시 설치하지 않았다
    assert venv_cfg.stat().st_mtime == before


def test_decode_reads_console_and_no_console_output():
    # 콘솔 창(cp949)과 콘솔 없음(UTF-8)의 출력이 한 줄씩 섞여도 한글이 그대로
    mixed = "처음 실행입니다\r\n".encode("cp949") + "Python 3.12가 필요합니다\r\n".encode()
    assert _decode(mixed) == "처음 실행입니다\r\nPython 3.12가 필요합니다\r\n"
    assert _decode(b"\xff\xfe ok\n") == "�� ok\n"  # 둘 다 아니면 깨진 글자만 바꾼다
