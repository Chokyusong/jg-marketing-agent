"""LLM 등록부와 설정: llm.active로 고르기, 모르는 종류, 옛 설정 키, api_key_env 가리기."""

import ast
from pathlib import Path

import pytest

from app.config import load_settings
from app.errors import AppError
from app.llm.base import LLMClient
from app.llm.ollama import OllamaClient
from app.llm.registry import build_llm, supported_types

ROOT = Path(__file__).resolve().parents[2]


def settings_with(make_config, llm: dict | None, environ: dict | None = None, *, replace=False):
    """config.yaml의 llm 절을 바꾼 설정. replace=True면 llm 절을 통째로 바꾼다."""
    path = make_config({} if replace else {"llm": llm or {}})
    if replace:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["llm"] = llm
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return load_settings(path, env_path=None, environ=environ or {})


def test_repo_config_builds_ollama(clean_env, tmp_path):
    settings = load_settings(env_path=tmp_path / "없음.env", environ={})
    assert settings.llm.active == "ollama"
    assert settings.llm.timeout_seconds == 180
    assert settings.llm.num_ctx == 8192
    assert settings.llm.keep_alive == "30m"
    assert settings.context_chars == 6000
    llm = build_llm(settings)
    try:
        assert isinstance(llm, LLMClient)
        assert isinstance(llm, OllamaClient)
        assert (llm.provider, llm.model, llm.local) == ("ollama", "qwen3.8:27b", True)
        assert llm.base_url == "http://127.0.0.1:11434"
        assert llm.timeout_seconds == 180
    finally:
        llm.close()


def test_env_sets_ollama_address_and_model(make_config):
    environ = {"OLLAMA_BASE_URL": "http://10.0.0.5:11434/", "OLLAMA_MODEL": "qwen3.8:27b"}
    settings = load_settings(make_config(), env_path=None, environ=environ)
    llm = build_llm(settings)
    assert llm.model == "qwen3.8:27b"
    assert llm.base_url == "http://10.0.0.5:11434"
    llm.close()


def test_active_picks_named_provider(make_config):
    settings = settings_with(
        make_config,
        {
            "active": "big",
            "providers": {
                "ollama": {"type": "ollama"},
                "big": {"type": "ollama", "model": "qwen3.6:latest"},
            },
        },
    )
    llm = build_llm(settings)
    assert (llm.provider, llm.model) == ("big", "qwen3.6:latest")
    llm.close()


def test_other_provider_types_do_not_stop_the_app(make_config):
    # 12단계 종류가 적혀 있어도 고른 것이 ollama면 그대로 뜬다
    settings = settings_with(
        make_config,
        {
            "active": "ollama",
            "providers": {
                "ollama": {"type": "ollama"},
                "claude": {"type": "anthropic", "model": "", "api_key_env": "ANTHROPIC_API_KEY"},
                "codex-cli": {"type": "cli", "command": []},
            },
        },
    )
    llm = build_llm(settings)
    assert llm.provider == "ollama"
    llm.close()


def test_unknown_type_is_clear_error(make_config):
    settings = settings_with(
        make_config,
        {
            "active": "claude",
            # R5부터 anthropic은 지원한다 → 모르는 종류는 다른 이름으로 본다
            "providers": {"ollama": {"type": "ollama"}, "claude": {"type": "mystery"}},
        },
    )
    with pytest.raises(AppError) as info:
        build_llm(settings)
    assert info.value.kind == "llm_provider_unknown"
    assert "아직 지원하지 않는 공급자" in info.value.detail
    assert "mystery" in info.value.detail and "ollama" in info.value.detail


def test_active_not_in_providers(make_config):
    settings = settings_with(
        make_config, {"active": "없는것", "providers": {"ollama": {"type": "ollama"}}}
    )
    with pytest.raises(AppError) as info:
        build_llm(settings)
    assert info.value.kind == "llm_provider_unknown"
    assert "llm.providers에 없습니다" in info.value.detail


def test_old_provider_key_still_reads(make_config):
    settings = settings_with(
        make_config, {"provider": "ollama", "context_chars": 5000}, replace=True
    )
    assert settings.llm.active == "ollama"
    assert set(settings.llm.providers) == {"ollama"}
    assert settings.context_chars == 5000
    llm = build_llm(settings)
    assert llm.provider == "ollama"
    llm.close()


def test_no_llm_section_defaults_to_ollama(make_config):
    settings = settings_with(make_config, None, replace=True)
    assert settings.llm.active == "ollama"
    build_llm(settings).close()


def test_supported_types_now():
    # R5: 네 종류(API 키 둘 + 이 PC + 로그인된 프로그램)
    assert supported_types() == ("ollama", "openai_compatible", "anthropic", "cli")


@pytest.mark.parametrize(
    ("providers", "match"),
    [
        ({"x": "ollama"}, "type이 없습니다"),
        ({"x": {"model": "m"}}, "type이 없습니다"),
        ({"x": {"type": "ollama", "api_key_env": "sk-abc def"}}, "환경 변수 이름만"),
        (["ollama"], "모양이어야"),
    ],
)
def test_bad_provider_entries_fail_at_start(make_config, providers, match):
    with pytest.raises(ValueError, match=match):
        settings_with(make_config, {"active": "x", "providers": providers}, replace=True)


# ---------------------------------------------------------------- api_key_env → 비밀값 목록


def test_api_key_env_names_join_secret_list_and_redaction(make_config):
    fake = "sk-" + "z" * 32  # 실행할 때 조립한다
    youtube = "AIza" + "x" * 35
    settings = settings_with(
        make_config,
        {
            "providers": {
                "ollama": {"type": "ollama"},
                "openai": {"type": "openai_compatible", "api_key_env": "OPENAI_API_KEY"},
            }
        },
        environ={"OPENAI_API_KEY": fake, "YOUTUBE_API_KEY": youtube},
    )
    # R5: config.yaml에 다른 AI의 키 이름도 있다(값은 없음) → 순서와 포함만 본다
    names = settings.secret_env_names
    assert names[0] == "YOUTUBE_API_KEY" and "OPENAI_API_KEY" in names
    assert set(settings.secret_values()) == {youtube, fake}
    assert fake not in repr(settings)
    llm = build_llm(settings)
    assert fake in llm._secrets  # Ollama 오류 문구·로그도 이 값을 가린다
    llm.close()


def test_api_key_env_without_value_adds_nothing(make_config):
    settings = settings_with(
        make_config,
        {
            "providers": {
                "ollama": {"type": "ollama"},
                "grok": {"type": "openai_compatible", "api_key_env": "XAI_API_KEY"},
            }
        },
    )
    assert "XAI_API_KEY" in settings.secret_env_names
    assert settings.secret_values() == []


# ---------------------------------------------------------------- 모듈 경계


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_only_registry_imports_ollama_module():
    """분석·초안·라우터는 Ollama를 모른다: app/llm/ 밖에서 app.llm.ollama를 import하지 않는다."""
    offenders = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("app/llm/"):
            continue
        if "app.llm.ollama" in _imports(path):
            offenders.append(rel)
    assert offenders == []
    inside = [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "app" / "llm").glob("*.py"))
        if p.name != "ollama.py" and "app.llm.ollama" in _imports(p)
    ]
    assert inside == ["app/llm/registry.py"]


# ---------------------------------------------------------------- R5: 저장소 config.yaml의 AI 목록


def test_repo_config_lists_every_ai_without_secrets(clean_env, tmp_path):
    settings = load_settings(env_path=tmp_path / "없음.env", environ={})
    providers = settings.llm.providers
    expected = {
        "ollama": "ollama", "openai": "openai_compatible", "claude": "anthropic",
        "gemini": "openai_compatible", "grok": "openai_compatible", "custom": "openai_compatible",
        "codex-cli": "cli", "claude-cli": "cli", "gemini-cli": "cli",
    }
    assert {n: p.type for n, p in providers.items()} == expected
    for p in providers.values():
        assert p.options.get("label")
        assert "model" not in p.options  # 모델 이름을 박지 않는다
        assert not any("key" in k and k != "key_optional" for k in p.options)


def test_build_provider_by_name(clean_env, tmp_path):
    from app.llm.anthropic import AnthropicClient
    from app.llm.cli import CLIClient
    from app.llm.openai_compatible import OpenAICompatibleClient
    from app.llm.registry import build_provider

    key = "sk-" + "k" * 30  # 실행할 때 조립한다
    settings = load_settings(env_path=tmp_path / "없음.env", environ={"OPENAI_API_KEY": key})
    openai = build_provider(settings, "openai")
    assert isinstance(openai, OpenAICompatibleClient)
    assert openai.base_url == "https://api.openai.com/v1" and openai.has_key
    assert openai.model == ""  # 고르기 전에는 비어 있다
    assert settings.llm.key_sources == {"openai": "dev_file"}
    assert key in settings.secret_values()
    claude = build_provider(settings, "claude")
    assert isinstance(claude, AnthropicClient) and not claude.has_key
    codex = build_provider(settings, "codex-cli")
    assert isinstance(codex, CLIClient) and codex.program == "codex"
    assert "OPENAI_API_KEY" in codex._hidden_env and "YOUTUBE_API_KEY" in codex._hidden_env
    for llm in (openai, claude, codex):
        llm.close()
