"""SQLite 연결과 테이블 만들기·버전 올리기.

- 파일 하나(`Settings.db_path`)를 쓴다. 연결은 작업마다 새로 연다(FastAPI 동기 함수는
  여러 스레드에서 돌기 때문).
- 버전은 `PRAGMA user_version`으로 센다. 새 표가 필요하면 MIGRATIONS 끝에 한 단계씩 붙인다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# 1번 덩어리(2단계): videos, quota_usage, search_cache(같은 검색 10분 저장, DESIGN 7절)
MIGRATIONS: list[str] = [
    """
    CREATE TABLE videos (
        video_id       TEXT PRIMARY KEY,
        title          TEXT NOT NULL,
        channel_id     TEXT NOT NULL DEFAULT '',
        channel_title  TEXT NOT NULL DEFAULT '',
        description    TEXT NOT NULL DEFAULT '',
        published_at   TEXT NOT NULL DEFAULT '',
        thumbnail_url  TEXT NOT NULL DEFAULT '',
        duration_seconds INTEGER,
        view_count     INTEGER,
        like_count     INTEGER,
        comment_count  INTEGER,
        fetched_at     TEXT NOT NULL,
        source         TEXT NOT NULL CHECK (source IN ('search', 'link', 'rising'))
    );
    CREATE TABLE quota_usage (
        day    TEXT PRIMARY KEY,           -- 한국 시각 날짜 YYYY-MM-DD
        units  INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE search_cache (
        cache_key  TEXT PRIMARY KEY,
        video_ids  TEXT NOT NULL,          -- JSON 배열(검색 결과 순서)
        created_at TEXT NOT NULL
    );
    """,
    # 3단계: video_context(영상당 1행, DESIGN 4절 · PLAYBOOK 3단계)
    # - 붙여 넣은 자막만 먼저 저장하면 built_at이 비어 있다(인기 댓글을 아직 부르지 않음).
    # - built_at이 있으면 comments_json은 그때 받은 인기 댓글이다(다시 만들 때만 새로 부른다).
    """
    CREATE TABLE video_context (
        video_id           TEXT PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
        transcript_source  TEXT NOT NULL DEFAULT 'none'
                           CHECK (transcript_source IN ('manual', 'unofficial', 'none')),
        transcript_text    TEXT NOT NULL DEFAULT '',
        comments_json      TEXT NOT NULL DEFAULT '[]',   -- [{text, like_count, published_at}]
        comments_disabled  INTEGER NOT NULL DEFAULT 0 CHECK (comments_disabled IN (0, 1)),
        body_source        TEXT NOT NULL DEFAULT 'title_description'
                           CHECK (body_source IN ('transcript', 'title_description')),
        built_at           TEXT
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path) -> int:
    """테이블을 만들거나 최신 버전으로 올린다. 최종 버전을 돌려준다."""
    conn = connect(path)
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version in range(current, SCHEMA_VERSION):
            conn.executescript(
                "BEGIN;" + MIGRATIONS[version] + f"PRAGMA user_version = {version + 1};COMMIT;"
            )
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


@contextmanager
def session(path: Path) -> Iterator[sqlite3.Connection]:
    """with 블록이 끝나면 commit(예외면 rollback)하고 닫는다."""
    conn = connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
