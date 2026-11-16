"""9단계 e2e: 처음 보는 사람이 대시보드 세 칸을 끝까지 쓰는 흐름(창 없는 크롬, 임시 포트).

[영상 찾기] → 영상 고르기 → 자막 붙여 넣기 → [분석하고 초안 만들기] → [이 초안 승인]
→ 테스트 페이지 모드 → [브라우저에서 영상 열기] → [게시 승인] → 게시 완료
→ 작업 기록·오늘 통계 → SETTINGS·VIEW ALL 열고 Esc로 닫기(초점이 연 단추로 돌아온다).

- 단계마다 금색으로 강조한 요소(.is-next)가 **정확히 하나**이고 그것이 다음 행동인지 본다.
- 유튜브는 저장해 둔 가짜 응답(httpx.MockTransport), AI는 가짜 LLM. 인터넷·키·Ollama 없이 돈다.
- 실제 유튜브를 여는 크롬 실행(launcher)은 막아 둔다. 크롬이 간 주소는 이 서버의 `/sandbox/`뿐.
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
    "body": f"'{QUOTE}'라는 댓글이 마음에 남네요. "
    "운명원에서 연애 사주 상담을 받아 보셔도 좋겠어요.",
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
        "browser": {"headless": True, "typing_delay_ms": [3, 8],
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
    hint = page.text_content(".progress .step.is-current .step-hint") or ""
    assert hint.strip(), "흐름 띠에 다음 행동 안내가 없다"


def job_state(page) -> str:
    return page.get_attribute("#job-box", "data-state") or ""


def test_first_user_can_finish_the_whole_flow_with_one_highlight_per_step(dashboard, page):
    base = dashboard["base"]
    page.goto(base + "/")
    page.wait_for_function("document.getElementById('status-browser').textContent.includes('크롬')")

    # ① 처음: [영상 찾기]
    expect_next(page, "search-btn")
    page.click("#search-btn")
    page.wait_for_selector(f'.vid[data-id="{VID}"]')

    # ② 목록이 뜨면: 목록에서 고르기
    expect_next(page, "video-list")
    page.click(f'.vid[data-id="{VID}"]')
    page.wait_for_function("document.getElementById('ctx-transcript').textContent.includes('자막')")

    # ③ 고르면: [분석하고 초안 만들기]. 그 전에 자막을 붙여 넣는다
    expect_next(page, "run-btn")
    page.click("#transcript-paste > summary")
    page.fill("#transcript-text", TRANSCRIPT)
    page.click("#transcript-save")
    page.wait_for_function(
        "document.getElementById('ctx-transcript').textContent.includes('붙여 넣은 자막')")
    expect_next(page, "run-btn")
    page.click("#run-btn")

    # ④ 초안이 나오면(규칙 검사 통과): [이 초안 승인]
    page.wait_for_function(DRAFT_TAG.format("CHECKED"), timeout=30000)
    expect_next(page, "approve-btn")
    page.click("#approve-btn")
    page.wait_for_function(DRAFT_TAG.format("APPROVED"))

    # ⑤ 승인 뒤: 테스트 페이지 모드 → [브라우저에서 영상 열기]
    page.check('input[name="mode"][value="sandbox"]', force=True)
    expect_next(page, "job-primary")
    assert "브라우저에서 영상 열기" in page.text_content("#job-primary")
    page.click("#job-primary")

    # ⑥ 승인 대기: [게시 승인]
    page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
    expect_next(page, "job-primary")
    assert "게시 승인" in page.text_content("#job-primary")
    page.click("#job-primary")
    page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
    assert job_state(page) == "posted"

    # ⑦ 게시 완료: 다음은 다른 영상 고르기. 기록과 오늘 통계가 바로 바뀐다
    expect_next(page, "video-list")
    page.wait_for_function("document.getElementById('stat-posted').textContent.trim() === '1'")
    assert page.text_content("#stat-success").strip().startswith("100")
    rows = page.eval_on_selector_all("#records-body tr", "(rows) => rows.map((r) => r.textContent)")
    assert 1 <= len(rows) <= 5  # 첫 화면 표는 최근 5줄까지
    assert "게시 완료" in rows[0]

    # ⑧ SETTINGS: 열면 제목에 초점, Esc로 닫으면 연 단추로 초점
    page.click("#settings-open")
    page.wait_for_function("document.getElementById('settings-body').querySelector('.set-group')")
    assert page.evaluate("document.getElementById('settings-panel').open")
    assert page.evaluate("document.activeElement.id") == "settings-title"
    settings_text = page.text_content("#settings-body")
    assert "운명원" in settings_text and "[광고]" in settings_text and "fake-model" in settings_text
    assert "AIza" not in settings_text  # 키 값은 보이지 않는다
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('settings-panel').open")
    assert page.evaluate("document.activeElement.id") == "settings-open"

    # ⑨ VIEW ALL: 전체 기록(실패 사유 칸 포함), Esc로 닫기
    page.click("#records-all")
    page.wait_for_function("document.querySelectorAll('#records-all-body tr').length >= 4")
    assert page.evaluate("document.activeElement.id") == "records-title"
    assert "전체" in page.text_content("#records-all-meta")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('records-panel').open")
    assert page.evaluate("document.activeElement.id") == "records-all"

    # 강조는 끝까지 하나, 실제 유튜브는 열지 않았고 모델 미리 불러오기는 부르지 않았다
    assert page.eval_on_selector_all(".is-next", "(n) => n.length") == 1
    assert dashboard["llm"].warmups == 0
    for driver in dashboard["drivers"]:
        for url in driver.visited:
            assert url.startswith(f"{base}/sandbox/"), url
    assert not page.errors, page.errors
