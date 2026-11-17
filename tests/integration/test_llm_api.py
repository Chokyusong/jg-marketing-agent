"""GET /api/status의 ai 항목과 POST /api/llm/warmup (가짜 Ollama)."""

import httpx
import pytest


@pytest.fixture
def ollama_up(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", "/api/tags", json=fixture_json("ollama/tags.json"))
    mock.add("POST", "/api/show", json=fixture_json("ollama/show_qwen3.8_27b.json"))
    loaded = {"model": "qwen3.8:27b", "done": True, "done_reason": "load"}
    mock.add("POST", "/api/chat", json=loaded)
    return mock


def test_status_ai_ok(make_client, ollama_up):
    res = make_client(llm=ollama_up).get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ai"] == {
        "provider": "ollama",
        "model": "qwen3.8:27b",  # 기본 모델(D3, 5단계)
        "reachable": True,
        "installed": True,
        "local": True,
        "error": None,
        "loaded": None,  # R4: 불러온 모델 목록(/api/ps)을 못 읽으면 모른다
        "recommended_model": "qwen3.8:27b",
        "recommended_installed": False,  # 지금 모델이 추천 모델이면 따로 보지 않는다
        # R5: 화면에 보일 이름 · 어디서 도는지 · 영상 자료가 가는 곳
        "label": "Ollama",
        "kind": "local",
        "sends_to": "Ollama",
    }
    assert set(data["youtube"]) == {"key_configured", "quota"}  # 기존 항목은 그대로


def test_status_ai_down_by_default(make_client):
    # 자동 테스트는 llm을 주지 않으면 「Ollama 꺼짐」이다(진짜 Ollama를 부르지 않는다)
    ai = make_client().get("/api/status").json()["ai"]
    assert ai["reachable"] is False and ai["installed"] is False
    assert ai["error"]["kind"] == "llm_down"
    assert "ollama serve" in ai["error"]["action"]


def test_status_ai_model_missing(make_client, mock_http):
    mock = mock_http()
    mock.add("GET", "/api/tags", json={"models": [{"name": "llama9:1b"}]})
    ai = make_client(llm=mock).get("/api/status").json()["ai"]
    assert ai["reachable"] is True and ai["installed"] is False
    assert ai["error"]["kind"] == "llm_model_missing"
    assert "ollama pull" in ai["error"]["action"]


def test_status_ai_unknown_provider_keeps_app_up(make_client):
    # R5부터 anthropic은 지원한다 → 모르는 종류는 다른 이름으로 본다
    overrides = {"llm": {"active": "claude", "providers": {"claude": {"type": "mystery"}}}}
    client = make_client(overrides=overrides)
    res = client.get("/api/status")
    assert res.status_code == 200  # 앱은 뜨고, AI 상태가 이유를 알린다
    ai = res.json()["ai"]
    assert ai["provider"] == "claude"
    assert ai["reachable"] is False
    assert ai["error"]["kind"] == "llm_provider_unknown"
    assert client.get("/api/health").json()["status"] == "ok"
    warm = client.post("/api/llm/warmup")
    assert warm.status_code == 503
    assert warm.json()["error"]["kind"] == "llm_provider_unknown"
    assert "아직 지원하지 않는 공급자" in warm.json()["error"]["detail"]


def test_status_uses_env_model(ollama_up, make_settings, clock):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = make_settings(None)
    settings = replace(settings, llm=replace(settings.llm, ollama_model="qwen3.6"))
    client = TestClient(create_app(settings, llm_transport=ollama_up.transport, clock=clock))
    ai = client.get("/api/status").json()["ai"]
    assert ai["model"] == "qwen3.6" and ai["installed"] is True  # qwen3.6 = qwen3.6:latest


def test_status_has_no_secret_values(make_client, ollama_up, fake_key):
    fake = "sk-" + "q" * 30
    overrides = {
        "llm": {
            "providers": {"openai": {"type": "openai_compatible", "api_key_env": "OPENAI_API_KEY"}}
        }
    }
    client = make_client(key=fake_key, overrides=overrides, llm=ollama_up)
    text = client.get("/api/status").text
    assert fake_key not in text and fake not in text


def test_warmup_ok(make_client, ollama_up):
    res = make_client(llm=ollama_up).post("/api/llm/warmup")
    assert res.status_code == 200
    data = res.json()
    assert (data["provider"], data["model"]) == ("ollama", "qwen3.8:27b")
    assert data["seconds"] >= 0
    chat = [r for r in ollama_up.requests if r.url.path == "/api/chat"]
    assert len(chat) == 1 and b'"messages":[]' in chat[0].content


def test_warmup_down(make_client):
    res = make_client().post("/api/llm/warmup")
    assert res.status_code == 503
    assert res.json()["error"]["kind"] == "llm_down"


def test_warmup_timeout(make_client, mock_http, fixture_json):
    mock = mock_http()
    mock.add("POST", "/api/show", json=fixture_json("ollama/show_qwen2.5_7b.json"))
    mock.add("POST", "/api/chat", exc=httpx.ReadTimeout("느림"))
    res = make_client(llm=mock).post("/api/llm/warmup")
    assert res.status_code == 504
    assert res.json()["error"]["kind"] == "llm_timeout"


def test_warmup_model_missing(make_client, mock_http, fixture_json):
    mock = mock_http()
    mock.add(
        "POST", "/api/show", status_code=404, json=fixture_json("ollama/error_model_missing.json")
    )
    res = make_client(llm=mock).post("/api/llm/warmup")
    assert res.status_code == 503
    assert res.json()["error"]["kind"] == "llm_model_missing"


def test_dashboard_ai_status_is_wired(make_client):
    page = make_client().get("/").text
    assert 'id="status-ai"' in page and 'id="status-ai-dot"' in page
    assert "4단계에서 연결" not in page
    js = make_client().get("/static/js/topbar.js").text
    for text in ("aiStatusText", "꺼져 있음", "모델 없음", "이 PC", "외부"):
        assert text in js


# ---------------------------------------------------------------- R4 모델을 불러왔는지 · 추천 모델


def test_status_ai_loaded(make_client, ollama_up):
    ollama_up.add("GET", "/api/ps", json={"models": [{"name": "qwen3.8:27b"}]})
    ai = make_client(llm=ollama_up).get("/api/status").json()["ai"]
    assert ai["loaded"] is True


def test_llm_loaded_endpoint(make_client, ollama_up):
    ollama_up.add("GET", "/api/ps", json={"models": []})
    data = make_client(llm=ollama_up).get("/api/llm/loaded").json()
    assert data == {"provider": "ollama", "model": "qwen3.8:27b", "loaded": False,
                    "cold_timeout_seconds": 420.0}
    assert not [r for r in ollama_up.requests if r.url.path == "/api/chat"]  # 모델을 부르지 않는다


def _client_with_model(model, mock, make_settings, clock):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = make_settings(None)
    settings = replace(settings, llm=replace(settings.llm, ollama_model=model))
    return TestClient(create_app(settings, llm_transport=mock.transport, clock=clock))


def test_recommended_model_installed(mock_http, make_settings, clock):
    mock = mock_http()
    mock.add("GET", "/api/tags", json={"models": [{"name": "qwen2.5:7b"}, {"name": "qwen3.8:27b"}]})
    client = _client_with_model("qwen2.5:7b", mock, make_settings, clock)
    ai = client.get("/api/status").json()["ai"]
    assert ai["model"] == "qwen2.5:7b" and ai["installed"] is True
    assert ai["recommended_model"] == "qwen3.8:27b" and ai["recommended_installed"] is True


def test_recommended_model_not_installed(mock_http, make_settings, clock):
    mock = mock_http()
    mock.add("GET", "/api/tags", json={"models": [{"name": "qwen2.5:7b"}]})
    client = _client_with_model("qwen2.5:7b", mock, make_settings, clock)
    ai = client.get("/api/status").json()["ai"]
    assert ai["recommended_installed"] is False


# ---------------------------------------------------------------- R4 켤 때 미리 불러오기


def test_start_warmup_runs_in_background(ollama_up, make_settings, clock):
    from app.api.deps import ServiceHolder
    from app.main import start_warmup

    holder = ServiceHolder(make_settings(None), llm_transport=ollama_up.transport, clock=clock)
    thread = start_warmup(holder)
    assert thread is not None and thread.daemon
    thread.join(5)
    chat = [r for r in ollama_up.requests if r.url.path == "/api/chat"]
    assert len(chat) == 1 and b'"messages":[]' in chat[0].content
    holder.close()


def test_start_warmup_off_by_setting(ollama_up, make_settings, clock):
    from app.api.deps import ServiceHolder
    from app.main import start_warmup

    settings = make_settings(None, {"llm": {"warmup_on_start": False}})
    holder = ServiceHolder(settings, llm_transport=ollama_up.transport, clock=clock)
    assert start_warmup(holder) is None
    assert ollama_up.requests == []
    holder.close()


def test_start_warmup_failure_is_silent(make_settings, clock):
    from app.api.deps import ServiceHolder
    from app.main import start_warmup

    def down(request):
        raise httpx.ConnectError("꺼짐")

    holder = ServiceHolder(make_settings(None), llm_transport=httpx.MockTransport(down),
                           clock=clock)
    thread = start_warmup(holder)
    thread.join(5)
    assert not thread.is_alive()  # 예외 없이 끝났다
    holder.close()


def test_app_with_given_settings_does_not_warm_up(ollama_up, make_settings, clock):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(make_settings(None), llm_transport=ollama_up.transport, clock=clock)
    with TestClient(app) as client:  # lifespan이 돈다
        client.get("/api/health")
    assert not [r for r in ollama_up.requests if r.url.path == "/api/chat"]


def test_cold_and_recommend_screen_words(make_client):
    client = make_client()
    report = client.get("/static/js/report.js").text
    assert "AI 모델을 불러오는 중입니다. 처음에는 1~3분 걸립니다" in report
    assert "api.llmLoaded()" in report
    assert "/api/llm/loaded" in client.get("/static/js/api.js").text
    setup = client.get("/static/js/setup.js").text
    assert "`지금 ${ai.model} — 추천 모델 ${ai.recommended_model}로 바꾸기`" in setup
    assert "'바꾸기'" in setup and "api.saveSettings({ 'llm.model': model })" in setup
    settings = client.get("/static/js/settings.js").text
    assert "llm.warmup_on_start" in settings
