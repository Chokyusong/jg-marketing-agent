"""작업 기록(`runs` 표, DESIGN 4절 · PLAYBOOK 7단계).

- 지우지 않는 기록이다(표의 트리거가 DELETE를 막는다). 고치지 않고 새 줄을 더한다.
- 한 줄: 시각, 한국 날짜, 작업(analyze·draft·approve·post), 영상, 프로필, 댓글, 대상, 결과, 사유,
  그 댓글이 광고 표기를 붙였는지(R3, `disclosed`).
- 결과: post는 success/failure, 5단계의 분석·초안·승인은 info(실패하면 failure와 사유).
- 오늘 통계(`today_stats`)는 이 표와 `posts`에서 센다. 성공률은 오늘 게시 시도가 없으면 None.
- 게시 결과 줄은 `rules.mark_posted`·`mark_failed`가 상태를 바꾸는 같은 거래 안에서
  `insert()`로 쓴다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app import db
from app.config import POST_TARGETS
from app.youtube.quota import Clock, kst_day, utc_now

ACTIONS = ("analyze", "draft", "approve", "post")
RESULTS = ("success", "failure", "info")
RECENT_MAX = 200


@dataclass(frozen=True)
class Run:
    id: int
    at: str
    day: str
    action: str
    video_id: str
    video_title: str
    profile: str
    comment_text: str
    target: str
    result: str
    reason: str
    screenshot_path: str
    job_id: str
    draft_id: int | None
    post_id: int | None
    disclosed: bool | None = None  # R3: 그 댓글이 광고 표기를 붙였는지(댓글이 없는 줄은 None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TodayStats:
    """제목 영역의 오늘 통계 4개(UI_SPEC 3절 A2)와 03칸 「오늘 작업 n / 상한」."""

    target: str
    day: str
    videos: int  # 오늘 상한에 센 영상(예약 + 게시). 실패는 세지 않는다
    daily_limit: int
    remaining: int
    drafts: int  # 오늘 만든 댓글 초안 수
    posted: int  # 오늘 게시 완료
    failed: int  # 오늘 게시 실패
    success_rate: float | None  # posted / (posted + failed). 오늘 게시 시도가 없으면 None


def insert(
    conn: sqlite3.Connection,
    *,
    at: str,
    action: str,
    result: str,
    video_id: str = "",
    video_title: str = "",
    profile: str = "",
    comment_text: str = "",
    target: str = "",
    reason: str = "",
    screenshot_path: str = "",
    job_id: str = "",
    draft_id: int | None = None,
    post_id: int | None = None,
    day: str | None = None,
    disclosed: bool | None = None,
) -> int:
    """열린 연결에 기록 한 줄을 넣는다(거래는 부르는 쪽이 연다). 제목이 비면 videos에서 찾는다."""
    if action not in ACTIONS:
        raise ValueError(f"알 수 없는 작업: {action}")
    if result not in RESULTS:
        raise ValueError(f"알 수 없는 결과: {result}")
    if target and target not in POST_TARGETS:
        raise ValueError(f"알 수 없는 대상: {target}")
    if video_id and not video_title:
        row = conn.execute("SELECT title FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        video_title = row["title"] if row else ""
    cur = conn.execute(
        "INSERT INTO runs(at, day, action, video_id, video_title, profile, comment_text, target, "
        "result, reason, screenshot_path, job_id, draft_id, post_id, disclosed) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            at,
            day or kst_day(datetime.fromisoformat(at)),
            action,
            video_id,
            video_title,
            profile,
            comment_text,
            target,
            result,
            reason,
            screenshot_path,
            job_id,
            draft_id,
            post_id,
            None if disclosed is None else int(bool(disclosed)),
        ),
    )
    return int(cur.lastrowid)


class Ledger:
    def __init__(self, db_path: Path, *, daily_limit: int, clock: Clock = utc_now) -> None:
        self.db_path = db_path
        self.daily_limit = int(daily_limit)
        self.clock = clock

    def record(self, action: str, result: str, **fields: Any) -> int:
        """기록 한 줄을 더하고 id를 돌려준다. 시각은 지금(고정 시계를 넣으면 그 시각)."""
        now = self.clock()
        with db.session(self.db_path) as conn:
            return insert(
                conn, at=now.isoformat(), day=kst_day(now), action=action, result=result, **fields
            )

    def recent(self, limit: int = 20) -> list[Run]:
        """최근 기록(최신이 위). 같은 시각이면 나중에 넣은 줄이 위."""
        limit = max(1, min(int(limit), RECENT_MAX))
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(r) for r in rows]

    def count(self) -> int:
        with db.session(self.db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def today_stats(self, target: str, *, daily_limit: int | None = None) -> TodayStats:
        if target not in POST_TARGETS:
            raise ValueError(f"알 수 없는 대상: {target}")
        limit = self.daily_limit if daily_limit is None else min(int(daily_limit), self.daily_limit)
        day = kst_day(self.clock())
        with db.session(self.db_path) as conn:
            videos = conn.execute(
                "SELECT COUNT(*) FROM posts WHERE target=? AND day=? "
                "AND status IN ('reserved', 'posted')",
                (target, day),
            ).fetchone()[0]
            drafts = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE day=? AND action='draft' AND result='info'",
                (day,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT result, COUNT(*) AS n FROM runs WHERE day=? AND action='post' AND target=? "
                "GROUP BY result",
                (day, target),
            ).fetchall()
        by_result = {r["result"]: int(r["n"]) for r in rows}
        posted = by_result.get("success", 0)
        failed = by_result.get("failure", 0)
        tried = posted + failed
        return TodayStats(
            target=target,
            day=day,
            videos=int(videos),
            daily_limit=limit,
            remaining=max(0, limit - int(videos)),
            drafts=int(drafts),
            posted=posted,
            failed=failed,
            success_rate=(posted / tried) if tried else None,
        )


def _row(row: sqlite3.Row) -> Run:
    return Run(
        id=int(row["id"]),
        at=row["at"],
        day=row["day"],
        action=row["action"],
        video_id=row["video_id"],
        video_title=row["video_title"],
        profile=row["profile"],
        comment_text=row["comment_text"],
        target=row["target"],
        result=row["result"],
        reason=row["reason"],
        screenshot_path=row["screenshot_path"],
        job_id=row["job_id"],
        draft_id=row["draft_id"],
        post_id=row["post_id"],
        disclosed=None if row["disclosed"] is None else bool(row["disclosed"]),
    )
