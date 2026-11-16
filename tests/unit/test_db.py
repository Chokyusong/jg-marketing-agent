"""SQLite 테이블 만들기·버전."""

from app import db


def _tables(path):
    with db.session(path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_init_creates_stage2_tables(tmp_db_path):
    version = db.init_db(tmp_db_path)
    assert version == db.SCHEMA_VERSION == 1
    assert {"videos", "quota_usage", "search_cache"} <= _tables(tmp_db_path)


def test_init_is_idempotent(tmp_db_path):
    db.init_db(tmp_db_path)
    with db.session(tmp_db_path) as conn:
        conn.execute("INSERT INTO quota_usage(day, units) VALUES ('2026-11-16', 5)")
    assert db.init_db(tmp_db_path) == 1
    with db.session(tmp_db_path) as conn:
        assert conn.execute("SELECT units FROM quota_usage").fetchone()["units"] == 5


def test_creates_parent_folder(tmp_path):
    path = tmp_path / "nested" / "dir" / "app.sqlite3"
    db.init_db(path)
    assert path.exists()


def test_session_rolls_back_on_error(tmp_db_path):
    db.init_db(tmp_db_path)
    try:
        with db.session(tmp_db_path) as conn:
            conn.execute("INSERT INTO quota_usage(day, units) VALUES ('2026-11-16', 1)")
            raise RuntimeError("중간 실패")
    except RuntimeError:
        pass
    with db.session(tmp_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM quota_usage").fetchone()[0] == 0


def test_video_source_is_constrained(tmp_db_path):
    import sqlite3

    import pytest

    db.init_db(tmp_db_path)
    with pytest.raises(sqlite3.IntegrityError), db.session(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO videos(video_id, title, fetched_at, source) "
            "VALUES ('x', 't', 'now', 'bad')"
        )
