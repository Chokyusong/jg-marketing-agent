"""9단계 SETTINGS 패널 API(`GET /api/settings`): 읽기 전용 설정값. 키·경로·LLM 주소가 없다."""

from __future__ import annotations

import json

from app.browser.hooks import BrowserHooks
from app.browser.screens import Monitor

MAIN = Monitor(0, 0, 1920, 1080, primary=True)
UPPER = Monitor(0, -1080, 1920, 0)


def hooks(monitors, chrome=None):
    return BrowserHooks(
        chrome_finder=lambda: chrome, playwright_ready=lambda: True, screens=lambda: monitors
    )


def test_settings_shows_rules_profiles_model_and_limits(make_client, tmp_path):
    client = make_client(key=None, browser_hooks=hooks([MAIN, UPPER]))
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "0.9.0" and data["stage"] == 9
    assert data["comment"] == {"min_chars": 40, "max_chars": 120, "disclosure": "[광고]",
                               "brand": "운명원", "own_video_count": 0}
    assert data["brand_facts"] == ["운명원은 연애 사주를 잘 봐주는 곳으로 "
        "유명하다"]  # 2026-11-17 과제 원문 소개로 바꿈
    assert data["daily_max_comments"] == 10
    assert [p["name"] for p in data["profiles"]] == ["유튜브1", "유튜브2", "유튜브3"]
    assert [p["folder"] for p in data["profiles"]] == ["profile-1", "profile-2", "profile-3"]
    assert all(p["ready"] is False for p in data["profiles"])  # 임시 프로필 폴더는 비어 있다
    llm = data["llm"]
    assert llm["active"] == "ollama" and llm["type"] == "ollama" and llm["local"] is True
    assert llm["model"]  # 설정의 모델 이름(모델을 부르지 않는다)
    assert data["youtube"]["key_configured"] is False
    assert data["youtube"]["quota"]["daily_limit"] == 10000
    assert data["discover"]["query"] == "연애 고민"
    assert data["transcript_provider"] == "auto"  # R4: 자막 자동으로 읽기가 기본
    b = data["browser"]
    # 2026-11-17 창 위치 자동: 좌표는 비고 「자동」으로 위쪽 모니터에 뜬다
    assert b["window_position"] == "" and b["window_screen"] == "auto" and b["window_auto"] is True
    assert b["window_position_used"] == "320,-990" and b["window_position_adjusted"] is False
    assert b["window_where"] == "지금은 모니터 2(위쪽)에 뜹니다"
    assert b["window_size_used"] == "1280×900" and b["window_fell_back"] is False
    assert b["chrome_found"] is False and b["playwright_ready"] is True


def test_settings_reports_window_moved_on_single_monitor(make_client):
    # 2026-11-17: 옛 판이 저장한 좌표가 남은 경우(옛 방식 그대로)
    client = make_client(key=None, browser_hooks=hooks([MAIN]),
                         overrides={"browser": {"window_position": "60,-1060"}})
    b = client.get("/api/settings").json()["browser"]
    assert b["window_position"] == "60,-1060"
    assert b["window_position_used"] == "60,60"
    assert b["window_position_adjusted"] is True and b["window_position_checked"] is True
    assert "화면 밖" in b["window_position_note"]


def test_settings_profile_ready_follows_folder(make_client, tmp_path):
    client = make_client(key=None, browser_hooks=hooks([MAIN]))
    services = client.app.state.services.get()
    (services.settings.browser.profiles_root / "profile-2").mkdir(parents=True)
    ready = [p["ready"] for p in client.get("/api/settings").json()["profiles"]]
    assert ready == [False, True, False]


def test_settings_does_not_call_the_model(make_client):
    # LLM 호출이 일어나면 실패하는 가짜를 끼워도 설정 응답은 그대로 온다
    client = make_client(key=None, browser_hooks=hooks([MAIN]))
    services = client.app.state.services.get()

    class Boom:
        provider, model, local = "ollama", "boom-model", True

        def __getattr__(self, name):
            raise AssertionError(f"설정 API가 LLM의 {name}을 불렀다")

    services.llm = Boom()
    assert client.get("/api/settings").json()["llm"]["model"] == "boom-model"


def test_settings_has_no_secrets_or_paths(make_client, fake_key, tmp_path, monkeypatch):
    llm_key = "sk-" + "y" * 40
    monkeypatch.setenv("FAKE_LLM_KEY", llm_key)
    overrides = {"llm": {"active": "ollama", "providers": {
        "ollama": {"type": "ollama"},
        "other": {"type": "openai_compatible", "api_key_env": "FAKE_LLM_KEY"},
    }}}
    chrome = tmp_path / "Google" / "Chrome" / "chrome.exe"
    client = make_client(key=fake_key, overrides=overrides,
                         browser_hooks=hooks([MAIN], chrome=chrome))
    services = client.app.state.services.get()
    text = client.get("/api/settings").text
    data = json.loads(text)
    assert data["youtube"]["key_configured"] is True
    assert data["browser"]["chrome_found"] is True
    for secret in (fake_key, llm_key, "AIza", "sk-"):
        assert secret not in text
    for path in (str(tmp_path), str(services.settings.db_path), str(chrome),
                 str(services.settings.browser.profiles_root), "AppData", "11434",
                 "127.0.0.1", "http"):
        assert path not in text, path
    assert "\\\\" not in text and ":/" not in text  # 경로처럼 보이는 글자도 없다
