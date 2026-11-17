"""받아서 더블클릭 한 번으로 설치하는 파일들(Install.cmd, scripts/install.ps1)의 규칙.

- .cmd·.ps1은 ASCII다(AGENTS.md: Windows PowerShell 5.1은 BOM 없는 UTF-8 한글을 깨뜨린다).
- 한글 문구는 scripts/install_messages.txt(UTF-8)에 두고,
  한국어 Windows 기본 콘솔(cp949)에 있는 글자만 쓴다.
- 설치 파일은 Python을 대신 설치하지 않고, requirements.txt의 패키지만 받는다.
- 자동 시험용 스위치 -NoPause -NoLaunch가 있다.

갈래별 실제 실행(파이썬 없음 → 2, 이미 준비됨 → 0)은 tests/integration/test_install_run.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_CMD = ROOT / "Install.cmd"
LAUNCHER = ROOT / "JG-Marketing-Agent.cmd"
INSTALL_PS1 = ROOT / "scripts" / "install.ps1"
MESSAGES = ROOT / "scripts" / "install_messages.txt"


def _messages() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in MESSAGES.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value
    return out


def test_install_files_are_ascii():
    for path in (INSTALL_CMD, LAUNCHER, INSTALL_PS1):
        path.read_bytes().decode("ascii")  # 한 글자라도 ASCII가 아니면 실패


def test_cmd_and_ps1_use_crlf():
    # .gitattributes가 *.cmd·*.ps1을 CRLF로 둔다. cmd.exe는 LF만 있으면 goto 라벨을 놓칠 수 있다.
    for path in (INSTALL_CMD, LAUNCHER, INSTALL_PS1):
        raw = path.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n"), path.name


def test_messages_are_utf8_and_fit_the_korean_console():
    raw = MESSAGES.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # BOM 없음(첫 줄 키가 깨지지 않게)
    msgs = _messages()
    assert msgs
    for key, text in msgs.items():
        text.encode("cp949")  # cp949 콘솔로 보낼 때 ?로 바뀌는 글자가 없다
        assert text.strip(), key


def test_every_message_key_used_by_install_ps1_exists():
    text = INSTALL_PS1.read_text(encoding="ascii")
    used = set(re.findall(r"\b(?:Say|Wait-Key)\s+'([a-z_]+)'", text))
    used |= set(re.findall(r"\$messages\['([a-z_]+)'\]", text))
    assert used, "install.ps1에서 문구 키를 찾지 못했습니다"
    missing = used - set(_messages())
    assert not missing, f"install_messages.txt에 없는 키: {sorted(missing)}"


def test_required_wording_is_present():
    msgs = _messages()
    assert "Python 3.12가 필요합니다" in msgs["python_missing"]
    assert "python.org" in msgs["python_get_page"]
    assert "winget install Python.Python.3.12" in msgs["python_get_winget"]
    assert "댓글을 달려면 Google Chrome이 필요합니다" in msgs["chrome_missing"]
    assert msgs["already_ready"].startswith("이미 준비됨")
    assert "설치가 끝났습니다" in msgs["done"]
    assert "JG-Marketing-Agent.cmd를 더블클릭하세요" in msgs["done"]
    assert "처음 실행입니다" in msgs["first_run"]
    assert "아무 키나" in msgs["press_key"]
    assert "{0}" in msgs["elapsed"]


def test_install_ps1_has_test_switches_and_exit_codes():
    text = INSTALL_PS1.read_text(encoding="ascii")
    for switch in ("[switch]$NoPause", "[switch]$NoLaunch", "[switch]$FirstRun"):
        assert switch in text
    assert "Finish 2" in text  # 파이썬 없음
    assert "Finish 1" in text  # 설치 실패
    assert "Finish 0" in text  # 준비됨
    assert "if ($NoLaunch) { return }" in text
    assert "if ($NoPause) { return }" in text


def test_install_ps1_finds_python_in_the_agreed_order():
    text = INSTALL_PS1.read_text(encoding="ascii")
    assert text.index("'-3.12'") < text.index("'-3.13'") < text.index("$PythonCommand @()")


def test_install_ps1_never_installs_python_and_downloads_only_requirements():
    text = INSTALL_PS1.read_text(encoding="ascii").lower()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    # 문구 키 이름(python_get_winget)은 명령이 아니다
    code = re.sub(r"\bsay '[a-z_]+'", "say", code)
    banned_words = ("winget", "invoke-webrequest", "invoke-restmethod", "iwr ", "curl", "wget",
                    "downloadfile", "start-bitstransfer", "msiexec", "playwright install")
    for banned in banned_words:
        assert banned not in code, banned
    pip_lines = [line for line in code.splitlines() if "pip install" in line]
    assert pip_lines == ["& $venvpy -m pip install --disable-pip-version-check -r $requirements"]


def test_install_cmd_calls_install_ps1_and_passes_exit_code():
    text = INSTALL_CMD.read_text(encoding="ascii")
    assert 'cd /d "%~dp0"' in text
    assert '-File "%~dp0scripts\\install.ps1" %*' in text
    assert "-ExecutionPolicy Bypass" in text
    assert "exit /b %code%" in text


def test_launcher_runs_first_time_install_when_venv_is_missing():
    text = LAUNCHER.read_text(encoding="ascii")
    block = text[text.index('if not exist ".venv\\Scripts\\pythonw.exe"'):text.index("start \"\"")]
    assert '-File "%~dp0scripts\\install.ps1" -FirstRun %*' in block
    # .venv가 있을 때는 예전처럼 바로 창을 연다
    assert 'start "" ".venv\\Scripts\\pythonw.exe" -m app.desktop' in text
