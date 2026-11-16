"""R2 사용자 설정: 저장·읽기·우선순위, 칸별 검사, 키 암호화(DPAPI), 평문 없음."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.config import DEFAULT_OLLAMA_MODEL, load_settings, reload_settings
from app.user_settings import (
    FIELDS,
    TYPING_SPEEDS,
    Protector,
    SecretStoreUnavailable,
    UserStore,
    apply_overlay,
    default_protector,
    default_user_dir,
    key_shape_ok,
    typing_speed_of,
    validate,
)

FAKE_KEY = "AIza" + "x" * 35  # 실행할 때 조립
OTHER_KEY = "AIza" + "y" * 35


def xor_protector() -> Protector:
    return Protector(
        protect=lambda b: b"X" + bytes(c ^ 0x33 for c in b),
        unprotect=lambda b: bytes(c ^ 0x33 for c in b[1:]),
    )


def load(make_config, tmp_path, *, environ=None, overrides=None, user=True):
    return load_settings(
        make_config(overrides or {}), env_path=None, db_path=tmp_path / "t.sqlite3",
        environ=environ or {}, user_dir=tmp_path / "user" if user else None,
        protector=xor_protector(),
    )


# ---------------------------------------------------------------- 위치


def test_default_user_dir_is_outside_repo(tmp_path):
    assert default_user_dir({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "JGMarketingAgent"
    assert default_user_dir({"JG_USER_DIR": str(tmp_path / "x")}) == tmp_path / "x"
    repo = Path(__file__).resolve().parents[2]
    assert repo not in default_user_dir({"LOCALAPPDATA": str(tmp_path)}).parents


def test_without_user_dir_nothing_is_read(make_config, tmp_path):
    store = UserStore(tmp_path / "user", xor_protector())
    store.write_values({"limits.daily_max_comments": 3})
    s = load(make_config, tmp_path, user=False)
    assert s.daily_max_comments == 10 and s.source is not None and s.source.user_dir is None


# ---------------------------------------------------------------- 저장·읽기·우선순위


def test_saved_values_override_config(make_config, tmp_path):
    UserStore(tmp_path / "user", xor_protector()).write_values({
        "limits.daily_max_comments": 3,
        "discover.query": "이별 고민",
        "comment.min_chars": 30,
        "brand.facts": ["운명원은 연애 사주 상담을 하는 곳이다", "운명원은 온라인으로 상담한다"],
        "browser.typing_speed": "fast",
        "discover.shorts_under_seconds": 120,
        "comment.disclose_default": False,
        "posting.confirm_before_post": True,
    })
    s = load(make_config, tmp_path)
    assert s.daily_max_comments == 3
    assert s.discover.query == "이별 고민"
    assert s.rules["comment"]["min_chars"] == 30 and s.rules["comment"]["max_chars"] == 120
    assert len(s.brand_facts) == 2
    assert s.browser.typing_delay_ms == TYPING_SPEEDS["fast"] and s.typing_speed == "fast"
    assert s.discover.shorts_under_seconds == 120
    assert s.disclose_default is False and s.confirm_before_post is True  # R3이 읽는다
    assert set(s.user_values) == {
        "limits.daily_max_comments", "discover.query", "comment.min_chars", "brand.facts",
        "browser.typing_speed", "discover.shorts_under_seconds", "comment.disclose_default",
        "posting.confirm_before_post",
    }


def test_defaults_without_saved_values(make_config, tmp_path):
    s = load(make_config, tmp_path)
    assert s.discover.shorts_under_seconds == 181  # 유튜브 쇼츠는 3분까지
    assert s.disclose_default is True and s.confirm_before_post is False
    assert s.typing_speed == "normal" and s.user_values == {}


def test_model_priority_user_over_env_over_code(make_config, tmp_path):
    assert load(make_config, tmp_path).llm.ollama_model == DEFAULT_OLLAMA_MODEL
    env = {"OLLAMA_MODEL": "qwen2.5:7b"}
    assert load(make_config, tmp_path, environ=env).llm.ollama_model == "qwen2.5:7b"
    UserStore(tmp_path / "user", xor_protector()).write_values({"llm.model": "qwen3.6:latest"})
    assert load(make_config, tmp_path, environ=env).llm.ollama_model == "qwen3.6:latest"


def test_key_priority_program_over_dev_file(make_config, tmp_path):
    env = {"YOUTUBE_API_KEY": OTHER_KEY}
    s = load(make_config, tmp_path, environ=env)
    assert s.youtube_api_key == OTHER_KEY and s.youtube_key_source == "dev_file"
    UserStore(tmp_path / "user", xor_protector()).write_key(FAKE_KEY)
    s = load(make_config, tmp_path, environ=env)
    assert s.youtube_api_key == FAKE_KEY and s.youtube_key_source == "program"
    assert FAKE_KEY in s.secret_values()  # 저장한 키도 로그 가리기 대상
    assert FAKE_KEY not in repr(s)
    none = load(make_config, tmp_path / "other")
    assert none.youtube_api_key is None and none.youtube_key_source is None


def test_reload_reads_the_same_way(make_config, tmp_path):
    s = load(make_config, tmp_path)
    UserStore(tmp_path / "user", xor_protector()).write_values({"limits.daily_max_comments": 7})
    assert reload_settings(s).daily_max_comments == 7
    assert reload_settings(s, use_user=False).daily_max_comments == 10


def test_broken_settings_file_falls_back_to_defaults(make_config, tmp_path):
    path = tmp_path / "user" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{깨진 글", encoding="utf-8")
    assert load(make_config, tmp_path).daily_max_comments == 10


def test_unknown_names_in_file_are_ignored(tmp_path):
    store = UserStore(tmp_path, xor_protector())
    store.settings_path.write_text(
        json.dumps({"version": 1, "values": {"nope": 1, "discover.query": "a"}}), encoding="utf-8"
    )
    assert store.read_values() == {"discover.query": "a"}


def test_overlay_does_not_change_original():
    rules = {"comment": {"min_chars": 40}}
    out = apply_overlay(rules, {"comment.min_chars": 20, "browser.typing_speed": "slow"})
    assert rules == {"comment": {"min_chars": 40}}
    assert out["comment"]["min_chars"] == 20
    assert out["browser"]["typing_delay_ms"] == list(TYPING_SPEEDS["slow"])


def test_typing_speed_of_nearest():
    assert typing_speed_of((60, 160)) == "normal"
    assert typing_speed_of((20, 60)) == "fast"
    assert typing_speed_of((200, 400)) == "slow"


# ---------------------------------------------------------------- 칸별 검사


CURRENT = {"comment.min_chars": 40, "comment.max_chars": 120, "comment.disclosure": "[광고]"}


@pytest.mark.parametrize(("name", "value", "word"), [
    ("limits.daily_max_comments", 0, "1~50"),
    ("limits.daily_max_comments", 51, "1~50"),
    ("limits.daily_max_comments", "열", "숫자"),
    ("limits.daily_max_comments", True, "숫자"),
    ("discover.query", "   ", "비워 둘 수 없습니다"),
    ("discover.max_results", 60, "1~50"),
    ("discover.exclude_shorts", "yes", "켬 또는 끔"),
    ("browser.typing_speed", "turbo", "고를 수 없는"),
    ("comment.brand", "가" * 31, "30자"),
    ("brand.facts", "한 줄", "목록"),
    ("brand.facts", ["가" * 201], "200자"),
    ("brand.facts", [f"사실 {i}번 문장" for i in range(11)], "10줄"),
    ("discover.shorts_under_seconds", 5, "10~3600"),
    ("nope.field", 1, "바꿀 수 없는"),
    ("browser.window_position", "1,1", "바꿀 수 없는"),
])
def test_bad_fields_get_korean_reasons(name, value, word):
    clean, errors = validate({name: value}, CURRENT)
    assert name in errors and word in errors[name]
    assert name not in clean


def test_min_must_be_below_max():
    _, errors = validate({"comment.min_chars": 130}, CURRENT)
    assert "최소" in errors["comment.min_chars"]
    _, errors = validate({"comment.max_chars": 30}, CURRENT)
    assert "최소" in errors["comment.max_chars"]
    clean, errors = validate({"comment.min_chars": 20, "comment.max_chars": 100}, CURRENT)
    assert errors == {} and clean == {"comment.min_chars": 20, "comment.max_chars": 100}


def test_good_values_are_cleaned():
    clean, errors = validate(
        {"discover.query": "  연애   상담 ", "limits.daily_max_comments": "5",
         "brand.facts": [" 운명원은  연애 사주 상담을 하는 곳이다 ", "", "  "]},
        CURRENT,
    )
    assert errors == {}
    assert clean == {"discover.query": "연애 상담", "limits.daily_max_comments": 5,
                     "brand.facts": ["운명원은 연애 사주 상담을 하는 곳이다"]}


def test_every_field_has_a_korean_label():
    for name, field in FIELDS.items():
        assert field.label and any("가" <= ch <= "힣" for ch in field.label), name


# ---------------------------------------------------------------- 키 저장(암호화)


def test_key_roundtrip_and_no_plaintext_with_fake_protector(tmp_path):
    store = UserStore(tmp_path, xor_protector())
    assert store.read_key() is None and not store.has_key()
    store.write_key(FAKE_KEY)
    raw = store.key_path.read_bytes()
    assert FAKE_KEY.encode() not in raw and b"AIza" not in raw
    assert store.read_key() == FAKE_KEY
    assert store.delete_key() is True and store.read_key() is None
    assert store.delete_key() is False


def test_key_is_not_in_settings_file(tmp_path):
    store = UserStore(tmp_path, xor_protector())
    store.write_key(FAKE_KEY)
    store.write_values({"discover.query": "연애"})
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert FAKE_KEY.encode() not in path.read_bytes(), path


def test_unreadable_key_counts_as_missing(tmp_path):
    def boom(_b: bytes) -> bytes:
        raise OSError("다른 사용자 계정")

    UserStore(tmp_path, xor_protector()).write_key(FAKE_KEY)
    store = UserStore(tmp_path, Protector(protect=lambda b: b, unprotect=boom))
    assert store.read_key() is None


def test_no_secret_store_off_windows(tmp_path):
    def off(_b: bytes) -> bytes:
        raise SecretStoreUnavailable("x")

    store = UserStore(tmp_path, Protector(protect=off, unprotect=off, available=False))
    with pytest.raises(SecretStoreUnavailable):
        store.write_key(FAKE_KEY)
    assert not store.has_key()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI는 Windows에만 있다")
def test_real_dpapi_roundtrip_has_no_plaintext(tmp_path):
    protector = default_protector()
    assert protector.available
    store = UserStore(tmp_path, protector)
    store.write_key(FAKE_KEY)
    raw = store.key_path.read_bytes()
    assert FAKE_KEY.encode() not in raw and FAKE_KEY[4:].encode() not in raw
    assert FAKE_KEY.encode("utf-16-le") not in raw
    assert store.read_key() == FAKE_KEY


def test_key_shape():
    assert key_shape_ok(FAKE_KEY)
    assert not key_shape_ok("짧음")
    assert not key_shape_ok("AIza xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
