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
    # 5단계: analyses(영상당 마지막 분석 1행), drafts(영상당 승인 초안 하나 — 코드가 지킨다)
    """
    CREATE TABLE analyses (
        video_id      TEXT PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
        topic         TEXT NOT NULL DEFAULT '',
        concern       TEXT NOT NULL DEFAULT '',
        tone          TEXT NOT NULL DEFAULT '',
        viewer_needs  TEXT NOT NULL DEFAULT '',
        evidence_json TEXT NOT NULL DEFAULT '[]',   -- [{quote, source}] 영상 자료와 대조해 남은 것
        dropped_json  TEXT NOT NULL DEFAULT '[]',   -- 자료에 없어서 버린 구절
        fallback      INTEGER NOT NULL DEFAULT 0 CHECK (fallback IN (0, 1)),
        model         TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL
    );
    CREATE TABLE drafts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id         TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
        body             TEXT NOT NULL,             -- 표기([광고])를 포함한 전체 글
        evidence_quote   TEXT NOT NULL DEFAULT '',
        evidence_source  TEXT NOT NULL DEFAULT ''
                         CHECK (evidence_source IN ('', 'transcript', 'title', 'description',
                                                    'comment')),
        tone_label       TEXT NOT NULL DEFAULT '',
        model            TEXT NOT NULL DEFAULT '',
        attempts         INTEGER NOT NULL DEFAULT 0,
        first_passed     INTEGER NOT NULL DEFAULT 0 CHECK (first_passed IN (0, 1)),
        validation_json  TEXT NOT NULL,
        passed           INTEGER NOT NULL DEFAULT 0 CHECK (passed IN (0, 1)),
        status           TEXT NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'approved', 'superseded')),
        edited_by_human  INTEGER NOT NULL DEFAULT 0 CHECK (edited_by_human IN (0, 1)),
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL,
        approved_at      TEXT
    );
    CREATE INDEX drafts_video ON drafts(video_id, id);
    CREATE INDEX drafts_status ON drafts(status);
    """,
    # 7단계: 운영 규칙과 기록(DESIGN 4절 · PLAYBOOK 7단계)
    # - posts: 영상당 1개는 UNIQUE(target, video_id)가 막는다. 하루 상한은 `day`(한국 날짜)로 센다.
    #   실패(failed)는 상한에 세지 않고, 같은 영상을 다시 시도하면 그 행을 reserved로 되돌린다.
    #   video_id에 외래 키를 걸지 않는다(영상 행이 지워져도 "이미 단 영상" 기록은 남아야 한다).
    # - runs: 지우지 않는 기록(트리거가 DELETE를 막는다). `day`는 통계용 한국 날짜.
    # - job_events: 작업 진행 상태(8단계 작업 서비스가 쓴다).
    """
    CREATE TABLE posts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        target      TEXT NOT NULL CHECK (target IN ('sandbox', 'youtube')),
        video_id    TEXT NOT NULL,
        profile     TEXT NOT NULL,
        draft_id    INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'reserved'
                    CHECK (status IN ('reserved', 'posted', 'failed')),
        day         TEXT NOT NULL,                 -- 예약한 한국 날짜 YYYY-MM-DD
        attempts    INTEGER NOT NULL DEFAULT 1,    -- 실패 뒤 다시 예약할 때마다 하나씩
        reason      TEXT NOT NULL DEFAULT '',      -- 마지막 실패 사유
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        posted_at   TEXT,
        UNIQUE (target, video_id)
    );
    CREATE INDEX posts_day ON posts(target, day, status);
    CREATE INDEX posts_profile ON posts(target, profile, updated_at);
    CREATE TABLE runs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        at               TEXT NOT NULL,
        day              TEXT NOT NULL,            -- 한국 날짜(오늘 통계)
        action           TEXT NOT NULL CHECK (action IN ('analyze', 'draft', 'approve', 'post')),
        video_id         TEXT NOT NULL DEFAULT '',
        video_title      TEXT NOT NULL DEFAULT '',
        profile          TEXT NOT NULL DEFAULT '',
        comment_text     TEXT NOT NULL DEFAULT '',
        target           TEXT NOT NULL DEFAULT '' CHECK (target IN ('', 'sandbox', 'youtube')),
        result           TEXT NOT NULL CHECK (result IN ('success', 'failure', 'info')),
        reason           TEXT NOT NULL DEFAULT '',
        screenshot_path  TEXT NOT NULL DEFAULT '',
        job_id           TEXT NOT NULL DEFAULT '',
        draft_id         INTEGER,
        post_id          INTEGER
    );
    CREATE INDEX runs_at ON runs(at, id);
    CREATE INDEX runs_day ON runs(day, action, target);
    CREATE TRIGGER runs_keep BEFORE DELETE ON runs
    BEGIN
        SELECT RAISE(ABORT, 'runs는 지우지 않는 기록입니다');
    END;
    CREATE TABLE job_events (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id   TEXT NOT NULL,
        at       TEXT NOT NULL,
        state    TEXT NOT NULL,
        message  TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX job_events_job ON job_events(job_id, id);
    """,
    # 8단계: 통제된 테스트 페이지(/sandbox/watch)의 댓글. 실제 유튜브와 상관없는 이 앱만의 표.
    # input_events: 댓글 상자에서 일어난 입력 이벤트 수(한 글자씩 입력됐는지 확인하는 데 쓴다)
    """
    CREATE TABLE sandbox_comments (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id      TEXT NOT NULL,
        profile       TEXT NOT NULL DEFAULT '',
        body          TEXT NOT NULL,
        input_events  INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX sandbox_comments_video ON sandbox_comments(video_id, id);
    """,
    # R2: 프로필 로그인 확인 결과(프로필 이름마다 마지막 한 번). 아이디·비밀번호는 없다
    """
    CREATE TABLE profile_logins (
        profile TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT '',
        checked_at TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    """,
    # R3: 광고 표기 켬/끔을 모든 영상에서. 초안마다 표기를 붙였는지(drafts.disclosed)와,
    # 기록 줄마다 그 댓글이 표기를 붙였는지(runs.disclosed, 댓글이 없는 줄은 NULL)를 남긴다.
    # 예전 초안은 글이 표기로 시작하는지로 채운다(기본 문구 [광고]).
    """
    ALTER TABLE drafts ADD COLUMN disclosed INTEGER NOT NULL DEFAULT 1
        CHECK (disclosed IN (0, 1));
    UPDATE drafts SET disclosed = CASE WHEN substr(body, 1, 4) = '[광고]' THEN 1 ELSE 0 END;
    ALTER TABLE runs ADD COLUMN disclosed INTEGER CHECK (disclosed IN (0, 1));
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


@contextmanager
def immediate(path: Path) -> Iterator[sqlite3.Connection]:
    """`BEGIN IMMEDIATE` 거래(7단계 운영 규칙). 시작할 때 쓰기 잠금을 잡는다.

    두 요청이 동시에 와도 한쪽은 다른 쪽이 commit할 때까지 기다린다(연결 timeout 10초).
    그래서 "세기 → 확인 → 넣기"가 끼어들기 없이 한 번에 된다. 예외면 rollback.
    """
    conn = connect(path)
    conn.isolation_level = None  # 거래를 직접 연다(파이썬의 자동 BEGIN을 끈다)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()
