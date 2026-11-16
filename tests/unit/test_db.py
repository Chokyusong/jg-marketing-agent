"""SQLite 테이블 만들기·버전."""

from app import db


def _tables(path):
    with db.session(path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_init_creates_stage2_tables(tmp_db_path):
    version = db.init_db(tmp_db_path)
    assert version == db.SCHEMA_VERSION == len(db.MIGRATIONS)
    assert {"videos", "quota_usage", "search_cache"} <= _tables(tmp_db_path)


def test_init_is_idempotent(tmp_db_path):
    db.init_db(tmp_db_path)
    with db.session(tmp_db_path) as conn:
        conn.execute("INSERT INTO quota_usage(day, units) VALUES ('2026-11-16', 5)")
    assert db.init_db(tmp_db_path) == db.SCHEMA_VERSION
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


# ---------------------------------------------------------------- 3단계: video_context


def _insert_video(conn, video_id="AAAAAAAAAA1"):
    conn.execute(
        "INSERT INTO videos(video_id, title, fetched_at, source) VALUES (?, 't', 'now', 'search')",
        (video_id,),
    )


def test_stage3_adds_video_context(tmp_db_path):
    assert db.init_db(tmp_db_path) == db.SCHEMA_VERSION == 2
    assert "video_context" in _tables(tmp_db_path)
    with db.session(tmp_db_path) as conn:
        _insert_video(conn)
        conn.execute("INSERT INTO video_context(video_id) VALUES ('AAAAAAAAAA1')")
        row = conn.execute("SELECT * FROM video_context").fetchone()
    assert row["transcript_source"] == "none"
    assert row["transcript_text"] == ""
    assert row["comments_json"] == "[]"
    assert row["comments_disabled"] == 0
    assert row["body_source"] == "title_description"
    assert row["built_at"] is None  # 댓글을 아직 부르지 않은 행


def test_upgrade_from_stage2_db_keeps_data(tmp_db_path):
    # 2단계 DB(버전 1)를 그대로 두고 3단계 덩어리만 더한다.
    import sqlite3

    conn = sqlite3.connect(tmp_db_path)
    conn.executescript("BEGIN;" + db.MIGRATIONS[0] + "PRAGMA user_version = 1;COMMIT;")
    conn.execute("INSERT INTO quota_usage(day, units) VALUES ('2026-11-16', 101)")
    conn.commit()
    conn.close()

    assert db.init_db(tmp_db_path) == 2
    with db.session(tmp_db_path) as conn:
        assert conn.execute("SELECT units FROM quota_usage").fetchone()["units"] == 101
    assert "video_context" in _tables(tmp_db_path)


def test_video_context_constraints(tmp_db_path):
    import sqlite3

    import pytest

    db.init_db(tmp_db_path)
    with db.session(tmp_db_path) as conn:
        _insert_video(conn)
    bad_rows = [
        "INSERT INTO video_context(video_id) VALUES ('없는영상ID0')",  # videos에 없는 영상
        "INSERT INTO video_context(video_id, transcript_source) VALUES ('AAAAAAAAAA1', 'auto')",
        "INSERT INTO video_context(video_id, body_source) VALUES ('AAAAAAAAAA1', 'comments')",
        "INSERT INTO video_context(video_id, comments_disabled) VALUES ('AAAAAAAAAA1', 2)",
    ]
    for sql in bad_rows:
        with pytest.raises(sqlite3.IntegrityError), db.session(tmp_db_path) as conn:
            conn.execute(sql)
