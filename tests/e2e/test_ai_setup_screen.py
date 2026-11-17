"""아무 PC에서나 AI 연결(2026-11-17) 화면 e2e: 첫 실행 안내 세 길 → 프로그램 상태마다 보이는 것.

- Claude Code: 설치됨·로그인 안 됨 → 칸을 열면 저절로 한 번 묻고 「로그인 필요」 →
  [로그인하기] → (가짜) 로그인 창이 그 프로그램의 로그인 명령으로 열림 → 창을 닫으면 저절로
  다시 묻고 「준비됨」.
- Codex: 설치되지 않음 → [설치 방법 보기]에 공식 설치 명령·[복사]·공식 페이지.
- Gemini(명령줄 프로그램): 2026-11-18 목록에서 뺐다(API 키 방식 Gemini는 그대로).
- 1920×1009 · 1600×960에서 화면 전체 스크롤 없음, 가장 작은 글자 12px 이상.

진짜 프로그램·로그인 명령은 실행하지 않는다(가짜 PATH·가짜 실행기·가짜 창). 창 없는(headless) 크롬.
"""

from __future__ import annotations

import threading

import pytest
from r1_support import headless_page, measure, r1_server

from app.llm import cli

pytestmark = pytest.mark.e2e

STATUS_LOADED = "document.getElementById('status-youtube').textContent !== '확인 중'"
AI_LOADED = "document.getElementById('ai-list') !== null"
FORBIDDEN = ("LLM", "공급자", "CLI")


class FakeWindow:
    def __init__(self) -> None:
        self.closed = threading.Event()

    def poll(self):
        return 0 if self.closed.is_set() else None

    def wait(self):
        self.closed.wait(30)
        return 0


class Programs:
    """가짜 PATH와 가짜 실행기. 버전·로그인 상태 명령만 받는다."""

    def __init__(self, installed=(), logged_in=()):
        self.installed = set(installed)
        self.logged_in = set(logged_in)
        self.calls: list[list[str]] = []
        self.gate: threading.Event | None = None  # 놓을 때까지 로그인 상태 명령이 답하지 않는다

    def which(self, program):
        return f"C:/fake/{program}.exe" if program in self.installed else None

    def run(self, req):
        self.calls.append(list(req.args))
        program = req.args[0].rsplit("/", 1)[-1].removesuffix(".exe")
        if req.args[1:] == ["--version"]:
            return cli.RunResult(0, f"{program} 9.9.9", "")
        if req.args[1:] in (["login", "status"], ["auth", "status"]):
            if self.gate is not None:
                self.gate.wait(10)
            return cli.RunResult(0 if program in self.logged_in else 1, "", "")
        raise AssertionError(f"뜻밖의 실행: {req.args}")


@pytest.fixture
def programs(monkeypatch):
    fake = Programs(installed={"claude", "gemini"})
    monkeypatch.setattr(cli, "default_which", fake.which)
    monkeypatch.setattr(cli, "default_runner", fake.run)
    return fake


@pytest.fixture
def app(tmp_path, make_config, fixture_json, programs):
    windows: list[tuple[list[str], dict, FakeWindow]] = []

    def launcher(args, env):
        window = FakeWindow()
        windows.append((args, env, window))
        return window

    with r1_server(tmp_path, make_config, fixture_json, user_dir=tmp_path / "user",
                   cli_login_launcher=launcher) as served:
        served["windows"] = windows
        yield served
    for _, _, window in windows:
        window.closed.set()


def open_ai(page) -> None:
    page.click("#nav-settings")
    page.wait_for_function(AI_LOADED)


def test_first_run_paths_and_each_program_state(app, programs):
    base, windows = app["base"], app["windows"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)

        # 첫 실행 안내: 권하는 순서 — 구독 프로그램 → API 키(무료 등급) → 이 PC(크기·시간)
        assert page.is_visible("#ai-first-run")
        order = page.eval_on_selector_all("#ai-first-run li", "els => els.map(e => e.id)")
        assert order == ["ai-path-program", "ai-path-key", "ai-path-ollama"]
        assert "무료 등급" in page.text_content("#ai-path-key")
        ollama = page.text_content("#ai-path-ollama")
        assert "18GB" in ollama and "25~35초" in ollama

        # Codex: 설치되지 않음 → 공식 설치 명령과 [복사]
        assert "설치되지 않음" in page.text_content("#ai-item-codex-cli")
        page.click("#ai-item-codex-cli")
        assert page.is_visible("#ai-install-codex-cli")
        assert "irm https://chatgpt.com/codex/install.ps1 | iex" in page.input_value(
            "#ai-install-cmd-codex-cli")
        assert page.is_visible("#ai-install-copy-codex-cli")
        guide = page.text_content("#ai-install-codex-cli")
        assert "공식 문서 기준 2026-11-17 확인" in guide and "따로 설치" in guide
        assert page.locator("#ai-login-codex-cli").count() == 0

        # Gemini(명령줄 프로그램): 2026-11-18 목록에서 뺐다. API 키 방식 Gemini는 그대로
        assert page.locator("#ai-item-gemini-cli").count() == 0
        assert page.locator("#ai-item-gemini").count() == 1
        assert "Antigravity" not in page.text_content("#settings-body")

        # 첫 실행 안내의 「이 길로 보기」 → 구독 프로그램 중 설치된 Claude Code 칸.
        # 설정을 열 때 로그인 상태를 저절로 한 번 물었다(2026-11-18) → 「로그인 필요」
        page.click("#ai-path-program [data-ai-path]")
        assert page.is_visible("#ai-pane-claude-cli")
        page.wait_for_selector("#ai-login-claude-cli")
        assert "로그인 필요" in page.text_content("#ai-item-claude-cli")
        assert ["C:/fake/claude.exe", "auth", "status"] in programs.calls
        page.wait_for_function("document.getElementById('ai-note-claude-cli')"
                               ".textContent.includes('[로그인하기]를 누르면')")
        assert "auth login" not in page.text_content("#ai-note-claude-cli")

        # [로그인하기] → 그 프로그램의 로그인 명령(인자 목록)으로 창 하나
        page.click("#ai-login-claude-cli")
        page.wait_for_function("document.getElementById('ai-pane-claude-cli')"
                               ".textContent.includes('로그인 창이 열려 있습니다')")
        assert len(windows) == 1
        assert windows[0][0] == ["C:/fake/claude.exe", "auth", "login"]
        assert page.is_disabled("#ai-login-claude-cli")

        # 사람이 그 창에서 로그인하고 닫는다 → 저절로 다시 묻고 「준비됨」
        programs.logged_in.add("claude")
        windows[0][2].closed.set()
        page.wait_for_function("document.getElementById('ai-note-claude-cli')"
                               ".textContent.includes('로그인됐습니다')", timeout=15000)
        assert "준비됨" in page.text_content("#ai-item-claude-cli")
        assert page.locator("#ai-login-claude-cli").count() == 0
        assert len(windows) == 1

        # 화면 글에 「LLM」「공급자」「CLI」가 없다
        for screen in ("settings", "work"):
            page.click(f"#nav-{screen}")
            text = page.inner_text("body")
            for word in FORBIDDEN:
                assert word not in text, (screen, word)
    assert not errors, errors


def test_setup_box_path_button_opens_that_ai(app):
    """시작 준비 상자의 「AI 붙이는 길」 → 설정 「AI 모델」의 그 길 칸.

    가짜 AI는 준비돼 있어 줄이 숨겨지므로 시험에서는 숨김을 풀고 누른다."""
    base = app["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        page.evaluate("document.getElementById('setup-ai-paths').hidden = false")
        page.click("#setup-ai-paths [data-setup-path='key']")
        page.wait_for_function(AI_LOADED)
        assert page.is_visible("#ai-pane-gemini")
        assert not page.is_visible("#ai-pane-ollama")
    assert not errors, errors


def test_key_path_is_three_steps(app):
    """「API 키로 → Gemini」: [키 받는 페이지 열기] → 키 붙여 넣기 → [연결 확인]. [키 저장]을
    따로 누르지 않아도 저장되고, 모델은 추천 목록 첫 번째로 골라진다. 키는 화면에 남지 않는다.
    받는 곳은 가짜 AI 회사(진짜 구글을 부르지 않는다)."""
    base = app["base"]
    key = "AIza" + "k" * 35  # 실행할 때 조립한 가짜 키
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        page.evaluate("document.getElementById('setup-ai-paths').hidden = false")
        page.click("#setup-ai-paths [data-setup-path='key']")
        page.wait_for_function(AI_LOADED)
        assert "키 받는 페이지 열기" in page.text_content("#ai-path-key")
        assert page.get_attribute("#ai-path-key a", "href") == "https://aistudio.google.com/apikey"
        page.fill("#ai-key-gemini", key)
        page.click("#ai-test-gemini")
        page.wait_for_function("document.getElementById('ai-note-gemini')"
                               ".textContent.includes('추천 목록 첫 번째')")
        assert "키 저장" not in page.text_content("#ai-note-gemini")
        assert page.input_value("#ai-model-gemini") == "gemini-3.8-flash"
        assert "저장됨" in page.text_content("#ai-pane-gemini")
        assert page.is_enabled("#ai-use-gemini")
        assert key not in page.content()
    assert not errors, errors


@pytest.mark.parametrize("size", [(1920, 1009), (1600, 960)])
def test_setup_screens_fit_without_page_scroll(app, size):
    base = app["base"]
    with headless_page(base, size=size) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        # 작업 화면: 시작 준비 상자에 세 길이 보이는 가장 긴 상태
        page.evaluate("document.getElementById('setup-ai-paths').hidden = false")
        m = measure(page, *size)
        assert not m["pageScroll"] and not m["hScroll"], ("work", size, m["scrollHeight"])
        assert m["minFont"] >= 12, ("work", size, m["minFont"], m["minFontAt"])

        open_ai(page)
        assert page.is_visible("#ai-first-run")  # 첫 실행 안내가 펼쳐진 상태
        for name in ("codex-cli", "claude-cli"):  # gemini-cli는 2026-11-18 뺐다
            page.click(f"#ai-item-{name}")
            if name == "claude-cli":
                page.wait_for_selector("#ai-login-claude-cli")
            m = measure(page, *size)
            where = f"{name} {size}"
            assert not m["pageScroll"] and not m["hScroll"], (
                where, m["scrollHeight"], m["scrollWidth"])
            assert m["minFont"] >= 12, (where, m["minFont"], m["minFontAt"])
            assert m["buttons"]["min"] >= 36, (where, m["buttons"])
    assert not errors, errors


def test_list_says_checking_until_the_login_answer_comes(app, programs):
    # 2026-11-18(기획 담당): 설치된 프로그램은 설정을 열 때 로그인 상태를 한 번 묻고, 답이 오기
    # 전에는 「확인 중」 — 「준비됨」이었다가 칸을 열면 「로그인 필요」로 바뀌지 않는다
    base = app["base"]
    programs.gate = threading.Event()
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        page.wait_for_function("document.getElementById('ai-item-claude-cli')"
                               ".textContent.includes('확인 중')")
        assert "준비됨" not in page.text_content("#ai-item-claude-cli")
        assert "준비됨" not in page.text_content("#ai-path-program")
        assert "확인하는 중" in page.text_content("#ai-pane-claude-cli")
        programs.gate.set()
        # 칸을 열지 않아도 답이 오면 바뀐다
        page.wait_for_function("document.getElementById('ai-item-claude-cli')"
                               ".textContent.includes('로그인 필요')")
        assert ["C:/fake/claude.exe", "auth", "status"] in programs.calls
        assert "준비됨" not in page.text_content("#ai-path-program")
        # 같은 화면에서 다시 묻지 않는다(칸을 열어도 한 번만)
        asked = programs.calls.count(["C:/fake/claude.exe", "auth", "status"])
        page.click("#ai-item-claude-cli")
        page.wait_for_selector("#ai-login-claude-cli")
        assert programs.calls.count(["C:/fake/claude.exe", "auth", "status"]) == asked
    assert not errors, errors
