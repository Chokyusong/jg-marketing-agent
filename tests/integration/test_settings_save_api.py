"""R2 설정 저장 API: 부분 저장·칸별 검사·초기화·바로 적용·게시 중 거절, 키 저장과 연결 확인,
설치된 모델 목록, 모니터 목록 → 창 위치 계산."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from yt_helpers import YT

from app.browser.hooks import BrowserHooks
from app.browser.screens import Monitor
from app.main import create_app
from app.user_settings import UserStore

MAIN = Monitor(0, 0, 1920, 1080, primary=True)
UPPER = Monitor(0, -1080, 1920, 0)
LEFT = Monitor(-1920, 1, 0, 1081)


def hooks(monitors=(MAIN, UPPER)):
    return BrowserHooks(
        chrome_finder=lambda: None, playwright_ready=lambda: True, screens=lambda: list(monitors)
    )


@pytest.fixture
def client(make_client):
    return make_client(key=None, browser_hooks=hooks())


def put(client, **values):
    return client.put("/api/settings", json={"values": values})


# ---------------------------------------------------------------- 읽기


def test_get_settings_has_edit_values_defaults_and_choices(client):
    edit = client.get("/api/settings").json()["edit"]
    v, d = edit["values"], edit["defaults"]
    assert v == d  # 바꾼 것이 없으면 지금 값 = 기본값
    assert v["limits.daily_max_comments"] == 10 and v["discover.query"] == "연애 고민"
    assert v["discover.shorts_under_seconds"] == 181
    assert v["comment.disclose_default"] is True and v["posting.confirm_before_post"] is False
    assert v["browser.typing_speed"] == "normal"
    assert edit["changed"] == [] and edit["store_ready"] is True
    assert edit["ranges"]["limits.daily_max_comments"] == [1, 50]
    assert [c["label"] for c in edit["typing_speeds"]] == ["느리게", "보통", "빠르게"]
    assert edit["applies_later"] == []  # R3: 광고 표기 기본값·게시 직전 확인도 바로 쓴다


def test_disclose_default_and_confirm_apply_right_away(client):
    res = put(client, **{"comment.disclose_default": False, "posting.confirm_before_post": True})
    assert res.status_code == 200, res.text
    services = client.app.state.services.get()
    assert services.drafts.disclose_default is False
    assert services.jobs.confirm_before_post is True
    browser = client.get("/api/status").json()["browser"]
    assert browser["disclose_default"] is False and browser["confirm_before_post"] is True


def test_ai_review_setting_defaults_on_and_turns_off_right_away(client):
    # 2026-11-18 AI 검수 한 번: 기본 켬, 끄면 초안 서비스가 바로 검수를 건너뛴다
    assert client.get("/api/settings").json()["edit"]["values"]["comment.ai_review"] is True
    assert client.app.state.services.get().drafts.ai_review is True
    res = put(client, **{"comment.ai_review": False})
    assert res.status_code == 200, res.text
    assert client.app.state.services.get().drafts.ai_review is False
    assert client.get("/api/settings").json()["edit"]["values"]["comment.ai_review"] is False


# ---------------------------------------------------------------- 저장·바로 적용


def test_partial_save_applies_right_away(client, user_dir):
    res = put(client, **{"limits.daily_max_comments": 3, "discover.query": "이별 고민"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["daily_max_comments"] == 3 and data["discover"]["query"] == "이별 고민"
    assert data["edit"]["changed"] == ["discover.query", "limits.daily_max_comments"]
    assert data["edit"]["defaults"]["limits.daily_max_comments"] == 10
    # 다음 요청이 새 값을 쓴다(프로그램을 다시 켜지 않는다)
    assert client.get("/api/stats/today").json()["daily_limit"] == 3
    page = client.get("/").text
    assert 'value="이별 고민"' in page and 'data-limit="3"' in page
    saved = json.loads((user_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["values"] == {"limits.daily_max_comments": 3, "discover.query": "이별 고민"}
    # 다른 칸만 저장해도 앞서 저장한 값은 남는다
    put(client, **{"discover.max_results": 20})
    data = client.get("/api/settings").json()
    assert data["daily_max_comments"] == 3 and data["discover"]["max_results"] == 20


def test_saved_values_survive_a_new_program(make_settings, client, clock):
    put(client, **{"limits.daily_max_comments": 4, "comment.disclose_default": False})
    again = create_app(make_settings(None), clock=clock, browser_hooks=hooks())
    from fastapi.testclient import TestClient

    data = TestClient(again).get("/api/settings").json()
    assert data["daily_max_comments"] == 4
    assert data["edit"]["values"]["comment.disclose_default"] is False


def test_rules_change_reaches_the_validator(client):
    put(client, **{"comment.min_chars": 10, "comment.brand": "별빛상담"})
    res = client.post("/api/validate", json={"video_id": "dQw4w9WgXcQ",
                                              "text": "[광고] 별빛상담 좋아요"})
    # 키가 없어 맥락을 못 읽는 것과 별개로, 규칙은 새 값으로 만든다
    services = client.app.state.services.get()
    assert services.checks.rules.min_chars == 10 and services.checks.rules.brand == "별빛상담"
    assert res.status_code in (200, 503)


def test_value_equal_to_default_is_not_kept(client, user_dir):
    put(client, **{"limits.daily_max_comments": 3})
    put(client, **{"limits.daily_max_comments": 10})
    assert not (user_dir / "settings.json").exists()
    assert client.get("/api/settings").json()["edit"]["changed"] == []


def test_bad_fields_are_listed_and_nothing_saved(client, user_dir):
    res = put(client, **{"limits.daily_max_comments": 99, "comment.min_chars": 500,
                         "discover.query": "연애"})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["kind"] == "settings_invalid"
    assert "1~50" in err["fields"]["limits.daily_max_comments"]
    assert "최소" in err["fields"]["comment.min_chars"]
    assert "discover.query" not in err["fields"]
    assert not (user_dir / "settings.json").exists()
    assert client.get("/api/settings").json()["discover"]["query"] == "연애 고민"


def test_reset_goes_back_to_config_but_keeps_key(client, fake_key):
    client.put("/api/settings/youtube-key", json={"key": fake_key})
    put(client, **{"limits.daily_max_comments": 2, "discover.exclude_shorts": False})
    res = client.post("/api/settings/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["daily_max_comments"] == 10 and data["discover"]["exclude_shorts"] is True
    assert data["edit"]["changed"] == []
    assert data["youtube"]["key_configured"] is True  # 키는 [지우기]로만 지운다


def test_save_is_refused_while_posting(client, user_dir):
    services = client.app.state.services.get()
    services.jobs.close_if_idle = lambda: False  # 게시 작업이 도는 중
    res = put(client, **{"limits.daily_max_comments": 3})
    assert res.status_code == 409
    err = res.json()["error"]
    assert err["kind"] == "settings_busy" and "지금 게시 중입니다" in err["message"]
    assert not (user_dir / "settings.json").exists()
    assert client.app.state.services.get() is services  # 서비스도 그대로
    assert client.post("/api/settings/reset").status_code == 409
    assert client.delete("/api/settings/youtube-key").status_code == 409


def test_save_rebuilds_services_and_keeps_test_fakes(make_client):
    seen = []
    client = make_client(key=None, browser_hooks=hooks(), on_build=seen.append)
    first = client.app.state.services.get()
    put(client, **{"discover.max_results": 30})
    second = client.app.state.services.get()
    assert second is not first and seen == [first, second]
    assert first.jobs.close_if_idle() is True  # 버린 묶음의 작업 서비스는 닫혔다


def test_model_choice_wins_over_dev_file(make_client, monkeypatch):
    client = make_client(key=None, browser_hooks=hooks())
    put(client, **{"llm.model": "qwen2.5:7b"})
    data = client.get("/api/settings").json()
    assert data["llm"]["model"] == "qwen2.5:7b"
    assert data["edit"]["defaults"]["llm.model"] != "qwen2.5:7b"


def test_shorts_seconds_reach_video_search(client):
    put(client, **{"discover.shorts_under_seconds": 61})
    assert client.app.state.services.get().videos.shorts_under_seconds == 61


# ---------------------------------------------------------------- 모니터 → 창 위치


def test_screens_list_and_choice_saves_safe_position(make_client):
    client = make_client(key=None, browser_hooks=hooks([MAIN, LEFT]))
    data = client.get("/api/screens").json()
    # 2026-11-17 창 위치 자동: 기본은 좌표 없이 「자동」
    assert data["checked"] is True and data["window_position"] == ""
    assert data["screen"] == "auto" and data["where"] == "지금은 모니터 2(왼쪽)에 뜹니다"
    labels = [i["label"] for i in data["items"]]
    assert labels == ["모니터 1 · 주 모니터 · 1920×1080", "모니터 2 · 왼쪽 모니터 · 1920×1080"]
    left = data["items"][1]
    assert left["position"] == "-1860,61" and left["current"] is False
    res = put(client, **{"browser.window_screen": left["id"]})
    assert res.status_code == 200, res.text
    b = res.json()["browser"]
    assert b["window_position"] == "-1860,61" and b["window_position_adjusted"] is False
    again = client.get("/api/screens").json()
    assert again["items"][1]["current"] is True
    assert res.json()["edit"]["values"]["browser.window_screen"] == left["id"]


def test_unknown_screen_and_typed_position_are_refused(client):
    res = put(client, **{"browser.window_screen": "1_2_3_4"})
    assert res.status_code == 422
    assert "모니터" in res.json()["error"]["fields"]["browser.window_screen"]
    res = put(client, **{"browser.window_position": "10,10"})
    assert res.status_code == 422 and "browser.window_position" in res.json()["error"]["fields"]


def test_screens_when_monitors_cannot_be_read(make_client):
    client = make_client(key=None, browser_hooks=hooks([]))
    data = client.get("/api/screens").json()
    assert {k: data[k] for k in ("checked", "window_position", "items")} == {
        "checked": False, "window_position": "", "items": []}  # 2026-11-17: 기본 좌표 없음
    assert data["screen"] == "auto"


# ---------------------------------------------------------------- 유튜브 API 키


def _assert_no_key(text: str, key: str) -> None:
    assert key not in text and key[4:] not in text


def test_save_key_never_echoes_it(client, fake_key, user_dir):
    res = client.put("/api/settings/youtube-key", json={"key": f"  {fake_key} "})
    assert res.status_code == 200
    assert res.json() == {"key_configured": True, "key_source": "program", "can_store_key": True}
    _assert_no_key(res.text, fake_key)
    for path in ("/api/settings", "/api/status", "/"):
        body = client.get(path)
        _assert_no_key(body.text, fake_key)
    settings = client.get("/api/settings").json()
    assert settings["youtube"]["key_configured"] is True
    assert settings["youtube"]["key_source"] == "program"
    for path in user_dir.rglob("*"):
        if path.is_file():
            assert fake_key.encode() not in path.read_bytes(), path


def test_saved_key_is_used_and_masked_in_logs(make_client, mock_http, fake_key, caplog):
    caplog.set_level(logging.DEBUG)
    mock = mock_http()
    mock.add("GET", f"{YT}/i18nLanguages", status_code=400, json={
        "error": {"code": 400, "message": f"API key not valid {fake_key}",
                  "errors": [{"reason": "keyInvalid"}]}})
    client = make_client(mock, key=None, browser_hooks=hooks())
    client.put("/api/settings/youtube-key", json={"key": fake_key})
    res = client.post("/api/settings/youtube-key/test")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False and data["result"] == "rejected"
    assert "받아 주지 않았습니다" in data["message"]
    assert mock.requests[0].url.params["key"] == fake_key  # 저장한 키로 불렀다
    _assert_no_key(res.text, fake_key)
    _assert_no_key(caplog.text, fake_key)


def test_key_test_ok_uses_one_unit(make_client, mock_http, fake_key):
    mock = mock_http()
    mock.add("GET", f"{YT}/i18nLanguages", json={"items": [{"id": "ko"}]})
    client = make_client(mock, key=None, browser_hooks=hooks())
    client.put("/api/settings/youtube-key", json={"key": fake_key})
    data = client.post("/api/settings/youtube-key/test").json()
    assert data["ok"] is True and data["result"] == "ok" and "연결됐습니다" in data["message"]
    assert data["quota"]["used_today"] == 1  # 검색(100)이 아니라 1
    assert [r.url.path for r in mock.requests] == [f"{YT}/i18nLanguages"]


def test_key_test_network_and_no_key(make_client, mock_http, fake_key):
    mock = mock_http()
    mock.add("GET", f"{YT}/i18nLanguages", exc=httpx.ConnectError("끊김"))
    client = make_client(mock, key=None, browser_hooks=hooks())
    data = client.post("/api/settings/youtube-key/test").json()
    assert data["result"] == "no_key" and mock.requests == []
    client.put("/api/settings/youtube-key", json={"key": fake_key})
    data = client.post("/api/settings/youtube-key/test").json()
    assert data["ok"] is False and data["result"] == "network"
    assert "인터넷" in data["message"]


def test_key_test_quota(make_client, mock_http, fake_key, fixture_json):
    mock = mock_http()
    mock.add("GET", f"{YT}/i18nLanguages", status_code=403,
             json=fixture_json("youtube/error_quota.json"))
    client = make_client(mock, key=fake_key, browser_hooks=hooks())
    assert client.post("/api/settings/youtube-key/test").json()["result"] == "quota"


def test_delete_key_falls_back_to_dev_file(make_client, fake_key):
    client = make_client(key=fake_key, browser_hooks=hooks())  # .env(환경 변수)의 키
    assert client.get("/api/settings").json()["youtube"]["key_source"] == "dev_file"
    other = "AIza" + "z" * 35
    assert client.put("/api/settings/youtube-key", json={"key": other}).json()[
        "key_source"] == "program"
    assert client.app.state.services.get().settings.youtube_api_key == other
    res = client.delete("/api/settings/youtube-key").json()
    assert res == {"key_configured": True, "key_source": "dev_file", "can_store_key": True}
    assert client.app.state.services.get().settings.youtube_api_key == fake_key


def test_delete_key_without_dev_file(client, fake_key):
    client.put("/api/settings/youtube-key", json={"key": fake_key})
    res = client.delete("/api/settings/youtube-key").json()
    assert res["key_configured"] is False and res["key_source"] is None
    assert client.get("/api/videos").json()["error"]["kind"] == "missing_key"


def test_bad_key_shape(client):
    res = client.put("/api/settings/youtube-key", json={"key": "짧은 키"})
    assert res.status_code == 422 and res.json()["error"]["kind"] == "key_bad_shape"


def test_key_save_refused_off_windows(make_config, tmp_path, fake_key, clock):
    """Windows가 아니면(암호화할 수 없으면) 저장을 거절하고 개발용 .env를 쓰라고 안내한다."""
    from fastapi.testclient import TestClient

    from app.config import load_settings
    from app.user_settings import Protector, SecretStoreUnavailable

    def off(_b):
        raise SecretStoreUnavailable("x")

    settings = load_settings(
        make_config({}), env_path=None, db_path=tmp_path / "off.sqlite3",
        environ={"JG_PROFILES_DIR": str(tmp_path / "profiles")}, user_dir=tmp_path / "user",
        protector=Protector(protect=off, unprotect=off, available=False),
    )
    client = TestClient(create_app(settings, clock=clock, browser_hooks=hooks()))
    res = client.put("/api/settings/youtube-key", json={"key": fake_key})
    assert res.status_code == 503
    err = res.json()["error"]
    assert err["kind"] == "secret_store_unavailable" and ".env" in err["action"]
    assert client.get("/api/settings").json()["youtube"]["can_store_key"] is False
    assert not (tmp_path / "user" / "youtube_key.bin").exists()


def test_user_store_is_temp_folder(client, user_dir):
    store = client.app.state.services.settings.source.store()
    assert isinstance(store, UserStore) and store.root == user_dir


# ---------------------------------------------------------------- 설치된 모델 목록


def test_models_lists_installed_with_general_first(make_client, mock_http):
    llm = mock_http()
    llm.add("GET", "/api/tags", json={"models": [
        {"name": "qwen2.5-coder:7b", "size": 4_700_000_000},
        {"name": "nomic-embed-text:latest", "size": 270_000_000},
        {"name": "qwen3.6:latest", "size": 23_000_000_000},
        {"name": "gemma3:12b", "size": 8_100_000_000},
    ]})
    client = make_client(key=None, llm=llm, browser_hooks=hooks())
    put(client, **{"llm.model": "qwen3.6"})
    data = client.get("/api/llm/models").json()
    assert data["reachable"] is True and data["current"] == "qwen3.6"
    assert data["current_installed"] is True
    names = [(i["name"], i["kind"]) for i in data["items"]]
    assert names == [("gemma3:12b", "general"), ("qwen3.6:latest", "general"),
                     ("qwen2.5-coder:7b", "code"), ("nomic-embed-text:latest", "embed")]
    assert data["items"][1]["current"] is True and data["items"][1]["size_gb"] == 23.0


def test_models_when_ollama_is_off(client):
    data = client.get("/api/llm/models").json()
    assert data["reachable"] is False and data["items"] == []


def test_choosing_auto_clears_the_old_position(make_client):
    """2026-11-17 창 위치 자동: 「자동 (권장)」을 고르면 옛 좌표를 지우고 자동으로 띄운다."""
    client = make_client(key=None, browser_hooks=hooks([MAIN, UPPER]),
                         overrides={"browser": {"window_position": "-1860,60"}})
    before = client.get("/api/screens").json()
    assert before["screen"] == "" and before["where"] == "지금은 모니터 1(주 모니터)에 뜹니다"
    assert before["auto_where"] == "지금은 모니터 2(위쪽)에 뜹니다"
    res = put(client, **{"browser.window_screen": "auto"})
    assert res.status_code == 200, res.text
    b = res.json()["browser"]
    assert b["window_screen"] == "auto" and b["window_auto"] is True
    assert b["window_position"] == "" and b["window_position_used"] == "320,-990"
    after = client.get("/api/screens").json()
    assert after["screen"] == "auto" and after["where"] == "지금은 모니터 2(위쪽)에 뜹니다"
    browser = client.app.state.services.get().settings.browser
    assert browser.window_position is None and browser.window_screen == "auto"


def test_missing_chosen_monitor_shows_fallback_note(make_client):
    client = make_client(key=None, browser_hooks=hooks([MAIN]),
                         overrides={"browser": {"window_screen": "0_-1080_1920_1080"}})
    b = client.get("/api/settings").json()["browser"]
    assert b["window_fell_back"] is True
    assert b["window_where"] == "지금은 모니터 1(주 모니터)에 뜹니다"
    assert "연결돼 있지 않아" in b["window_position_note"]
    screens = client.get("/api/screens").json()
    assert "연결돼 있지 않아" in screens["note"]
