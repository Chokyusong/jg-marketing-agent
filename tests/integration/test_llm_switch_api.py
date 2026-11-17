"""R5: 설정에서 AI 바꾸기 — 목록 · 키 저장(암호화) · 연결 확인 · 모델 목록 · 저장하면 바로 적용.

진짜 AI 회사 주소는 부르지 않는다(mock_http). 로그인된 프로그램은 가짜 실행기로 본다.
키는 실행할 때 조립한 가짜 값이고, 파일·응답·로그 어디에도 평문으로 남지 않아야 한다.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from yt_helpers import YT

from app.llm import cli

VID = "BBBBBBBBBB2"
Q_COMMENT = "하루에 한 번 연락으로 싸운 적 있어요"
ANALYSIS = {
    "has_love_concern": True,
    "reason": "댓글에 연락 다툼 고민이 있다",
    "topic": "장거리 연애 연락 문제",
    "concern": "연락 횟수 때문에 맨날 싸우는데 우리 괜찮은 걸까",
    "tone": "진지한 사연 읽기",
    "viewer_needs": "연락 다툼을 줄이는 방법",
    "evidence": [{"quote": Q_COMMENT, "source": "comment"}],
    "key_phrases": ["장거리", "하루에 한 번 연락", "기대치 차이"],
}
# C1 새 기준(시청자 말투, 핵심 말, 운명원은 들은 얘기로 꺼내기)에 맞춘 본문
BODY = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글 완전 제 얘기네요ㅠㅠ "
    "운명원 연애 사주 잘 본다던데 이번 인연은 오래 갈지 알면 좋겠어요."
)
DRAFT = {"body": BODY, "used_quote": Q_COMMENT, "tone_label": "공감형"}


def openai_key() -> str:
    return "sk-" + "t" * 20 + "R5" + "u" * 20  # 실행할 때 조립한다(진짜 키가 아니다)


def chat(obj) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": json.dumps(obj)}}]}


def ai_mock(mock_http):
    """AI 쪽 가짜 연결: Ollama는 꺼져 있고, OpenAI·Claude는 정한 답을 준다."""
    mock = mock_http()
    mock.add("GET", "/api/tags", exc=httpx.ConnectError("Ollama 꺼짐"))
    mock.add("GET", "/api/ps", exc=httpx.ConnectError("Ollama 꺼짐"))
    return mock


def youtube_mock(mock_http, fixture_json):
    mock = mock_http()
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    return mock


@pytest.fixture
def ai(mock_http):
    return ai_mock(mock_http)


@pytest.fixture
def client(make_client, ai, mock_http, fixture_json, fake_key):
    return make_client(youtube_mock(mock_http, fixture_json), key=fake_key, llm=ai)


def put(client, **values):
    return client.put("/api/settings", json={"values": values})


def by_name(client) -> dict:
    return {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}


# ---------------------------------------------------------------- 목록


def test_provider_list_groups_and_readiness(client):
    data = client.get("/api/llm/providers").json()
    assert data["active"] == "ollama"
    assert [k["label"] for k in data["kinds"]] == ["이 PC에서", "API 키로", "로그인된 프로그램으로"]
    items = by_name(client)
    assert items["ollama"]["kind"] == "local" and items["ollama"]["active"] is True
    assert items["ollama"]["local"] is True and items["ollama"]["unavailable_reason"] is None
    openai = items["openai"]
    assert openai["kind"] == "api" and openai["local"] is False and openai["needs_key"] is True
    assert openai["key_configured"] is False and openai["can_store_key"] is True
    assert openai["unavailable_reason"] == "API 키를 먼저 넣어 주세요."
    assert openai["sends_to"] == "OpenAI" and openai["model"] == ""
    assert items["custom"]["url_editable"] is True and items["custom"]["needs_key"] is False
    assert items["custom"]["unavailable_reason"] == "주소를 먼저 넣어 주세요."
    # 로그인된 프로그램: 자동 테스트에서는 설치되지 않은 것으로 보인다(진짜로 찾지 않는다)
    assert items["codex-cli"]["kind"] == "program" and items["codex-cli"]["installed"] is False
    assert items["codex-cli"]["unavailable_reason"] == "이 PC에 설치되지 않았습니다."
    assert items["codex-cli"]["models_listable"] is False
    assert items["gemini-cli"]["verified"] is False
    assert "아직 연결하지 않았습니다" in items["gemini-cli"]["unavailable_reason"]
    text = json.dumps(data, ensure_ascii=False)
    assert "api.openai.com" not in text  # 주소는 싣지 않는다


def test_cannot_choose_ai_that_is_not_ready(client, user_dir):
    for name, reason in [
        ("openai", "API 키를 먼저"),
        ("custom", "주소를 먼저"),
        ("codex-cli", "설치되지 않았습니다"),
        ("gemini-cli", "아직 연결하지 않았습니다"),
        ("없는것", "목록에 없는 AI"),
    ]:
        res = put(client, **{"llm.active": name})
        assert res.status_code == 422, name
        assert reason in res.json()["error"]["fields"]["llm.active"], name
    assert not (user_dir / "settings.json").exists()
    bad = put(client, **{"llm.models": {"openai": "--sandbox"}})
    assert bad.status_code == 422  # 「-」로 시작하는 모델 이름은 받지 않는다(명령 인자로 쓰이니까)
    bad = put(client, **{"llm.base_urls": {"openai": "http://127.0.0.1:1/v1"}})
    assert "「직접 입력」만" in bad.json()["error"]["fields"]["llm.base_urls"]


# ---------------------------------------------------- 키: 암호화 저장, 어디에도 평문 없음


def test_key_is_encrypted_and_never_shown(client, user_dir, caplog):
    key = openai_key()
    caplog.set_level(logging.DEBUG)
    res = client.put("/api/settings/llm-key/openai", json={"key": key})
    assert res.status_code == 200, res.text
    assert res.json() == {
        "name": "openai",
        "key_configured": True,
        "key_source": "program",
        "can_store_key": True,
    }
    # 파일: 사용자 폴더의 llm_keys/openai.bin에 암호화돼 있다. 어느 파일에도 평문이 없다
    assert (user_dir / "llm_keys" / "openai.bin").is_file()
    for path in user_dir.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes(), path.name
    # 응답: 목록·설정·상태 어디에도 없다
    for url in ("/api/llm/providers", "/api/settings", "/api/status", "/"):
        assert key not in client.get(url).text, url
    assert by_name(client)["openai"]["key_configured"] is True
    # 로그: 키가 섞인 줄도 가린다
    logging.getLogger("app.test").warning("보낸 머리말 Bearer %s", key)
    assert key not in caplog.text and "***" in caplog.text
    # 유튜브 키는 그대로
    assert not (user_dir / "youtube_key.bin").exists()


def test_key_delete_and_bad_shape(client, user_dir):
    assert client.put("/api/settings/llm-key/openai", json={"key": "짧음"}).status_code == 422
    assert client.put("/api/settings/llm-key/ollama", json={"key": openai_key()}).status_code == 422
    assert (
        client.put("/api/settings/llm-key/codex-cli", json={"key": openai_key()}).status_code == 422
    )
    client.put("/api/settings/llm-key/claude", json={"key": openai_key()})
    res = client.delete("/api/settings/llm-key/claude")
    assert res.status_code == 200 and res.json()["key_configured"] is False
    assert not (user_dir / "llm_keys" / "claude.bin").exists()


def test_env_key_is_dev_fallback_and_program_key_wins(make_client, ai, monkeypatch):
    env_key = "sk-" + "e" * 40
    client = make_client(llm=ai)
    # .env(개발용) 키는 make_settings가 environ으로만 받으므로 설정을 다시 만든다
    from app.config import load_settings

    holder = client.app.state.services
    src = holder.settings.source
    holder._settings = load_settings(
        src.config_path,
        src.env_path,
        db_path=src.db_path,
        environ={**(src.environ or {}), "OPENAI_API_KEY": env_key},
        user_dir=src.user_dir,
        protector=src.protector,
    )
    holder._services = None
    assert by_name(client)["openai"]["key_source"] == "dev_file"
    assert env_key not in client.get("/api/llm/providers").text
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    assert by_name(client)["openai"]["key_source"] == "program"  # 프로그램 > .env


def test_key_save_is_refused_while_posting(client):
    services = client.app.state.services.get()
    services.jobs.close_if_idle = lambda: False
    res = client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    assert res.status_code == 409 and res.json()["error"]["kind"] == "settings_busy"
    res = put(client, **{"llm.models": {"openai": "m-1"}})
    assert res.status_code == 409


# ---------------------------------------------------------------- 연결 확인 · 모델 목록


def test_connection_check_uses_model_list_only(client, ai):
    res = client.post("/api/llm/providers/openai/test")
    assert res.json()["result"] == "no_key" and res.json()["ok"] is False
    ai.add("GET", "/v1/models", json={"data": [{"id": "m-1"}, {"id": "m-2"}]})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    res = client.post("/api/llm/providers/openai/test").json()
    assert res["ok"] is True and res["result"] == "ok" and res["models"] == 2
    sent = [r for r in ai.requests if r.url.host == "api.openai.com"]
    assert [(r.method, r.url.path) for r in sent] == [("GET", "/v1/models")]  # 글 생성 없음
    assert openai_key() not in json.dumps(res)


@pytest.mark.parametrize(
    ("status", "result"), [(401, "rejected"), (429, "rate_limited"), (500, "error")]
)
def test_connection_check_failures_in_plain_words(client, ai, status, result):
    ai.add("GET", "/v1/models", status_code=status, json={"error": {"message": "x"}})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    res = client.post("/api/llm/providers/openai/test").json()
    assert res["ok"] is False and res["result"] == result and res["message"] and res["action"]


def test_models_by_provider(client, ai):
    ai.add("GET", "/v1/models", json={"data": [{"id": "z-9"}, {"id": "a-1"}]})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    data = client.get("/api/llm/models", params={"provider": "openai"}).json()
    assert data["provider"] == "openai" and data["reachable"] is True
    assert [i["name"] for i in data["items"]] == ["a-1", "z-9"]
    manual = client.get("/api/llm/models", params={"provider": "codex-cli"}).json()
    assert manual["manual_only"] is True and manual["items"] == []
    no_key = client.get("/api/llm/models", params={"provider": "claude"}).json()
    assert no_key["reachable"] is False and no_key["error"]["kind"] == "llm_auth"
    # 인자가 없으면 전과 같이 이 PC의 Ollama
    old = client.get("/api/llm/models").json()
    assert old["reachable"] is False and old["provider"] == ""


# ---------------------------------------------------- 저장하면 바로 적용 → 다른 AI로 초안


def test_switch_to_openai_applies_now_and_writes_a_draft(client, ai, user_dir):
    ai.add("POST", "/v1/chat/completions", json=chat(ANALYSIS))
    ai.add("POST", "/v1/chat/completions", json=chat(DRAFT))
    key = openai_key()
    client.put("/api/settings/llm-key/openai", json={"key": key})
    res = put(client, **{"llm.active": "openai", "llm.models": {"openai": "m-1"}})
    assert res.status_code == 200, res.text
    llm = res.json()["llm"]
    assert (llm["active"], llm["label"], llm["model"], llm["local"]) == (
        "openai",
        "ChatGPT(OpenAI)",
        "m-1",
        False,
    )
    status = client.get("/api/status").json()["ai"]
    assert status["provider"] == "openai" and status["label"] == "ChatGPT(OpenAI)"
    assert status["kind"] == "api" and status["local"] is False and status["error"] is None
    assert status["recommended_model"] == ""  # 추천 모델 안내는 Ollama만
    assert client.post("/api/llm/warmup").json()["seconds"] == 0.0  # 미리 불러올 것이 없다
    # 프로그램을 다시 켜지 않고 다음 요청이 OpenAI로 간다
    r0 = client.post(f"/api/analysis/{VID}")
    assert r0.status_code == 200, r0.text
    res = client.post("/api/drafts", json={"video_id": VID})
    assert res.status_code == 200, res.text
    assert res.json()["body"] == f"[광고] {BODY}"
    sent = [r for r in ai.requests if r.url.path == "/v1/chat/completions"]
    assert len(sent) == 2 and all(r.url.host == "api.openai.com" for r in sent)
    assert sent[0].headers["authorization"] == f"Bearer {key}"
    assert json.loads(sent[0].content)["model"] == "m-1"
    saved = json.loads((user_dir / "settings.json").read_text(encoding="utf-8"))["values"]
    assert saved["llm.active"] == "openai" and saved["llm.models"] == {"openai": "m-1"}
    assert key not in json.dumps(saved)


def test_models_merge_by_name_and_empty_removes(client):
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    put(client, **{"llm.models": {"openai": "m-1", "claude": "c-1"}})
    put(client, **{"llm.models": {"claude": ""}})
    values = client.get("/api/settings").json()["edit"]["values"]
    assert values["llm.models"] == {"openai": "m-1"}
    assert values["llm.active"] == "ollama"


def test_custom_local_address_counts_as_this_pc(client, ai):
    res = put(
        client,
        **{
            "llm.base_urls": {"custom": "http://127.0.0.1:1234/v1/"},
            "llm.models": {"custom": "local-m"},
            "llm.active": "custom",
        },
    )
    assert res.status_code == 200, res.text
    status = client.get("/api/status").json()["ai"]
    assert status["provider"] == "custom" and status["local"] is True
    assert client.get("/api/settings").json()["edit"]["values"]["llm.base_urls"] == {
        "custom": "http://127.0.0.1:1234/v1"
    }


def test_switch_to_claude_code_with_fake_runner(client, monkeypatch):
    calls = []

    def runner(req):
        calls.append(req)
        if req.args[1:] == ["--version"]:
            return cli.RunResult(0, "9.9.9 (Claude Code)", "")
        body = ANALYSIS if len([c for c in calls if "-p" in c.args]) == 1 else DRAFT
        out = {"type": "result", "is_error": False, "result": json.dumps(body)}
        return cli.RunResult(0, json.dumps(out), "")

    monkeypatch.setattr(cli, "default_which", lambda p: f"C:/fake/{p}.exe")
    monkeypatch.setattr(cli, "default_runner", runner)
    res = put(client, **{"llm.active": "claude-cli"})
    assert res.status_code == 200, res.text
    status = client.get("/api/status").json()["ai"]
    assert status["label"] == "Claude Code" and status["kind"] == "program"
    assert status["local"] is False and status["error"] is None
    assert client.post(f"/api/analysis/{VID}").status_code == 200
    assert client.post("/api/drafts", json={"video_id": VID}).status_code == 200
    runs = [c for c in calls if "-p" in c.args]
    assert len(runs) == 2
    for req in runs:
        assert req.args[req.args.index("--tools") + 1] == ""
        assert Q_COMMENT not in " ".join(req.args) and Q_COMMENT in req.input_text


def test_unknown_provider_in_api(client):
    assert client.post("/api/llm/providers/없는것/test").status_code == 503
    assert client.get("/api/llm/models", params={"provider": "없는것"}).status_code == 503



# ---------------------------------------------------------------- 모델 고르는 목록(2026-11-17)


def recommended(base_config, name):
    return base_config["llm"]["providers"][name].get("models") or []


def test_providers_carry_recommended_models_and_program_default(client, base_config):
    items = {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}
    assert items["openai"]["recommended_models"] == recommended(base_config, "openai")
    assert items["claude"]["recommended_models"] == recommended(base_config, "claude")
    assert items["openai"]["recommended_models"]  # 문서로 확인한 이름이 config.yaml에 있다
    assert items["openai"]["default_label"] == ""
    assert items["codex-cli"]["default_label"] == "기본값 (그 프로그램이 정한 모델)"
    assert items["custom"]["recommended_models"] == []  # 확인할 이름이 없으면 비워 둔다


def test_model_list_from_api_when_key_is_saved(client, ai, base_config):
    ai.add("GET", "/v1/models", json={"data": [{"id": "m-2"}, {"id": "m-1"}]})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    data = client.get("/api/llm/models", params={"provider": "openai"}).json()
    assert data["source"] == "api" and [i["name"] for i in data["items"]] == ["m-1", "m-2"]
    assert data["recommended"] == recommended(base_config, "openai") and data["note"] == ""


@pytest.mark.parametrize("status", [401, 500])
def test_model_list_failure_falls_back_to_recommended(client, ai, base_config, status):
    ai.add("GET", "/v1/models", status_code=status, json={"error": {"message": "x"}})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    data = client.get("/api/llm/models", params={"provider": "openai"}).json()
    assert data["reachable"] is False and data["items"] == []
    assert data["source"] == "recommended"
    assert data["recommended"] == recommended(base_config, "openai")
    assert data["note"].startswith("목록을 받아 오지 못해 추천 목록을 보입니다")
    assert "계정에 따라 쓸 수 없는 모델이 있을 수 있습니다" in data["note"]  # 2026-11-17


def test_model_list_without_key_shows_recommended_without_calling(client, ai, base_config):
    data = client.get("/api/llm/models", params={"provider": "claude"}).json()
    assert data["error"]["kind"] == "llm_auth" and data["source"] == "recommended"
    assert data["recommended"] == recommended(base_config, "claude")
    assert "키를 넣으면 쓸 수 있는 목록을 받아 옵니다" in data["note"]
    assert not [r for r in ai.requests if r.url.host == "api.anthropic.com"]  # 바깥에 묻지 않았다


def test_empty_api_list_also_falls_back(client, ai, base_config):
    ai.add("GET", "/v1/models", json={"data": []})
    client.put("/api/settings/llm-key/openai", json={"key": openai_key()})
    data = client.get("/api/llm/models", params={"provider": "openai"}).json()
    assert data["source"] == "recommended" and data["recommended"]


def test_no_recommended_list_leaves_only_typing(client):
    ollama = client.get("/api/llm/models", params={"provider": "ollama"}).json()
    assert ollama["reachable"] is False and ollama["source"] == "none"
    assert ollama["recommended"] == [] and "직접 입력" in ollama["note"]


def test_program_models_are_recommended_names(client, base_config):
    data = client.get("/api/llm/models", params={"provider": "claude-cli"}).json()
    assert data["manual_only"] is True and data["items"] == []
    assert data["source"] == "recommended"
    assert data["recommended"] == recommended(base_config, "claude-cli")


def test_typed_model_name_is_saved_even_if_not_in_any_list(client, base_config):
    """「직접 입력…」으로 적은 이름도 그대로 저장되고, 다시 읽어도 사라지지 않는다."""
    name = "my-own-model-9"
    assert name not in recommended(base_config, "openai")
    res = put(client, **{"llm.models": {"openai": name}})
    assert res.status_code == 200, res.text
    items = {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}
    assert items["openai"]["model"] == name
    data = client.get("/api/llm/models", params={"provider": "openai"}).json()
    assert data["current"] == name


def test_bad_recommended_entries_are_ignored():
    from app.api.ai_choice import recommended_models
    from app.config import ProviderSettings

    p = ProviderSettings("x", "openai_compatible",
                         options={"models": ["a", " a ", True, None, {"b": 1}, 7, "", "c"]})
    assert recommended_models(p) == ["a", "7", "c"]
    assert recommended_models(ProviderSettings("y", "openai_compatible",
                                               options={"models": "a,b"})) == []


def codex_runner(calls, catalog):
    def runner(req):
        calls.append(req)
        if req.args[1:] == ["--version"]:
            return cli.RunResult(0, "codex-cli 9.9.9", "")
        if req.args[1:] == ["debug", "models"]:
            return catalog if isinstance(catalog, cli.RunResult) else cli.RunResult(
                0, json.dumps(catalog), "")
        raise AssertionError(f"모델 목록 말고는 실행하지 않는다: {req.args[1:3]}")

    return runner


def test_codex_models_come_from_the_program(client, monkeypatch):
    """2026-11-17: Codex 목록은 그 프로그램에서(`codex debug models`, visibility: list만)."""
    calls = []
    catalog = {"models": [{"slug": "x-hidden", "visibility": "hide"},
                          {"slug": "x-sol", "display_name": "X-Sol", "visibility": "list"},
                          {"slug": "x-luna", "display_name": "X-Luna", "visibility": "list"}]}
    monkeypatch.setattr(cli, "default_which", lambda p: f"C:/fake/{p}.exe")
    monkeypatch.setattr(cli, "default_runner", codex_runner(calls, catalog))
    items = {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}
    assert items["codex-cli"]["models_from_program"] is True
    assert items["claude-cli"]["models_from_program"] is False
    assert items["codex-cli"]["recommended_models"] == []  # 틀린 추천 이름은 뺐다
    data = client.get("/api/llm/models", params={"provider": "codex-cli"}).json()
    assert data["source"] == "api" and data["reachable"] is True
    assert [(i["name"], i["label"]) for i in data["items"]] == [("x-sol", "X-Sol"),
                                                                ("x-luna", "X-Luna")]
    assert [c.args[1:] for c in calls if "debug" in c.args] == [["debug", "models"]]


@pytest.mark.parametrize("bad", ["{깨진", cli.RunResult(1, "", "boom")])
def test_codex_model_list_failure_leaves_default_and_typing(client, monkeypatch, bad):
    monkeypatch.setattr(cli, "default_which", lambda p: f"C:/fake/{p}.exe")
    catalog = cli.RunResult(0, bad, "") if isinstance(bad, str) else bad
    monkeypatch.setattr(cli, "default_runner", codex_runner([], catalog))
    data = client.get("/api/llm/models", params={"provider": "codex-cli"}).json()
    assert data["reachable"] is False and data["items"] == [] and data["source"] == "none"
    assert data["recommended"] == [] and "「기본값」이나 「직접 입력…」" in data["note"]
