"""Codex 추론 수준(2026-11-18 기획 담당 · 대표 지시).

Codex를 부를 때 추론 수준을 명령줄(`-c model_reasoning_effort=<값>`)로 준다. 기본 low,
설정 화면 「추론 수준」에서 AI별로(`llm.reasoning.<이름>`) 고른다. 고를 수 있는 값은
`codex debug models`의 모델별 `supported_reasoning_levels`(받아 오지 못하면 config.yaml
`reasoning_levels`). 사용자 config.toml은 읽지도 고치지도 않는다(`--ignore-user-config` 그대로).
진짜 Codex는 실행하지 않는다(가짜 실행기).
"""

from __future__ import annotations

import json

import pytest
from test_llm_switch_api import ANALYSIS, DRAFT, VID, ai_mock, put, youtube_mock

from app.llm import cli


@pytest.fixture
def client(make_client, mock_http, fixture_json, fake_key):
    return make_client(youtube_mock(mock_http, fixture_json), key=fake_key, llm=ai_mock(mock_http))


CATALOG = {"models": [
    {"slug": "x-sol", "visibility": "list", "default_reasoning_level": "low",
     "supported_reasoning_levels": [{"effort": e} for e in
                                    ("low", "medium", "high", "xhigh", "max", "ultra")]},
    {"slug": "x-luna", "visibility": "list", "default_reasoning_level": "medium",
     "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"},
                                    {"effort": "high"}, {"effort": "생각 많이"}]},
    {"slug": "x-plain", "visibility": "list"},
]}


def fake_codex(calls):
    state = {"n": 0}

    def runner(req):
        calls.append(req)
        if req.args[1:] == ["--version"]:
            return cli.RunResult(0, "codex-cli 9.9.9", "")
        if req.args[1:] == ["debug", "models"]:
            return cli.RunResult(0, json.dumps(CATALOG), "")
        if req.args[1:] == ["login", "status"]:
            return cli.RunResult(0, "Logged in using ChatGPT", "")
        if req.args[1:] == ["features", "list"]:  # 2026-11-18: 못 읽으면 0.152.1 이름만 끈다
            return cli.RunResult(0, "", "")
        state["n"] += 1
        return cli.RunResult(0, json.dumps(ANALYSIS if state["n"] == 1 else DRAFT), "")

    return runner


@pytest.fixture
def codex(monkeypatch):
    calls: list = []
    monkeypatch.setattr(cli, "default_which", lambda p: f"C:/fake/{p}.exe")
    monkeypatch.setattr(cli, "default_runner", fake_codex(calls))
    return calls


def efforts(calls) -> list[str]:
    out = []
    for req in calls:
        if "exec" not in req.args:
            continue
        flags = [req.args[i + 1] for i, a in enumerate(req.args) if a == "-c"]
        out.append(",".join(flags))
    return out


def test_build_args_carries_only_known_levels():
    args = cli.build_args("codex", "codex.exe", model="m", workdir=".", reasoning="low")
    i = args.index("-c")
    assert args[i + 1] == "model_reasoning_effort=low" and args[-1] == "-"
    assert "--ignore-user-config" in args  # 사용자 config.toml은 여전히 읽지 않는다
    for bad in ("", "생각 많이", "low --sandbox danger-full-access", "LOW"):
        args = cli.build_args("codex", "codex.exe", model="m", workdir=".", reasoning=bad)
        assert "-c" not in args, bad
    # Claude Code에는 넣지 않는다(이번에는 Codex만)
    args = cli.build_args("claude", "claude.exe", model="", workdir=".", reasoning="low")
    assert "-c" not in args and not any("reasoning" in a for a in args)
    assert cli.CLIClient(provider="claude-cli", label="Claude Code", program="claude",
                         reasoning="high").reasoning == ""


def test_default_is_low_and_the_saved_level_reaches_the_command(client, codex):
    providers = {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}
    assert providers["codex-cli"]["reasoning"] == "low"
    assert providers["codex-cli"]["reasoning_levels"] == ["low", "medium", "high"]
    for other in ("claude-cli", "openai", "ollama", "gemini"):
        assert providers[other]["reasoning_levels"] == [] and providers[other]["reasoning"] == ""
    assert put(client, **{"llm.active": "codex-cli"}).status_code == 200
    assert client.post(f"/api/analysis/{VID}").status_code == 200
    assert efforts(codex) == ["model_reasoning_effort=low"]
    # 「보통」으로 바꿔 저장하면 다음 실행부터
    res = put(client, **{"llm.reasoning": {"codex-cli": "medium"}})
    assert res.status_code == 200, res.text
    values = client.get("/api/settings").json()["edit"]["values"]
    assert values["llm.reasoning"] == {"codex-cli": "medium"}
    assert client.post("/api/drafts", json={"video_id": VID, "review": False}).status_code == 200
    assert efforts(codex)[-1] == "model_reasoning_effort=medium"
    # 빈 값을 보내면 지워지고 기본(low)으로 돌아간다
    assert put(client, **{"llm.reasoning": {"codex-cli": ""}}).status_code == 200
    assert client.get("/api/settings").json()["edit"]["values"]["llm.reasoning"] == {}
    providers = {p["name"]: p for p in client.get("/api/llm/providers").json()["items"]}
    assert providers["codex-cli"]["reasoning"] == "low"


@pytest.mark.parametrize("values, field", [
    ({"codex-cli": "생각 많이"}, "llm.reasoning"),
    ({"codex-cli": "minimal-ish"}, "llm.reasoning"),
    ({"claude-cli": "high"}, "llm.reasoning"),   # Claude Code는 추론 수준 칸이 없다
    ({"openai": "low"}, "llm.reasoning"),
    ({"없는것": "low"}, "llm.reasoning"),
])
def test_unsupported_levels_and_ais_are_refused(client, codex, values, field):
    res = put(client, **{"llm.reasoning": values})
    assert res.status_code == 422, res.text
    assert field in res.json()["error"]["fields"]
    assert client.get("/api/settings").json()["edit"]["values"]["llm.reasoning"] == {}


def test_model_list_carries_levels_per_model(client, codex):
    data = client.get("/api/llm/models", params={"provider": "codex-cli"}).json()
    by = {i["name"]: i for i in data["items"]}
    assert by["x-sol"]["reasoning_levels"] == ["low", "medium", "high", "xhigh", "max", "ultra"]
    assert by["x-sol"]["default_reasoning"] == "low"
    # 모르는 이름(「생각 많이」)은 뺀다
    assert by["x-luna"]["reasoning_levels"] == ["low", "medium", "high"]
    assert by["x-luna"]["default_reasoning"] == "medium"
    # 추론 수준을 알려 주지 않는 모델은 빈 목록(화면은 config.yaml 목록을 보인다)
    assert by["x-plain"]["reasoning_levels"] == [] and by["x-plain"]["default_reasoning"] == ""
    # 모델 목록은 모델을 부르지 않는다(추론 수준 인자도 없다)
    assert all("-c" not in c.args for c in codex if "debug" in c.args)
