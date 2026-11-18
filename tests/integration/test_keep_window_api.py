"""게시 뒤 크롬 창 열어 두기(2026-11-18 대표): 설정 · 작업 API · 로그인 창과 이어지는 곳.

- 설정: config.yaml `posting.keep_window_seconds`(기본 300초, 0이면 바로 닫기). 자동 테스트는 0
  (`tests/conftest.py`의 `base_config`). 설정 화면 「게시 뒤 크롬 창: 열어 두기(5분) / 바로 닫기」,
  저장하면 바로 적용.
- 작업 API(`GET /api/jobs/{id}`)의 `window_open`은 `test_jobs_api.py` 끝에서 본다.
- [로그인하기]·[유튜브 열기]·[로그인 확인]은 열어 둔 게시 창을 먼저 닫고 닫힌 것을 확인한다.
- 가짜 실행기·가짜 확인기만 쓴다(실제 크롬·유튜브 없음).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.browser.hooks import BrowserHooks
from app.browser.login import LoginResult
from app.browser.screens import Monitor
from app.config import load_settings

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path("C:/Fake/Chrome/chrome.exe")
KEEP = {"posting": {"keep_window_seconds": 60}}


def put(client, **values):
    return client.put("/api/settings", json={"values": values})


# ---------------------------------------------------------------- 설정


def test_repo_default_keeps_the_window_five_minutes_and_tests_close_now(make_client, tmp_path):
    settings = load_settings(ROOT / "config.yaml", env_path=None, db_path=tmp_path / "x.db")
    assert settings.keep_window_seconds == 300  # 프로그램 기본: 열어 두기(5분)
    client = make_client(key=None)
    assert client.app.state.services.get().jobs.keep_window_seconds == 0  # 자동 테스트: 바로 닫기


@pytest.mark.parametrize("bad", [-1, 3601, "300", True, 1.5])
def test_bad_keep_window_seconds_is_refused(make_config, tmp_path, bad):
    path = make_config({"posting": {"keep_window_seconds": bad}})
    with pytest.raises(ValueError, match="keep_window_seconds"):
        load_settings(path, env_path=None, db_path=tmp_path / "x.db")


def test_settings_screen_offers_keep_or_close_and_applies_right_away(make_client):
    client = make_client(key=None, overrides=KEEP)
    edit = client.get("/api/settings").json()["edit"]
    assert edit["values"]["posting.after_post_window"] == "keep"
    assert [(c["value"], c["label"]) for c in edit["after_post_windows"]] == [
        ("keep", "열어 두기(1분)"), ("close", "바로 닫기")]  # config.yaml의 초를 그대로 적는다
    assert put(client, **{"posting.after_post_window": "close"}).status_code == 200
    assert client.app.state.services.get().jobs.keep_window_seconds == 0
    assert client.get("/api/settings").json()["edit"]["values"]["posting.after_post_window"] == (
        "close")
    assert put(client, **{"posting.after_post_window": "keep"}).status_code == 200
    assert client.app.state.services.get().jobs.keep_window_seconds == 60
    assert put(client, **{"posting.after_post_window": "open"}).status_code == 422


def test_keep_choice_falls_back_to_five_minutes_when_config_says_zero(make_client):
    client = make_client(key=None)  # 자동 테스트 설정은 0초
    edit = client.get("/api/settings").json()["edit"]
    assert edit["values"]["posting.after_post_window"] == "close"
    assert edit["after_post_windows"][0]["label"] == "열어 두기(5분)"
    assert put(client, **{"posting.after_post_window": "keep"}).status_code == 200
    assert client.app.state.services.get().jobs.keep_window_seconds == 300


# ---------------------------------------------------------------- 로그인 창 · 로그인 확인


class Proc:
    def __init__(self) -> None:
        self.closed = False

    def poll(self):
        return 0 if self.closed else None

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def accounts_client(make_client):
    order: list[str] = []

    def launcher(args):
        order.append("launch")
        return Proc()

    def checker(path):
        order.append("check")
        return LoginResult("signed_in", "채널")

    hooks = BrowserHooks(
        chrome_finder=lambda: CHROME, playwright_ready=lambda: True, launcher=launcher,
        login_checker=checker, screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)],
    )
    client = make_client(key=None, browser_hooks=hooks)
    services = client.app.state.services.get()
    assert services.accounts.release_window == services.jobs.release_window  # 같은 작업 스레드
    answer = {"ok": True}

    def release():
        order.append("release")
        return answer["ok"]

    services.accounts.release_window = release
    yield client, order, answer
    services.jobs.shutdown(timeout=5)


@pytest.mark.parametrize("path", ["/api/profiles/유튜브1/login", "/api/profiles/유튜브1/open"])
def test_login_and_open_youtube_close_the_post_window_first(accounts_client, path):
    client, order, _ = accounts_client
    res = client.post(path)
    assert res.status_code == 200, res.text
    assert order[:2] == ["release", "launch"]  # (가짜 창은 바로 닫혀 저절로 확인이 뒤따른다)


def test_login_check_closes_the_post_window_first(accounts_client):
    client, order, _ = accounts_client
    res = client.post("/api/profiles/유튜브1/check")
    assert res.status_code == 200, res.text
    assert order == ["release", "check"]


def test_window_that_will_not_close_blocks_the_login_window(accounts_client):
    client, order, answer = accounts_client
    answer["ok"] = False
    res = client.post("/api/profiles/유튜브1/login")
    assert res.status_code != 200 and res.json()["error"]["kind"] == "profile_in_use"
    assert order == ["release"]  # 그 프로필 폴더로 크롬을 열지 않는다
