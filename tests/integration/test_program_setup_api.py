"""아무 PC에서나 AI 연결(2026-11-17): 로그인된 프로그램의 상태마다 보이는 것과 [로그인하기].

- 설치되지 않음 → [설치 방법 보기](공식 설치 명령·페이지, 확인한 날). 이 앱은 설치하지 않는다.
- 설치됨·로그인 안 됨 → [로그인하기]: 그 프로그램의 **자기 로그인 명령**을 인자 목록으로
  새 창에 연다.
  창이 닫히면 로그인 상태 명령으로 한 번 저절로 묻는다.
- 로그인됨 → 지금처럼 쓴다.
- Gemini(명령줄 프로그램)는 2026-11-18 목록에서 뺐다(API 키 방식 Gemini는 그대로).

진짜 프로그램·로그인 명령은 실행하지 않는다(가짜 실행기·가짜 창). 로그인 정보 파일도 읽지 않는다.
"""

from __future__ import annotations

import threading
import time

import pytest
from test_llm_switch_api import ai_mock, by_name, youtube_mock

from app.browser.hooks import BrowserHooks
from app.llm import cli


class FakeWindow:
    def __init__(self) -> None:
        self.closed = threading.Event()

    def poll(self):
        return 0 if self.closed.is_set() else None

    def wait(self):
        self.closed.wait(5)
        return 0


class Programs:
    """가짜 PATH와 가짜 실행기: 어떤 프로그램이 설치됐고 로그인됐는지 정한다."""

    def __init__(self, installed=(), logged_in=()):
        self.installed = set(installed)
        self.logged_in = set(logged_in)
        self.calls: list[list[str]] = []

    def which(self, program):
        return f"C:/fake/{program}.exe" if program in self.installed else None

    def run(self, req):
        self.calls.append(list(req.args))
        program = req.args[0].rsplit("/", 1)[-1].removesuffix(".exe")
        if req.args[1:] == ["--version"]:
            return cli.RunResult(0, f"{program} 9.9.9", "")
        if req.args[1:] in (["login", "status"], ["auth", "status"]):
            return cli.RunResult(0 if program in self.logged_in else 1, "", "")
        raise AssertionError(f"뜻밖의 실행: {req.args}")


@pytest.fixture
def setup(make_client, mock_http, fixture_json, fake_key, monkeypatch):
    windows: list[tuple[list[str], dict, FakeWindow]] = []

    def launcher(args, env):
        window = FakeWindow()
        windows.append((args, env, window))
        return window

    def make(programs: Programs):
        monkeypatch.setattr(cli, "default_which", programs.which)
        monkeypatch.setattr(cli, "default_runner", programs.run)
        hooks = BrowserHooks(cli_login_launcher=launcher)
        return make_client(youtube_mock(mock_http, fixture_json), key=fake_key,
                           llm=ai_mock(mock_http), browser_hooks=hooks)

    return make, windows


def wait_until(check, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


def test_not_installed_shows_the_official_install_guide(setup):
    make, windows = setup
    client = make(Programs())
    items = by_name(client)
    for name, command, page in [
        ("claude-cli", "irm https://claude.ai/install.ps1 | iex",
         "https://code.claude.com/docs/en/setup"),
        ("codex-cli", "irm https://chatgpt.com/codex/install.ps1 | iex",
         "https://learn.chatgpt.com/docs/codex/cli.md"),
    ]:
        p = items[name]
        assert p["installed"] is False and p["can_open_login"] is False
        guide = p["install_guide"]
        assert command in guide["command"] and guide["page"] == page
        assert guide["shell"] == "PowerShell" and guide["checked"] == "2026-11-17"
        assert any("따로 설치" in n for n in guide["notes"])
    # 설치되지 않은 프로그램은 [로그인하기]가 안 된다(창을 열지 않는다)
    res = client.post("/api/llm/providers/claude-cli/login")
    assert res.status_code == 503 and "설치돼 있지 않습니다" in res.json()["error"]["message"]
    assert windows == []


def test_installed_but_logged_out_opens_the_programs_own_login_and_checks_after_close(setup):
    make, windows = setup
    programs = Programs(installed={"claude", "codex"})
    client = make(programs)
    # [연결 확인]이 로그인 안 됨을 알아 둔다 → 목록에 「로그인 필요」
    res = client.post("/api/llm/providers/claude-cli/test").json()
    assert res["result"] == "not_logged_in"
    p = by_name(client)["claude-cli"]
    assert p["installed"] is True and p["logged_in"] is False and p["can_open_login"] is True
    # [로그인하기]: 셸 없이 그 프로그램의 로그인 명령(인자 목록)
    res = client.post("/api/llm/providers/claude-cli/login")
    assert res.status_code == 200 and res.json()["login_window_open"] is True
    args, env, window = windows[-1]
    assert args == ["C:/fake/claude.exe", "auth", "login"]
    assert not any(k in env for k in ("YOUTUBE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"))
    # 열려 있는 동안 다시 눌러도 창을 하나 더 열지 않는다
    client.post("/api/llm/providers/claude-cli/login")
    assert len(windows) == 1
    # 사람이 창에서 로그인하고 창을 닫는다 → 저절로 다시 묻는다
    programs.logged_in.add("claude")
    window.closed.set()
    assert wait_until(lambda: by_name(client)["claude-cli"]["logged_in"] is True)
    p = by_name(client)["claude-cli"]
    assert p["login_window_open"] is False and p["login_checking"] is False
    assert ["C:/fake/claude.exe", "auth", "status"] in programs.calls
    # Codex는 `codex login`
    client.post("/api/llm/providers/codex-cli/login")
    assert windows[-1][0] == ["C:/fake/codex.exe", "login"]


def test_logged_in_program_is_ready_as_before(setup):
    make, windows = setup
    client = make(Programs(installed={"codex"}, logged_in={"codex"}))
    res = client.post("/api/llm/providers/codex-cli/test").json()
    assert res["ok"] is True and "로그인돼 있습니다" in res["message"]
    p = by_name(client)["codex-cli"]
    assert p["logged_in"] is True and p["unavailable_reason"] is None
    assert windows == []


def test_gemini_program_is_not_in_the_list(setup):
    """2026-11-18(대표 지시): Gemini 명령줄 프로그램은 고를 수 없어 목록에서 뺐다.

    설치돼 있어도 보이지 않고, 그 이름으로 묻거나 로그인 창을 열 수 없다. API 키 방식의
    Gemini(Google)는 그대로 있다."""
    make, windows = setup
    client = make(Programs(installed={"gemini"}))
    items = by_name(client)
    assert "gemini-cli" not in items
    programs = [n for n, p in items.items() if p["kind"] == "program"]
    assert sorted(programs) == ["claude-cli", "codex-cli"]  # 프로그램 방식은 둘만
    assert items["gemini"]["kind"] == "api" and items["gemini"]["needs_key"] is True
    assert all(not p["not_wired_notes"] for p in items.values())
    res = client.post("/api/llm/providers/gemini-cli/login")
    assert res.status_code >= 400 and windows == []
    assert client.post("/api/llm/providers/gemini-cli/test").status_code >= 400


def test_antigravity_is_not_in_the_list(setup):
    make, _ = setup
    items = by_name(make(Programs(installed={"agy", "gemini"})))
    assert not any("agy" in n or "antigravity" in n.lower() for n in items)


def test_first_run_key_path_is_three_steps(setup):
    make, _ = setup
    paths = {p["key"]: p for p in make(Programs()).get("/api/llm/providers").json()["first_run"]}
    key = paths["key"]
    assert key["providers"] == ["gemini"] and key["link"] == "https://aistudio.google.com/apikey"
    assert key["link_label"] == "키 받는 페이지 열기"
    assert "[키 받는 페이지 열기] → 이 AI 칸에 키 붙여 넣기 → [연결 확인]" in key["detail"]
    assert "무료 등급" in key["detail"] and "2026-11-17 확인" in key["detail"]


def test_api_key_ai_has_no_program_fields(setup):
    make, _ = setup
    p = by_name(make(Programs()))["openai"]
    assert p["install_guide"] is None and p["can_open_login"] is False and p["logged_in"] is None


def test_login_asked_tells_not_asked_from_asked_but_unknown(setup):
    # 2026-11-18(기획 담당): 설정 화면이 로그인 여부를 모르는 동안 「준비됨」이라고 하지 않게,
    # 목록이 「아직 안 물어봄」과 「물었지만 모름」을 가른다(필드 추가 `login_asked`)
    make, _ = setup
    programs = Programs(installed={"claude"})
    client = make(programs)
    p = by_name(client)["claude-cli"]
    # 아직 안 물어봄 → 화면은 「확인 중」으로 두고 묻는다
    assert p["logged_in"] is None and p["login_asked"] is False
    assert by_name(client)["codex-cli"]["login_asked"] is False  # 설치되지 않음
    # 묻는 길은 [연결 확인]과 같다: 버전과 그 프로그램의 로그인 상태 명령만
    client.post("/api/llm/providers/claude-cli/test")
    p = by_name(client)["claude-cli"]
    assert p["logged_in"] is False and p["login_asked"] is True
    assert programs.calls == [["C:/fake/claude.exe", "--version"],
                              ["C:/fake/claude.exe", "auth", "status"]]


def test_status_command_that_cannot_answer_is_asked_but_unknown(setup):
    make, _ = setup

    class Silent(Programs):
        def run(self, req):
            if req.args[1:] == ["auth", "status"]:
                self.calls.append(list(req.args))
                raise cli.RunTimeout()
            return super().run(req)

    client = make(Silent(installed={"claude"}))
    res = client.post("/api/llm/providers/claude-cli/test").json()
    assert res["ok"] is True and "로그인 여부는 확인하지 못했습니다" in res["message"]
    p = by_name(client)["claude-cli"]
    assert p["logged_in"] is None and p["login_asked"] is True  # 화면은 「로그인 모름」
