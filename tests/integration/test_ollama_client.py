"""Ollama 공급자(`app/llm/ollama.py`)를 가짜 Ollama(`mock_http`)로 시험한다.

응답 본문은 이 PC의 Ollama 0.34.0에서 받은 것을 줄여 저장했다(`tests/fixtures/ollama/`).
"""

import json

import httpx
import pytest

from app.errors import AppError
from app.llm.ollama import OllamaClient, same_model

SCHEMA = {
    "type": "object",
    "properties": {"concern": {"type": "string"}},
    "required": ["concern"],
}
BASE = "http://127.0.0.1:11434"


def chat_reply(content: str) -> dict:
    return {"model": "m", "message": {"role": "assistant", "content": content}, "done": True}


@pytest.fixture
def ollama(mock_http, fixture_json):
    """생각 기능이 없는 qwen2.5:7b처럼 답하는 가짜 Ollama."""
    mock = mock_http()
    mock.add("POST", "/api/show", json=fixture_json("ollama/show_qwen2.5_7b.json"))
    return mock


def make(mock, **kwargs) -> OllamaClient:
    kwargs.setdefault("model", "qwen2.5:7b")
    return OllamaClient(base_url=BASE, transport=mock.transport, **kwargs)


def chat_bodies(mock) -> list[dict]:
    return [json.loads(r.content) for r in mock.requests if r.url.path == "/api/chat"]


def ask(client: OllamaClient) -> dict:
    return client.generate_json(
        system="시스템", user="질문", schema=SCHEMA, temperature=0.3, max_tokens=99
    )


# ---------------------------------------------------------------- 정상과 재시도


def test_ok_with_saved_reply(ollama, fixture_json):
    ollama.add("POST", "/api/chat", json=fixture_json("ollama/chat_ok.json"))
    assert ask(make(ollama)) == {"concern": "상대방과의 소통이 부족해 관계가 식어가는 것 같아요."}
    assert len(chat_bodies(ollama)) == 1


def test_request_shape(ollama):
    ollama.add("POST", "/api/chat", json=chat_reply('{"concern": "x"}'))
    ask(make(ollama, num_ctx=4096, keep_alive="10m"))
    body = chat_bodies(ollama)[0]
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert body["format"] == SCHEMA  # 구조화 출력: format에 JSON 스키마
    assert body["options"] == {"temperature": 0.3, "num_ctx": 4096, "num_predict": 99}
    assert body["keep_alive"] == "10m"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == "시스템"
    assert body["messages"][1]["content"].startswith("질문")
    assert '"required": ["concern"]' in body["messages"][1]["content"]  # 프롬프트에도 스키마
    assert "think" not in body  # 생각 기능이 없는 모델에는 싣지 않는다


def test_thinking_model_gets_think_false(mock_http, fixture_json):
    mock = mock_http()
    mock.add("POST", "/api/show", json=fixture_json("ollama/show_qwen3.8_27b.json"))
    mock.add("POST", "/api/chat", json=chat_reply('{"concern": "x"}'))
    client = make(mock, model="qwen3.8:27b")
    ask(client)
    ask(client)
    assert all(b["think"] is False for b in chat_bodies(mock))
    shows = [r for r in mock.requests if r.url.path == "/api/show"]
    assert len(shows) == 1  # 기능 목록은 한 번만 읽는다
    assert json.loads(shows[0].content) == {"model": "qwen3.8:27b"}


@pytest.mark.parametrize(
    ("values", "expected"),
    [([False, True], False), (["low", "medium", "high"], False), ([False], None)],
)
def test_thinking_values_from_show(mock_http, values, expected):
    mock = mock_http()
    mock.add(
        "POST",
        "/api/show",
        json={"capabilities": ["completion"], "thinking": {"values": values, "default": values[0]}},
    )
    mock.add("POST", "/api/chat", json=chat_reply('{"concern": "x"}'))
    ask(make(mock))
    assert chat_bodies(mock)[0].get("think") is expected


def test_broken_json_then_retry_ok(ollama):
    ollama.add("POST", "/api/chat", json=chat_reply("음... 고민은 연락이에요"))
    ollama.add("POST", "/api/chat", json=chat_reply('```json\n{"concern": "연락"}\n```'))
    assert ask(make(ollama)) == {"concern": "연락"}
    bodies = chat_bodies(ollama)
    assert len(bodies) == 2
    assert "다시 요청" in bodies[1]["messages"][1]["content"]
    assert bodies[1]["format"] == SCHEMA


def test_both_broken_is_bad_output(ollama):
    ollama.add("POST", "/api/chat", json=chat_reply("깨진 답"))
    ollama.add("POST", "/api/chat", json=chat_reply('{"other": 1}'))
    with pytest.raises(AppError) as info:
        ask(make(ollama))
    assert info.value.kind == "llm_bad_output"
    assert info.value.http_status == 502
    assert len(chat_bodies(ollama)) == 2  # 처음 + 한 번만 다시


def test_thinking_only_reply_counts_as_broken(ollama):
    # 생각만 하고 답(content)이 비면 깨진 답으로 보고 다시 시킨다
    ollama.add(
        "POST",
        "/api/chat",
        json={"message": {"role": "assistant", "content": "", "thinking": "..."}},
    )
    ollama.add("POST", "/api/chat", json=chat_reply('{"concern": "ok"}'))
    assert ask(make(ollama)) == {"concern": "ok"}


# ---------------------------------------------------------------- 연결 오류


def test_timeout(ollama):
    ollama.add("POST", "/api/chat", exc=httpx.ReadTimeout("느림"))
    with pytest.raises(AppError) as info:
        ask(make(ollama, timeout_seconds=1))
    assert info.value.kind == "llm_timeout"
    assert info.value.http_status == 504
    assert "ollama serve" not in info.value.action  # 시간 초과 안내는 따로


def test_server_down(mock_http):
    mock = mock_http()
    mock.add("POST", "/api/show", exc=httpx.ConnectError("refused"))
    with pytest.raises(AppError) as info:
        ask(make(mock))
    assert info.value.kind == "llm_down"
    assert "ollama serve" in info.value.action
    assert "OLLAMA_BASE_URL" in info.value.action


def test_model_missing_on_show(mock_http, fixture_json):
    mock = mock_http()
    mock.add(
        "POST", "/api/show", status_code=404, json=fixture_json("ollama/error_model_missing.json")
    )
    with pytest.raises(AppError) as info:
        ask(make(mock, model="nope:1b"))
    assert info.value.kind == "llm_model_missing"
    assert "ollama pull" in info.value.action
    assert "not found" in info.value.detail
    assert not chat_bodies(mock)  # 모델이 없으면 /api/chat까지 가지 않는다


def test_model_missing_on_chat(ollama, fixture_json):
    ollama.add(
        "POST", "/api/chat", status_code=404, json=fixture_json("ollama/error_model_missing.json")
    )
    with pytest.raises(AppError) as info:
        ask(make(ollama))
    assert info.value.kind == "llm_model_missing"


def test_other_server_error(ollama):
    ollama.add("POST", "/api/chat", status_code=500, json={"error": "out of memory"})
    with pytest.raises(AppError) as info:
        ask(make(ollama))
    assert info.value.kind == "llm_error"
    assert "HTTP 500 out of memory" in info.value.detail


def test_secret_values_are_redacted_from_detail(ollama):
    secret = "sk-" + "y" * 30  # 실행할 때 조립한다
    ollama.add("POST", "/api/chat", status_code=500, json={"error": f"bad header {secret}"})
    with pytest.raises(AppError) as info:
        ask(make(ollama, secrets=[secret]))
    assert secret not in info.value.detail
    assert "***" in info.value.detail


# ---------------------------------------------------------------- 상태와 불러 두기


def test_health_ok_and_installed(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", "/api/tags", json=fixture_json("ollama/tags.json"))
    health = make(mock).health()
    assert health.to_dict() == {
        "provider": "ollama",
        "model": "qwen2.5:7b",
        "reachable": True,
        "installed": True,
        "local": True,
    }


def test_health_model_not_installed(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", "/api/tags", json=fixture_json("ollama/tags.json"))
    health = make(mock, model="llama9:1b").health()
    assert health.reachable is True and health.installed is False


def test_health_latest_tag_is_same_model(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", "/api/tags", json=fixture_json("ollama/tags.json"))
    assert make(mock, model="qwen3.6").health().installed is True
    assert same_model("qwen3.6", "qwen3.6:latest")
    assert not same_model("qwen3.6", "qwen3.8:27b")


def test_health_down(mock_http):
    mock = mock_http()
    mock.add("GET", "/api/tags", exc=httpx.ConnectError("refused"))
    health = make(mock).health()
    assert health.reachable is False and health.installed is False


def test_health_server_error_is_unreachable(mock_http):
    mock = mock_http()
    mock.add("GET", "/api/tags", status_code=500, text="oops")
    assert make(mock).health().reachable is False


def test_warmup_loads_model_with_empty_messages(ollama):
    ollama.add(
        "POST", "/api/chat", json={"model": "qwen2.5:7b", "done": True, "done_reason": "load"}
    )
    seconds = make(ollama, keep_alive="30m").warmup()
    assert seconds >= 0
    body = chat_bodies(ollama)[0]
    assert body == {"model": "qwen2.5:7b", "messages": [], "stream": False, "keep_alive": "30m"}


def test_unload_uses_keep_alive_zero(ollama):
    ollama.add("POST", "/api/chat", json={"done": True, "done_reason": "unload"})
    make(ollama).unload()
    assert chat_bodies(ollama)[0]["keep_alive"] == 0
