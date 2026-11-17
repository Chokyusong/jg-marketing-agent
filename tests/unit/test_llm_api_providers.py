"""R5: API 키로 쓰는 AI(OpenAI 호환 · Claude API). 진짜 주소는 부르지 않는다(mock_http)."""

import json

import httpx
import pytest

from app.errors import AppError
from app.llm.anthropic import API_VERSION, AnthropicClient
from app.llm.openai_compatible import OpenAICompatibleClient, is_local_url

SCHEMA = {
    "type": "object",
    "properties": {"comment": {"type": "string"}},
    "required": ["comment"],
}
REPLY = {"comment": "잘 봤어요"}


def fake_key(prefix: str = "sk-") -> str:
    return prefix + "q" * 40  # 실행할 때 조립한다(진짜 키가 아니다)


def openai_reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def make_openai(mock, **kw):
    args = {
        "provider": "openai",
        "label": "ChatGPT(OpenAI)",
        "base_url": "https://api.example.test/v1",
        "model": "m-1",
        "api_key": fake_key(),
        "json_mode": True,
        "transport": mock.transport,
    }
    args.update(kw)
    return OpenAICompatibleClient(**args)


# ---------------------------------------------------------------- OpenAI 호환


def test_openai_request_shape_and_reply(mock_http):
    mock = mock_http().add("POST", "/v1/chat/completions", json=openai_reply(json.dumps(REPLY)))
    llm = make_openai(mock)
    out = llm.generate_json(system="역할", user="요청", schema=SCHEMA, max_tokens=300)
    assert out == REPLY
    req = mock.requests[0]
    assert str(req.url) == "https://api.example.test/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer " + fake_key()
    body = json.loads(req.content)
    assert body["model"] == "m-1"
    assert body["messages"][0] == {"role": "system", "content": "역할"}
    assert (
        "요청" in body["messages"][1]["content"] and '"comment"' in body["messages"][1]["content"]
    )
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_completion_tokens"] >= 300  # 생각하는 모델 몫까지 넉넉히
    assert "temperature" not in body  # 일부 모델은 받지 않는다
    llm.close()


def test_openai_json_mode_refused_retries_without(mock_http):
    mock = mock_http()
    mock.add("POST", "/v1/chat/completions", status_code=400, json={"error": {"message": "no"}})
    mock.add("POST", "/v1/chat/completions", json=openai_reply(json.dumps(REPLY)))
    llm = make_openai(mock)
    assert llm.generate_json(system="s", user="u", schema=SCHEMA) == REPLY
    second = json.loads(mock.requests[1].content)
    assert "response_format" not in second
    llm.close()


def test_gemini_shape_sends_no_extra_fields(mock_http):
    mock = mock_http().add(
        "POST",
        "/v1beta/openai/chat/completions",
        json=openai_reply("```json\n" + json.dumps(REPLY) + "\n```"),
    )
    llm = make_openai(
        mock,
        base_url="https://generativelanguage.example.test/v1beta/openai",
        json_mode=False,
        max_tokens_field="",
    )
    assert llm.generate_json(system="s", user="u", schema=SCHEMA) == REPLY
    body = json.loads(mock.requests[0].content)
    assert set(body) == {"model", "messages"}
    llm.close()


def test_bad_json_asks_once_more_then_fails(mock_http):
    mock = mock_http().add("POST", "/v1/chat/completions", json=openai_reply("그냥 글"))
    llm = make_openai(mock)
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    assert info.value.kind == "llm_bad_output"
    assert len(mock.requests) == 2
    llm.close()


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "llm_auth"),
        (403, "llm_auth"),
        (429, "llm_rate_limited"),
        (404, "llm_model_missing"),
        (500, "llm_error"),
    ],
)
def test_openai_http_errors_have_korean_text_and_hide_key(mock_http, status, kind):
    key = fake_key()
    mock = mock_http().add(
        "POST",
        "/v1/chat/completions",
        status_code=status,
        json={"error": {"message": f"bad key {key}"}},
    )
    llm = make_openai(mock, api_key=key)
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    err = info.value
    assert err.kind == kind
    assert err.message and err.action
    assert key not in err.detail and key not in err.message and key not in err.action
    llm.close()


def test_openai_network_errors(mock_http):
    mock = mock_http().add("POST", "/v1/chat/completions", exc=httpx.ReadTimeout("slow"))
    llm = make_openai(mock)
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    assert info.value.kind == "llm_timeout"
    mock2 = mock_http().add("POST", "/v1/chat/completions", exc=httpx.ConnectError("x"))
    llm2 = make_openai(mock2)
    with pytest.raises(AppError) as info2:
        llm2.generate_json(system="s", user="u", schema=SCHEMA)
    assert info2.value.kind == "llm_down"
    llm.close()
    llm2.close()


def test_openai_problems_before_any_request(mock_http):
    mock = mock_http()
    cases = [
        (dict(api_key=None), "llm_auth"),
        (dict(model=""), "llm_model_missing"),
        (dict(base_url=""), "llm_settings_invalid"),
    ]
    for kw, kind in cases:
        llm = make_openai(mock, **kw)
        with pytest.raises(AppError) as info:
            llm.generate_json(system="s", user="u", schema=SCHEMA)
        assert info.value.kind == kind
        llm.close()
    assert mock.requests == []


def test_openai_health_never_calls_out(mock_http):
    mock = mock_http()
    llm = make_openai(mock)
    h = llm.health()
    assert (h.reachable, h.installed, h.local) == (True, True, False)
    assert make_openai(mock, api_key=None).health().reachable is False
    assert mock.requests == []  # 아래 줄이 30초마다 물어도 요금이 들지 않는다
    assert llm.warmup_supported is False
    llm.close()


def test_openai_list_models(mock_http):
    mock = mock_http().add("GET", "/v1/models", json={"data": [{"id": "a-1"}, {"id": "b-2"}, {}]})
    llm = make_openai(mock)
    assert [m["name"] for m in llm.list_models()] == ["a-1", "b-2"]
    llm.close()
    bad = mock_http().add("GET", "/v1/models", status_code=401, json={"error": "no"})
    llm = make_openai(bad)
    with pytest.raises(AppError) as info:
        llm.list_models()
    assert info.value.kind == "llm_auth"
    llm.close()


def test_custom_local_address_without_key(mock_http):
    mock = mock_http().add("POST", "/v1/chat/completions", json=openai_reply(json.dumps(REPLY)))
    llm = make_openai(
        mock,
        base_url="http://127.0.0.1:1234/v1",
        api_key=None,
        key_optional=True,
        json_mode=False,
        max_tokens_field="max_tokens",
    )
    assert llm.local is True
    assert llm.generate_json(system="s", user="u", schema=SCHEMA) == REPLY
    req = mock.requests[0]
    assert "authorization" not in req.headers
    assert "max_tokens" in json.loads(req.content)
    llm.close()


@pytest.mark.parametrize(
    ("url", "local"),
    [
        ("http://127.0.0.1:1234/v1", True),
        ("http://localhost:8080", True),
        ("http://[::1]:1/v1", True),
        ("https://api.openai.com/v1", False),
        ("", False),
        ("http://192.168.0.2/v1", False),
    ],
)
def test_is_local_url(url, local):
    assert is_local_url(url) is local


# ---------------------------------------------------------------- Claude API


def make_claude(mock, **kw):
    args = {
        "provider": "claude",
        "label": "Claude(Anthropic)",
        "model": "c-1",
        "api_key": fake_key("sk-ant-"),
        "base_url": "https://anthropic.example.test",
        "transport": mock.transport,
    }
    args.update(kw)
    return AnthropicClient(**args)


def test_claude_request_shape_and_reply(mock_http):
    reply = {
        "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": json.dumps(REPLY)},
        ],
        "stop_reason": "end_turn",
    }
    mock = mock_http().add("POST", "/v1/messages", json=reply)
    llm = make_claude(mock)
    assert llm.generate_json(system="역할", user="요청", schema=SCHEMA, max_tokens=200) == REPLY
    req = mock.requests[0]
    assert req.headers["x-api-key"] == fake_key("sk-ant-")
    assert req.headers["anthropic-version"] == API_VERSION
    body = json.loads(req.content)
    assert body["model"] == "c-1" and body["system"] == "역할"
    assert body["messages"][0]["role"] == "user" and '"comment"' in body["messages"][0]["content"]
    assert body["max_tokens"] >= 200
    assert "temperature" not in body  # 이 API 버전은 받지 않는다(400)
    llm.close()


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "llm_auth"),
        (403, "llm_auth"),
        (429, "llm_rate_limited"),
        (529, "llm_rate_limited"),
        (404, "llm_model_missing"),
        (500, "llm_error"),
    ],
)
def test_claude_errors(mock_http, status, kind):
    key = fake_key("sk-ant-")
    mock = mock_http().add(
        "POST",
        "/v1/messages",
        status_code=status,
        json={"type": "error", "error": {"type": "x", "message": f"key {key}"}},
    )
    llm = make_claude(mock, api_key=key)
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    assert info.value.kind == kind
    assert key not in info.value.detail
    llm.close()


def test_claude_list_models_and_health(mock_http):
    mock = mock_http().add(
        "GET",
        "/v1/models",
        json={"data": [{"id": "c-1", "display_name": "C One"}, {"id": "c-2"}], "has_more": False},
    )
    llm = make_claude(mock)
    models = llm.list_models()
    assert [(m["name"], m["label"]) for m in models] == [("c-1", "C One"), ("c-2", None)]
    h = llm.health()
    assert (h.reachable, h.installed, h.local) == (True, True, False)
    assert len(mock.requests) == 1  # health는 묻지 않는다
    llm.close()


def test_claude_without_key_sends_nothing(mock_http):
    mock = mock_http()
    llm = make_claude(mock, api_key=None)
    with pytest.raises(AppError) as info:
        llm.generate_json(system="s", user="u", schema=SCHEMA)
    assert info.value.kind == "llm_auth"
    assert "API 키" in info.value.message
    assert mock.requests == []
    llm.close()
