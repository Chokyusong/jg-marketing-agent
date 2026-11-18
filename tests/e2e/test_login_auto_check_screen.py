"""로그인 확인 문구 고침 화면 e2e(2026-11-17): 로그인 창을 닫으면 그 카드에
「창이 닫혀 로그인을 확인하는 중입니다」와 흐린 [확인 중…]이 보이고,
끝나면 결과를 저절로 다시 읽는다.
그동안 오류(「게시 중이라 …」)는 뜨지 않는다.

- 창 없는(headless) 크롬. 로그인 창 실행기·확인기는 가짜(창을 띄우지 않고 유튜브에 가지 않는다).
"""

from __future__ import annotations

import threading

import pytest
from r1_support import headless_page, r1_server

from app.browser.login import LoginResult

pytestmark = pytest.mark.e2e

# 첫 /api/status 답을 그린 뒤. 답이 오기 전에도 윗줄은 「확인 못 함」을 그려서(아직 모름)
# 「확인 중」이 아닌 것만 보면 시작 준비 상자를 그리기 전에 읽을 수 있었다(2026-11-18 전체 실행에서
# 흔들림) — 둘 다 아닐 때까지 기다린다
STATUS_LOADED = ("!['확인 중', '확인 못 함']"
                 ".includes(document.getElementById('status-youtube').textContent)")
LOGIN_STATE = "document.querySelector('#profiles-body .card .login-state').textContent"


class FakeProc:
    def __init__(self) -> None:
        self._closed = threading.Event()

    def poll(self):
        return 0 if self._closed.is_set() else None

    def wait(self, timeout=None):
        self._closed.wait(timeout)
        return 0

    def close(self) -> None:
        self._closed.set()


class SlowChrome:
    def __init__(self) -> None:
        self.procs: list[FakeProc] = []
        self.gate = threading.Event()
        self.checks = 0

    def launcher(self, args):
        proc = FakeProc()
        self.procs.append(proc)
        return proc

    def checker(self, _path):
        self.checks += 1
        self.gate.wait(15)
        return LoginResult("signed_in", "테스트 채널")


@pytest.fixture
def chrome():
    c = SlowChrome()
    yield c
    c.gate.set()


@pytest.fixture
def app(tmp_path, make_config, fixture_json, chrome):
    with r1_server(tmp_path, make_config, fixture_json, user_dir=tmp_path / "user",
                   launcher=chrome.launcher, login_checker=chrome.checker) as served:
        yield served


def test_closing_window_shows_auto_check_then_result(app, chrome):
    base = app["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        page.click("#nav-profiles")
        page.wait_for_selector("#profile-1-login")
        page.click("#profile-1-login")
        page.wait_for_selector("#profiles-body .card .notice")
        chrome.procs[0].close()  # 사람이 창을 닫았다 → 서버가 저절로 확인(확인기에서 멈춤)
        page.wait_for_selector("#profile-1-auto", timeout=10000)
        assert "창이 닫혀 로그인을 확인하는 중입니다" in page.text_content("#profile-1-auto")
        assert page.text_content("#profiles-body .card .login-state") == "로그인 확인 중…"
        assert page.is_disabled("#profile-1-check")
        assert page.text_content("#profile-1-check") == "확인 중…"
        msg = page.text_content("#profiles-msg") or ""
        assert "게시 중" not in msg
        chrome.gate.set()
        page.wait_for_function(LOGIN_STATE + ".startsWith('로그인됨')", timeout=15000)
        assert page.locator("#profile-1-auto").count() == 0
        assert page.is_enabled("#profile-1-check")
        assert chrome.checks == 1
    assert not errors, errors
