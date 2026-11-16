"""e2e: ② 「광고 표기 붙이기」 켬/끔 — 내 채널 영상(own_video_ids)에서만 끌 수 있다(창 없는 크롬).

- 내 채널 영상을 고르면 초안이 자동으로 나오고(표기 붙음), 체크가 풀려(켜진 채) 끌 수 있다.
  끄면 글 상자 맨 앞 표기가 빠진다.
- 표기를 끈 채 [다른 댓글 만들기]를 누르면 표기 없는 초안이 나오고 규칙 검사를 통과한다.
- 다른 영상으로 바꾸면 체크가 켜진 채 잠기고 초안은 표기로 시작한다.
- 내 채널 영상에서 연습 모드를 끄면(실제 유튜브) 자동 게시(youtube_auto)로 돈다:
  [댓글 달기] → 가짜 YouTube 페이지에 입력 → [게시] → 게시 완료(실제 YouTube에는 접속하지 않는다).
- 유튜브는 가짜 응답, AI는 가짜 LLM. 실제 유튜브를 여는 크롬은 막아 둔다. 창을 띄우지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from test_dashboard_flow import (
    DRAFT,
    DRAFT_TAG,
    JOB_STATE,
    VID,
    ScriptedLLM,
    _no_real_chrome,
    _youtube,
)
from test_youtube_auto_flow import WATCH, make_driver

from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.screens import Monitor
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.main import create_app

pytestmark = pytest.mark.e2e

OTHER = "AAAAAAAAAA1"


@pytest.fixture
def base(tmp_path: Path, make_config, fixture_json) -> Iterator[str]:
    config = make_config({
        "own_video_ids": [VID],
        "browser": {"headless": True, "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(
        config, env_path=None, db_path=tmp_path / "e2e.sqlite3",
        environ={"YOUTUBE_API_KEY": "AIza" + "x" * 35,  # 가짜 키(실행할 때 조립)
                 "JG_PROFILES_DIR": str(tmp_path / "profiles")},
    )
    seen: list[str] = []  # 가짜 YouTube 페이지가 받은 요청(그 밖의 요청은 막는다)
    hooks = BrowserHooks(driver_factory=default_driver_factory, launcher=_no_real_chrome,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)],
                         youtube_driver_factory=lambda b, v: make_driver("signed_in", seen, v))
    app = create_app(settings, transport=_youtube(fixture_json), browser_hooks=hooks)
    services = app.state.services.get()
    services.llm = ScriptedLLM()
    server = ServerThread(app, open_listen_socket())
    server.start()
    url = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(url, timeout=20, is_alive=server.is_alive)
    try:
        yield url, seen
    finally:
        services.jobs.shutdown(timeout=15)
        server.stop()


def _pick(page, video_id: str) -> None:
    """고르면 초안이 자동으로 나온다(규칙 검사 통과까지 기다린다)."""
    page.click(f'.vid[data-id="{video_id}"]')
    page.wait_for_function(
        "(id) => { const c = document.getElementById('ctx-transcript');"
        " return c && c.textContent.includes('자막'); }", arg=video_id)
    page.wait_for_function(DRAFT_TAG.format("검사 통과"), timeout=30000)


def _draft_without_disclosure(page) -> None:
    """표기를 끄고 [다른 댓글 만들기] → 표기 없는 초안."""
    page.wait_for_function("!document.getElementById('disclose').disabled")
    page.uncheck("#disclose", force=True)
    assert not page.input_value("#draft-text").startswith("[광고]")
    page.click("#another-btn")
    page.wait_for_function(
        "(body) => document.getElementById('draft-text').value === body"
        " && document.getElementById('draft-tag').textContent === '검사 통과'",
        arg=DRAFT["body"], timeout=30000)


def test_disclosure_can_be_turned_off_only_on_own_video(base):
    from playwright.sync_api import sync_playwright

    base, _ = base

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 창 없이
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                   else route.abort())
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(base + "/")
            page.click("#search-btn")
            page.wait_for_selector(f'.vid[data-id="{VID}"]')

            # 내 채널 영상: 초안은 표기로 시작하고, 체크가 풀린다(켜진 채)
            _pick(page, VID)
            page.wait_for_function("!document.getElementById('disclose').disabled")
            assert page.is_checked("#disclose")
            assert page.input_value("#draft-text").startswith("[광고]")

            # 끄면 글 상자 맨 앞 표기가 빠지고, 그 채로 [다른 댓글 만들기] → 표기 없는 초안이 통과
            _draft_without_disclosure(page)
            assert not page.is_checked("#disclose")

            # 다른 영상: 켜진 채 잠기고 초안은 표기로 시작
            _pick(page, OTHER)
            page.wait_for_function("document.getElementById('disclose').disabled")
            assert page.is_checked("#disclose")
            assert page.input_value("#draft-text").startswith("[광고]")
            assert errors == []
        finally:
            browser.close()


def test_own_video_youtube_mode_auto_posts_after_approval(base):
    from playwright.sync_api import sync_playwright

    base, seen = base
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 창 없이
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                   else route.abort())
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(base + "/")
            page.click("#search-btn")
            page.wait_for_selector(f'.vid[data-id="{VID}"]')
            _pick(page, VID)
            _draft_without_disclosure(page)

            # 연습 모드를 끄면 실제 유튜브: 내 채널 영상이라 자동으로 입력하고 게시한다
            page.uncheck("#practice-mode", force=True)
            page.wait_for_function(
                "document.getElementById('job-status').textContent.includes('내 채널 영상')")
            page.click("#job-primary")  # [댓글 달기]
            page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
            assert page.text_content("#job-primary") == "게시"
            assert page.text_content("#draft-tag") == "승인됨"
            assert "유튜브" in page.text_content("#exec-title")
            page.click("#job-primary")
            page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
            assert "확인됨" in page.text_content("#exec-title")
            assert seen and all(u.startswith(WATCH + VID) for u in seen)
            assert errors == []
        finally:
            browser.close()
