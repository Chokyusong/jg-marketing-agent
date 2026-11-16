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


# ---------------------------------------------------------------- 6단계: brand.facts, validator


def test_brand_facts_and_extra_patterns_from_repo_config(clean_env, tmp_path):
    settings = load_settings(env_path=tmp_path / "없음.env")
    assert settings.brand_facts == ("운명원은 연애 사주 상담을 하는 곳이다",)  # D4 기본값
    assert settings.validator_extra_patterns == ()


def test_brand_facts_missing_uses_default_and_empty_list_means_none(make_config):
    path = make_config({"brand": {"other": 1}})
    assert load_settings(path, env_path=None, environ={}).brand_facts == (
        "운명원은 연애 사주 상담을 하는 곳이다",
    )
    path = make_config({"brand": {"facts": []}})
    assert load_settings(path, env_path=None, environ={}).brand_facts == ()
    path = make_config({"brand": {"facts": ["  운명원은 서울에 있다 ", ""]}})
    assert load_settings(path, env_path=None, environ={}).brand_facts == ("운명원은 서울에 있다",)


def test_extra_patterns_read_and_checked(make_config):
    path = make_config({"validator": {"extra_patterns": [{"code": "V10", "pattern": "기가 막히"}]}})
    settings = load_settings(path, env_path=None, environ={})
    assert settings.validator_extra_patterns == (("V10", "기가 막히"),)
    bad = make_config({"validator": {"extra_patterns": [{"code": "V10", "pattern": "(깨진"}]}})
    with pytest.raises(ValueError, match="정규식"):
        load_settings(bad, env_path=None, environ={})
    bad_facts = make_config({"brand": {"facts": "한 줄"}})
    with pytest.raises(ValueError, match="brand.facts"):
        load_settings(bad_facts, env_path=None, environ={})


def test_profiles_and_default_target(make_config):
    settings = load_settings(make_config(), env_path=None, environ={})
    assert settings.profiles == ("유튜브1", "유튜브2", "유튜브3")
    assert settings.default_target == "sandbox"
    path = make_config({"browser": {"default_target": "assist"}})
    assert load_settings(path, env_path=None, environ={}).default_target == "youtube"


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"profiles": []}, "profiles"),
        ({"profiles": "유튜브1"}, "profiles"),
        ({"profiles": ["유튜브1", " "]}, "빈 이름"),
        ({"profiles": ["유튜브1", "유튜브1"]}, "같은 이름"),
        ({"browser": {"default_target": "real"}}, "default_target"),
    ],
)
def test_bad_profiles_or_target_are_clear_errors(make_config, overrides, match):
    with pytest.raises(ValueError, match=match):
        load_settings(make_config(overrides), env_path=None, environ={})


# ---------------------------------------------------------------- 8단계: browser 절


def test_browser_settings_defaults(make_config):
    from app.config import load_settings

    s = load_settings(make_config(), env_path=None, environ={})
    assert s.browser.headless is False
    assert s.browser.window_position == (60, -1060)
    assert s.browser.typing_delay_ms == (60, 160)
    assert s.browser.chrome_path is None
    assert s.browser.profiles_root.parts[-2:] == ("JGMarketingAgent", "profiles")


def test_browser_settings_values(make_config, tmp_path):
    from app.config import load_settings

    path = make_config({"browser": {"headless": True, "window_position": [-1860, 60],
                                    "typing_delay_ms": 30, "screenshot_dir": str(tmp_path)}})
    s = load_settings(path, env_path=None, environ={})
    assert s.browser.headless is True and s.browser.window_position == (-1860, 60)
    assert s.browser.typing_delay_ms == (30, 30) and s.browser.screenshot_dir == tmp_path


@pytest.mark.parametrize(
    "browser",
    [
        {"headless": "yes"},
        {"window_position": "60"},
        {"window_position": "a,b"},
        {"typing_delay_ms": [200, 100]},
        {"typing_delay_ms": [-1, 10]},
        {"typing_delay_ms": "fast"},
    ],
)
def test_browser_settings_reject_bad_values(make_config, browser):
    from app.config import load_settings

    with pytest.raises(ValueError):
        load_settings(make_config({"browser": browser}), env_path=None, environ={})
