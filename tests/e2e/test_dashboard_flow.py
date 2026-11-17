"""9단계 e2e(R1 화면으로 옮김): 처음 보는 사람이 작업 화면 세 칸을 끝까지 쓰는 흐름.

창 없는 크롬, 임시 포트.

[영상 불러오기] → 영상 고르기(초안이 자동으로) → 자막 직접 넣기 → 연습 모드 → [댓글 달기]
→ [게시] → 게시 완료 → 기록·오늘 숫자 → 설정 화면 · 기록 화면(화면 이름에 초점)을 열고
작업 화면으로.

- 단계마다 금색으로 강조한 요소(.is-next)가 **정확히 하나**이고 그것이 다음 행동인지 본다.
- 유튜브는 저장해 둔 가짜 응답(httpx.MockTransport), AI는 가짜 LLM. 인터넷·키·Ollama 없이 돈다.
- 실제 유튜브를 여는 크롬 실행(launcher)은 막아 둔다. 크롬이 간 주소는 이 서버의 `/sandbox/`뿐.
- R3부터 설정 기본은 실제 게시 · 게시 직전 확인 끔이다. 이 시험은 연습 모드와 [게시] 단계를 보려고
  설정을 연습 모드(`default_target: sandbox`) · 게시 직전 확인 켬으로 바꿔 돈다.
- 창을 띄우지 않는다(headless). 주 모니터에 창이 뜨지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.screens import Monitor
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.llm.base import LLMHealth
from app.main import create_app

pytestmark = pytest.mark.e2e

VID = "BBBBBBBBBB2"
QUOTE = "하루에 한 번 연락으로 싸운 적 있어요"
ANALYSIS = {
    "topic": "장거리 연애 연락 문제",
    "concern": "연락 빈도 차이로 자주 다투는 장거리 커플",
    "tone": "진지한 사연 읽기",
    "viewer_needs": "연락 다툼을 줄이는 방법",
    "evidence": [{"quote": QUOTE, "source": "comment"}],
}
DRAFT = {
    "body": "'하루에 한 번 연락'으로 싸웠다는 댓글이 마음에 남네요. "
    "운명원 연애 사주 잘 본다던데 저도 한번 상담받아 보고 싶어요.",
    "used_quote": QUOTE,
    "tone_label": "공감형",
}
TRANSCRIPT = ("0:01 오늘은 장거리 연애 사연을 읽어 봅니다\n"
              "0:05 연락 횟수 때문에 자주 다툰다는 이야기예요")
DRAFT_TAG = "document.getElementById('draft-tag').textContent === '{}'"
JOB_STATE = "document.getElementById('job-box').dataset.state === '{}'"
YT = "/youtube/v3/"


class ScriptedLLM:
    """분석 요청(evidence가 있는 형식)에는 분석, 그 밖에는 초안을 돌려주는 가짜 LLM."""

    provider = "ollama"
    model = "fake-model"
    local = True

    def __init__(self) -> None:
        self.calls = 0
        self.warmups = 0

    def generate_json(self, *args, **kwargs):
        self.calls += 1
        return ANALYSIS if "evidence" in json.dumps(kwargs.get("schema", {})) else dict(DRAFT)

    def health(self) -> LLMHealth:
        return LLMHealth("ollama", "fake-model", True, True, True)

    def warmup(self):  # 이 테스트는 [모델 미리 불러오기]를 누르지 않는다
        self.warmups += 1
        raise AssertionError("warmup은 부르지 않는다")

    def close(self) -> None:
        pass


def _youtube(fixture_json):
    files = {f"{YT}search": "youtube/search.json", f"{YT}videos": "youtube/videos.json",
             f"{YT}commentThreads": "youtube/comment_threads.json"}

    def handler(request: httpx.Request) -> httpx.Response:
        name = files.get(request.url.path)
        if name is None:
            return httpx.Response(404, json={"error": {"message": "not in fixture"}})
        return httpx.Response(200, json=fixture_json(name))

    return httpx.MockTransport(handler)


def _no_real_chrome(args):
    raise AssertionError(f"실제 유튜브용 크롬을 띄우려 했다: {args!r}")


@pytest.fixture
def dashboard(tmp_path: Path, make_config, fixture_json) -> Iterator[dict]:
    config = make_config({
        "limits": {"daily_max_comments": 10},
        "posting": {"confirm_before_post": True},
        "browser": {"headless": True, "typing_delay_ms": [3, 8], "default_target": "sandbox",
                    "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(
        config, env_path=None, db_path=tmp_path / "e2e.sqlite3",
        environ={"YOUTUBE_API_KEY": "AIza" + "x" * 35,  # 가짜 키(실행할 때 조립)
                 "JG_PROFILES_DIR": str(tmp_path / "profiles")},
    )
    drivers: list = []

    def factory(browser_settings):
        driver = default_driver_factory(browser_settings)
        drivers.append(driver)
        return driver

    hooks = BrowserHooks(driver_factory=factory, launcher=_no_real_chrome,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)])
    app = create_app(settings, transport=_youtube(fixture_json), browser_hooks=hooks)
    services = app.state.services.get()
    llm = ScriptedLLM()
    services.llm = llm
    server = ServerThread(app, open_listen_socket())
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
    try:
        yield {"base": base, "drivers": drivers, "llm": llm}
    finally:
        services.jobs.shutdown(timeout=15)
        server.stop()


@pytest.fixture
def page(dashboard) -> Iterator:
    from playwright.sync_api import sync_playwright

    base = dashboard["base"]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 창 없이
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        # 바깥 주소(썸네일 이미지 등)는 부르지 않는다(인터넷 없이)
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                   else route.abort())
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.errors = errors
        try:
            yield page
        finally:
            browser.close()


def expect_next(page, element_id: str) -> None:
    """금색 강조가 정확히 하나이고, 그것이 element_id다."""
    page.wait_for_function(
        "(id) => { const n = document.querySelectorAll('.is-next');"
        " return n.length === 1 && n[0].id === id; }", arg=element_id, timeout=15000)
    found = page.eval_on_selector_all(".is-next", "(nodes) => nodes.map((n) => n.id)")
    assert found == [element_id], found
    hint = page.text_content("#next-hint") or ""
    assert hint.strip(), "위 줄에 다음 행동 안내가 없다"


def job_state(page) -> str:
    return page.get_attribute("#job-box", "data-state") or ""


def test_first_user_can_finish_the_whole_flow_with_one_highlight_per_step(dashboard, page):
    base = dashboard["base"]
    page.goto(base + "/")
    page.wait_for_function("document.getElementById('status-browser').textContent !== '확인 중'")

    # ① 처음: [영상 불러오기]
    expect_next(page, "search-btn")
    page.click("#search-btn")
    page.wait_for_selector(f'.vid[data-id="{VID}"]')

    # ② 목록이 뜨면: 목록에서 고르기. 고르면 단추 없이 고민 한 줄과 초안이 나온다
    expect_next(page, "video-list")
    page.click(f'.vid[data-id="{VID}"]')
    page.wait_for_function(DRAFT_TAG.format("검사 통과"), timeout=30000)
    assert page.text_content("#an-concern") == ANALYSIS["concern"]

    # 자막을 직접 넣어도 초안은 그대로(이미 있으면 다시 만들지 않는다)
    calls = dashboard["llm"].calls
    page.click("#transcript-paste > summary")
    page.fill("#transcript-text", TRANSCRIPT)
    page.click("#transcript-save")
    page.wait_for_function(
        "document.getElementById('ctx-transcript').textContent.includes('붙여 넣은 자막')")
    page.wait_for_function(DRAFT_TAG.format("검사 통과"), timeout=15000)
    assert dashboard["llm"].calls == calls

    # ③ 초안이 규칙 검사를 통과하면: 연습 모드로 [댓글 달기]
    assert page.is_checked("#practice-mode")
    expect_next(page, "job-primary")
    assert page.text_content("#job-primary") == "댓글 달기"
    page.click("#job-primary")

    # ④ 게시 직전: 금색 [게시]
    page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
    expect_next(page, "job-primary")
    assert page.text_content("#job-primary") == "게시"
    page.click("#job-primary")
    page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
    assert job_state(page) == "posted"

    # ⑤ 게시 완료: 다음은 다른 영상 고르기. 기록과 오늘 숫자가 바로 바뀐다
    expect_next(page, "video-list")
    # 2026-11-17(PDF 대조): 오늘 숫자는 실제 게시 기준. 연습 게시는 따로 「연습 n」(흐리게)
    page.wait_for_function("document.getElementById('today-count').textContent.includes('연습 1')")
    assert page.text_content("#stat-posted").strip() == "0"
    assert page.text_content("#stat-success").strip() == "–"
    page.wait_for_function("document.querySelectorAll('#records-body td.st').length >= 1")
    rows = page.eval_on_selector_all("#records-body tr", "(rows) => rows.map((r) => r.textContent)")
    assert 1 <= len(rows) <= 4  # ③ 아래 표는 최근 게시 4줄까지
    assert "성공" in rows[0]
    assert page.text_content("#today-count").startswith("0/10")
    assert page.text_content("#records-body .kind") == "연습"

    # ⑥ 설정 화면: 열면 화면 이름에 초점. 키 값은 보이지 않는다
    page.click("#nav-settings")
    page.wait_for_function("document.getElementById('settings-body').querySelector('.set-group')")
    assert page.evaluate("document.activeElement.id") == "screen-title"
    assert page.text_content("#screen-title") == "설정"
    settings_text = page.text_content("#settings-body")
    # R2: 홍보하는 곳 · 홍보 표기는 고칠 수 있는 칸에 들어 있다(글자로는 모델 이름이 보인다)
    assert page.input_value("#set-brand") == "운명원"
    assert page.input_value("#set-disclosure") == "[광고]"
    assert "fake-model" in settings_text
    assert "AIza" not in settings_text and "AIza" not in page.content()
    page.click("#nav-work")
    assert page.is_visible("#screen-work") and not page.is_visible("#screen-settings")

    # ⑦ 기록 전체: 전체 기록(실패 이유 칸 포함)
    page.click("#records-all")
    page.wait_for_function("document.querySelectorAll('#records-all-body tr td.st').length >= 1")
    assert page.evaluate("document.activeElement.id") == "screen-title"
    assert "실제 게시 0건 · 연습 1건" in page.text_content("#records-all-meta")  # 처음은 「게시」
    page.check('input[name="records-filter"][value="all"]', force=True)
    page.wait_for_function("document.querySelectorAll('#records-all-body tr').length >= 4")
    assert "모든 활동" in page.text_content("#records-all-meta")
    page.click("#nav-work")
    expect_next(page, "video-list")

    # 강조는 끝까지 하나, 실제 유튜브는 열지 않았고 모델 미리 불러오기는 부르지 않았다
    assert page.eval_on_selector_all(".is-next", "(n) => n.length") == 1
    assert dashboard["llm"].warmups == 0
    for driver in dashboard["drivers"]:
        for url in driver.visited:
            assert url.startswith(f"{base}/sandbox/"), url
    assert not page.errors, page.errors
