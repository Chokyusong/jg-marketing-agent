"""GET /api/status의 ai 항목과 POST /api/llm/warmup (가짜 Ollama)."""

import httpx
import pytest


@pytest.fixture
def ollama_up(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", "/api/tags", json=fixture_json("ollama/tags.json"))
    mock.add("POST", "/api/show", json=fixture_json("ollama/show_qwen2.5_7b.json"))
    mock.add("POST", "/api/chat", json={"model": "qwen2.5:7b", "done": True, "done_reason": "load"})
    return mock


def test_status_ai_ok(make_client, ollama_up):
    res = make_client(llm=ollama_up).get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ai"] == {
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "reachable": True,
        "installed": True,
        "local": True,
        "error": None,
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
    overrides = {"llm": {"active": "claude", "providers": {"claude": {"type": "anthropic"}}}}
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
    assert (data["provider"], data["model"]) == ("ollama", "qwen2.5:7b")
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
    for text in ("aiStatusText", "꺼짐", "모델 없음", "로컬", "외부"):
        assert text in js
