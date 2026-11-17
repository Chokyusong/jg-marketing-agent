"""e2e: ② 「광고 표기 붙이기」 켬/끔 — 모든 영상에서(R3, 창 없는 크롬).

- 영상을 고르면 초안이 자동으로 나오고(표기 붙음, 설정 기본값 켬) 체크를 끌 수 있다.
  끄면 글 상자 맨 앞 표기가 빠지고, 저장된 초안도 표기 없이 다시 검사돼 통과한다.
  **모델을 다시 부르지 않는다.**
- 다른 영상으로 바꿔도 끌 수 있다(처음 상태는 다시 설정 기본값).
- 설정 「광고 표기 기본값」을 끄면 새 초안이 표기 없이 나온다.
- 표기를 끈 채 [댓글 달기] 한 번 → 가짜 YouTube 페이지에 입력 → 바로 게시 완료 → 기록에
  「광고 표기 없음」(실제 YouTube에는 접속하지 않는다).
- 유튜브는 가짜 응답, AI는 가짜 LLM. 창을 띄우지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from r1_support import fake_youtube_driver
from test_dashboard_flow import (
    DRAFT,
    DRAFT_TAG,
    JOB_STATE,
    VID,
    ScriptedLLM,
    _no_real_chrome,
    _youtube,
)

from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.screens import Monitor
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app

pytestmark = pytest.mark.e2e

OTHER = "AAAAAAAAAA1"
WATCH = "https://www.youtube.com/watch?v="


@pytest.fixture
def disclose_default() -> bool:
    return True


@pytest.fixture
def base(tmp_path: Path, make_config, fixture_json, disclose_default) -> Iterator[tuple]:
    config = make_config({
        "comment": {"disclose_default": disclose_default},
        "browser": {"headless": True, "typing_delay_ms": [0, 3],
                    "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(
        config, env_path=None, db_path=tmp_path / "e2e.sqlite3",
        environ={"YOUTUBE_API_KEY": "AIza" + "x" * 35,  # 가짜 키(실행할 때 조립)
                 "JG_PROFILES_DIR": str(tmp_path / "profiles")},
    )
    assert settings.default_target == "youtube"  # 기본은 실제 게시(가짜 페이지로 돈다)
    seen: list[str] = []  # 가짜 YouTube 페이지가 받은 요청(그 밖의 요청은 막는다)
    hooks = BrowserHooks(driver_factory=default_driver_factory, launcher=_no_real_chrome,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)],
                         youtube_driver_factory=lambda b, v: fake_youtube_driver("signed_in",
                                                                                 seen, v))
    llm = ScriptedLLM()
    app = create_app(settings, transport=_youtube(fixture_json), browser_hooks=hooks,
                     on_build=lambda built: setattr(built, "llm", llm))
    services = app.state.services.get()
    services.llm = llm
    server = ServerThread(app, open_listen_socket())
    server.start()
    url = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(url, timeout=20, is_alive=server.is_alive)
    try:
        yield url, seen, llm
    finally:
        services.jobs.shutdown(timeout=15)
        server.stop()


@pytest.fixture
def page_of(base):
    from playwright.sync_api import sync_playwright

    url = base[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 창 없이
        page = browser.new_page(viewport={"width": 1920, "height": 1009})
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url)
                   else route.abort())
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(url + "/")
            page.click("#search-btn")
            page.wait_for_selector(f'.vid[data-id="{VID}"]')
            yield page, errors
        finally:
            browser.close()


def _pick(page, video_id: str) -> None:
    """고르면 초안이 자동으로 나온다(규칙 검사 통과까지 기다린다)."""
    page.click(f'.vid[data-id="{video_id}"]')
    page.wait_for_function(
        "(id) => { const c = document.getElementById('ctx-transcript');"
        " return c && c.textContent.includes('자막'); }", arg=video_id)
    page.wait_for_function(DRAFT_TAG.format("검사 통과"), timeout=30000)
    page.wait_for_function("!document.getElementById('disclose').disabled")


def _turn_off(page) -> None:
    page.uncheck("#disclose", force=True)
    page.wait_for_function(
        "(body) => document.getElementById('draft-text').value === body"
        " && document.getElementById('draft-tag').textContent === '검사 통과'",
        arg=DRAFT["body"], timeout=30000)


def test_label_can_be_turned_off_on_any_video_without_calling_the_model(base, page_of):
    _, _, llm = base
    page, errors = page_of
    _pick(page, VID)
    assert page.is_checked("#disclose")
    assert page.input_value("#draft-text") == "[광고] " + DRAFT["body"]
    calls = llm.calls
    _turn_off(page)  # 표기가 빠지고 그대로 통과
    page.wait_for_timeout(600)  # 저장(POST /disclosure)이 끝날 때까지
    assert llm.calls == calls  # 모델을 다시 부르지 않는다
    page.check("#disclose", force=True)
    page.wait_for_function(
        "(body) => document.getElementById('draft-text').value === body",
        arg="[광고] " + DRAFT["body"])
    page.wait_for_function(DRAFT_TAG.format("검사 통과"))
    assert llm.calls == calls

    # 다른 영상도 끌 수 있다(처음 상태는 설정 기본값 = 켬)
    _pick(page, OTHER)
    assert page.is_checked("#disclose")
    _turn_off(page)
    assert errors == []


@pytest.mark.parametrize("disclose_default", [False])
def test_settings_default_off_makes_drafts_without_label(base, page_of):
    page, errors = page_of
    _pick(page, VID)
    assert not page.is_checked("#disclose")
    page.wait_for_function(
        "(body) => document.getElementById('draft-text').value === body",
        arg=DRAFT["body"])
    assert errors == []


def test_post_without_label_in_one_click_and_record_says_so(base, page_of):
    _, seen, _ = base
    page, errors = page_of
    _pick(page, VID)
    _turn_off(page)
    assert not page.is_checked("#practice-mode")  # 기본은 실제 게시
    page.click("#job-primary")  # [댓글 달기] 한 번
    page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
    assert page.text_content("#exec-title").startswith("게시 완료")
    assert "확인했습니다" in page.text_content("#exec-desc")
    href = page.get_attribute("#job-view", "href")
    assert href == WATCH + VID and page.is_visible("#job-view")  # [댓글 보기] → 그 영상
    assert seen and all(u.startswith(WATCH + VID) for u in seen)
    page.wait_for_function(
        "document.getElementById('records-body').textContent.includes('광고 표기 없음')"
        " || [...document.querySelectorAll('#records-body [title]')]"
        ".some((n) => n.title.includes('광고 표기 없음'))", timeout=10000)
    assert errors == []
