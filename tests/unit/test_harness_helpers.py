"""conftest 도우미와 저장소 설정 파일 자체를 확인한다."""

import httpx
import pytest
import yaml


def test_config_yaml_matches_design(base_config):
    # DESIGN 8절의 핵심 값
    assert base_config["profiles"] == ["유튜브1", "유튜브2", "유튜브3"]
    assert base_config["comment"] == {
        "min_chars": 40,
        "max_chars": 120,
        "brand": "운명원",
        "disclosure": "[광고]",
    }
    assert base_config["limits"]["daily_max_comments"] == 10
    assert base_config["browser"]["default_target"] == "sandbox"
    assert base_config["browser"]["window_position"] == "60,-1060"
    assert base_config["transcript"]["provider"] == "manual"


def test_make_config_overrides_only_given_keys(make_config, base_config):
    path = make_config({"limits": {"daily_max_comments": 2}})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["limits"]["daily_max_comments"] == 2
    assert data["comment"] == base_config["comment"]
    assert base_config["limits"]["daily_max_comments"] == 10  # 원본은 그대로


def test_tmp_db_path_is_isolated(tmp_db_path, tmp_path):
    assert tmp_db_path.parent == tmp_path
    assert not tmp_db_path.exists()


def test_clean_env_removes_secrets(monkeypatch, request):
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")
    request.getfixturevalue("clean_env")
    import os

    assert "YOUTUBE_API_KEY" not in os.environ


def test_fake_llm_returns_in_order_and_records(fake_llm):
    llm = fake_llm([{"a": 1}, ValueError("깨진 JSON"), {"b": 2}])
    assert llm.generate_json("p1", temperature=0.2) == {"a": 1}
    with pytest.raises(ValueError):
        llm.generate_json("p2")
    assert llm.generate_json("p3") == {"b": 2}
    assert [c["args"][0] for c in llm.calls] == ["p1", "p2", "p3"]
    assert llm.calls[0]["kwargs"] == {"temperature": 0.2}
    with pytest.raises(AssertionError):
        llm.generate_json("too many")


def test_mock_http_routes_and_records(mock_http):
    mock = mock_http()
    mock.add("GET", "/v3/search", json={"items": [1]})
    mock.add("GET", "/v3/videos", status_code=403, json={"error": "quota"})
    mock.add("GET", "/v3/videos", json={"items": []})
    with mock.client() as client:
        assert client.get("/v3/search", params={"q": "연애"}).json() == {"items": [1]}
        assert client.get("/v3/videos").status_code == 403
        assert client.get("/v3/videos").status_code == 200
        assert client.get("/v3/videos").status_code == 200  # 마지막 응답 반복
        with pytest.raises(AssertionError):
            client.get("/not-registered")
    assert mock.requests[0].url.params["q"] == "연애"


def test_mock_http_can_raise_network_error(mock_http):
    mock = mock_http()
    mock.add("GET", "/x", exc=httpx.ConnectError("down"))
    with mock.client() as client, pytest.raises(httpx.ConnectError):
        client.get("/x")
