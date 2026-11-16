"""설정 읽기: config.yaml + .env(환경 변수 우선), 키가 없어도 뜬다, 키는 repr에 없다."""

from pathlib import Path

import pytest

from app.config import DEFAULT_DB_PATH, load_settings

FAKE_KEY = "AIza" + "x" * 35  # 실행할 때 조립한다(파일에 키 모양을 남기지 않는다)


def test_reads_repo_config_without_key(clean_env, tmp_path):
    settings = load_settings(env_path=tmp_path / "없음.env")
    assert settings.discover.query == "연애 고민"
    assert settings.discover.max_results == 12
    assert settings.daily_max_comments == 10
    assert settings.rules["comment"]["disclosure"] == "[광고]"
    assert settings.youtube_api_key is None
    assert settings.youtube_key_configured is False
    assert settings.db_path == DEFAULT_DB_PATH


def test_reads_key_from_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"YOUTUBE_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    settings = load_settings(env_path=env_file)
    assert settings.youtube_api_key == FAKE_KEY
    assert settings.youtube_key_configured is True


def test_environment_overrides_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("YOUTUBE_API_KEY=from-file\n", encoding="utf-8")
    clean_env.setenv("YOUTUBE_API_KEY", "from-env")
    assert load_settings(env_path=env_file).youtube_api_key == "from-env"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_key_means_missing(clean_env, tmp_path, value):
    settings = load_settings(env_path=None, environ={"YOUTUBE_API_KEY": value})
    assert settings.youtube_key_configured is False


def test_key_not_in_repr(tmp_path):
    settings = load_settings(env_path=None, environ={"YOUTUBE_API_KEY": FAKE_KEY})
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings)
    assert settings.secret_values() == [FAKE_KEY]


def test_custom_config_and_db_path(make_config, tmp_path):
    path = make_config({"discover": {"query": "이별", "max_results": 5}})
    settings = load_settings(path, env_path=None, environ={"APP_DB_PATH": str(tmp_path / "x.db")})
    assert settings.discover.query == "이별"
    assert settings.discover.max_results == 5
    assert settings.db_path == Path(tmp_path / "x.db")


def test_missing_config_file_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="설정 파일이 없습니다"):
        load_settings(tmp_path / "nope.yaml", env_path=None, environ={})
