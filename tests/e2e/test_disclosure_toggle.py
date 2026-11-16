"""e2e: 02칸 「홍보 표기」 켬/끔 — 내 채널 영상(own_video_ids)에서만 끌 수 있다(창 없는 크롬).

- 내 채널 영상을 고르면 체크가 풀려(켜진 채) 끌 수 있고, 끄면 글 상자 맨 앞 표기가 빠진다.
- 표기를 끈 채 [분석하고 초안 만들기]를 누르면 표기 없는 초안이 나오고 규칙 검사를 통과한다.
- 다른 영상으로 바꾸면 체크가 켜진 채 잠기고 글 상자는 표기로 시작한다.
- 유튜브는 가짜 응답, AI는 가짜 LLM. 실제 유튜브를 여는 크롬은 막아 둔다. 창을 띄우지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from test_dashboard_flow import (
    DRAFT,
    DRAFT_TAG,
    TRANSCRIPT,
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
    hooks = BrowserHooks(driver_factory=default_driver_factory, launcher=_no_real_chrome,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)])
    app = create_app(settings, transport=_youtube(fixture_json), browser_hooks=hooks)
    services = app.state.services.get()
    services.llm = ScriptedLLM()
    server = ServerThread(app, open_listen_socket())
    server.start()
    url = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(url, timeout=20, is_alive=server.is_alive)
    try:
        yield url
    finally:
        services.jobs.shutdown(timeout=15)
        server.stop()


def _pick(page, video_id: str) -> None:
    page.click(f'.vid[data-id="{video_id}"]')
    page.wait_for_function(
        "(id) => { const c = document.getElementById('ctx-transcript');"
        " return c && c.textContent.includes('자막'); }", arg=video_id)


def test_disclosure_can_be_turned_off_only_on_own_video(base):
    from playwright.sync_api import sync_playwright

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

            # 내 채널 영상: 체크가 풀린다(켜진 채)
            _pick(page, VID)
            page.wait_for_function("!document.getElementById('disclose').disabled")
            assert page.is_checked("#disclose")
            assert page.input_value("#draft-text").startswith("[광고]")

            # 끄면 글 상자 맨 앞 표기가 빠진다
            page.uncheck("#disclose", force=True)
            assert not page.input_value("#draft-text").startswith("[광고]")

            # 표기를 끈 채 초안 만들기 → 표기 없는 초안이 규칙 검사 통과
            page.click("#transcript-paste > summary")
            page.fill("#transcript-text", TRANSCRIPT)
            page.click("#transcript-save")
            page.wait_for_function(
                "document.getElementById('ctx-transcript').textContent.includes('붙여 넣은 자막')")
            page.click("#run-btn")
            page.wait_for_function(DRAFT_TAG.format("CHECKED"), timeout=30000)
            assert page.input_value("#draft-text") == DRAFT["body"]
            assert not page.is_checked("#disclose")

            # 다른 영상: 켜진 채 잠기고 글 상자는 표기로 시작
            _pick(page, OTHER)
            page.wait_for_function("document.getElementById('disclose').disabled")
            assert page.is_checked("#disclose")
            assert page.input_value("#draft-text").startswith("[광고]")
            assert errors == []
        finally:
            browser.close()
