"""운영 규칙: 영상당 댓글 1개, 하루 상한, 승인한 초안만(DESIGN 4절 · PLAYBOOK 7단계).

평가 15점(운영 규칙)이 여기 달려 있다. 앱 코드의 if 문이 아니라 **DB 거래와 제약**으로 막는다.

예약(`reserve`)은 `BEGIN IMMEDIATE` 거래 하나 안에서 다음을 한 번에 한다.
1. 초안이 그 영상의 승인한 초안인지 확인한다. 아니면 `draft_not_approved`.
2. 오늘(한국 날짜) 그 대상의 예약 + 게시 수를 센다. 상한 이상이면 `daily_limit_reached`.
3. `posts`에 예약 행을 넣는다. `UNIQUE(target, video_id)`에 걸리면
   - 그 행이 실패(failed)면 같은 행을 예약(reserved)으로 되돌린다(다시 시도. 오늘 수에 다시 센다).
   - 예약·게시 상태면 `already_commented`.

`BEGIN IMMEDIATE`는 시작할 때 쓰기 잠금을 잡으므로, 버튼을 연달아 누르거나 요청 두 개가 동시에
와도 "세기 → 넣기" 사이에 다른 예약이 끼어들지 못한다. sandbox와 youtube는 따로 센다.

게시가 끝나면 8단계 작업 서비스가 `mark_posted` / `mark_failed`를 부른다. 두 함수는 상태를 바꾸는
같은 거래 안에서 작업 기록(`runs`)에 결과 한 줄을 남긴다(기록이 빠질 수 없게).
실패는 상한에 세지 않지만 기록에는 남는다.

이 모듈은 네트워크·LLM 없이 돈다. 시간은 넣어 준 시계(`clock`)로만 잰다(테스트는 고정 시계).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app import db
from app.config import POST_TARGETS
from app.errors import AppError, ErrorKind
from app.ops import ledger
from app.youtube.quota import Clock, kst_day, utc_now
from app.youtube.url_parser import is_video_id

POST_STATUSES = ("reserved", "posted", "failed")


@dataclass(frozen=True)
class Post:
    id: int
    target: str
    video_id: str
    profile: str
    draft_id: int
    status: str
    day: str
    attempts: int
    reason: str
    created_at: str
    updated_at: str
    posted_at: str | None


def check_target(target: str) -> str:
    if target not in POST_TARGETS:
        raise ValueError(f"알 수 없는 게시 대상: {target!r} (sandbox | youtube)")
    return target


class PostRules:
    def __init__(
        self,
        db_path: Path,
        *,
        daily_limit: int,
        profiles: Sequence[str],
        clock: Clock = utc_now,
    ) -> None:
        if int(daily_limit) < 0:
            raise ValueError("하루 상한은 0 이상이어야 합니다.")
        self.db_path = db_path
        self.daily_limit = int(daily_limit)
        self.profiles = tuple(profiles)
        self.clock = clock

    # ------------------------------------------------------------ 예약

    def effective_limit(self, daily_limit: int | None = None) -> int:
        """화면에서 낮춘 상한(있으면). 설정값(`limits.daily_max_comments`)보다 높일 수는 없다."""
        if daily_limit is None:
            return self.daily_limit
        return max(0, min(int(daily_limit), self.daily_limit))

    def reserve(
        self,
        video_id: str,
        target: str,
        profile: str,
        draft_id: int,
        *,
        daily_limit: int | None = None,
    ) -> int:
        """게시를 시작하기 전에 자리를 잡는다. 잡은 `posts.id`를 돌려준다. 막히면 AppError."""
        check_target(target)
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        if profile not in self.profiles:
            raise AppError(ErrorKind.PROFILE_UNKNOWN, detail=f"프로필 {profile!r}")
        limit = self.effective_limit(daily_limit)
        now = self.clock()
        day = kst_day(now)
        stamp = now.isoformat()
        with db.immediate(self.db_path) as conn:
            draft = conn.execute(
                "SELECT video_id, status FROM drafts WHERE id = ?", (int(draft_id),)
            ).fetchone()
            if draft is None:
                raise AppError(ErrorKind.DRAFT_NOT_FOUND, detail=f"초안 {draft_id}")
            if draft["video_id"] != video_id:
                raise AppError(
                    ErrorKind.DRAFT_NOT_APPROVED, detail=f"초안 {draft_id}은 다른 영상의 초안"
                )
            if draft["status"] != "approved":
                raise AppError(
                    ErrorKind.DRAFT_NOT_APPROVED,
                    detail=f"초안 {draft_id} 상태: {draft['status']}",
                )
            used = _count_today(conn, target, day)
            if used >= limit:
                raise AppError(
                    ErrorKind.DAILY_LIMIT_REACHED,
                    detail=f"{target} 오늘 {used} / {limit}",
                    extra={"used": used, "daily_limit": limit},
                )
            try:
                cur = conn.execute(
                    "INSERT INTO posts(target, video_id, profile, draft_id, status, day, attempts, "
                    "created_at, updated_at) VALUES (?,?,?,?,'reserved',?,1,?,?)",
                    (target, video_id, profile, int(draft_id), day, stamp, stamp),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT id, status FROM posts WHERE target = ? AND video_id = ?",
                    (target, video_id),
                ).fetchone()
                if existing is None:  # UNIQUE가 아닌 다른 제약(일어나지 않아야 한다)
                    raise
            if existing["status"] != "failed":
                doing = "게시 작업 중" if existing["status"] == "reserved" else "게시 완료"
                raise AppError(
                    ErrorKind.ALREADY_COMMENTED,
                    detail=f"{target} 영상 {video_id}: {doing}",
                    extra={"post_id": int(existing["id"]), "status": existing["status"]},
                )
            # 실패한 영상을 다시 시도: 같은 행을 예약으로 되돌린다(새 프로필·초안·오늘 날짜)
            conn.execute(
                "UPDATE posts SET status='reserved', profile=?, draft_id=?, day=?, "
                "attempts=attempts+1, reason='', updated_at=?, posted_at=NULL WHERE id=?",
                (profile, int(draft_id), day, stamp, int(existing["id"])),
            )
            return int(existing["id"])

    # ------------------------------------------------------------ 결과

    def mark_posted(
        self,
        post_id: int,
        *,
        comment_text: str | None = None,
        job_id: str = "",
        note: str = "",
    ) -> Post:
        """예약을 게시 완료로 바꾸고 기록에 success 한 줄. 댓글을 안 주면 그 초안 글을 쓴다.

        `note`(8단계)는 기록 줄의 사유 칸에 남기는 덧붙임(예: 「확인 못 함」). 실패 사유가 아니다.
        """
        return self._finish(post_id, "posted", comment_text=comment_text, job_id=job_id, note=note)

    def mark_failed(
        self,
        post_id: int,
        reason: str,
        *,
        comment_text: str | None = None,
        screenshot_path: str = "",
        job_id: str = "",
    ) -> Post:
        """예약을 실패로 바꾸고 기록에 failure 한 줄(사유·화면 캡처). 실패는 상한에 세지 않는다."""
        return self._finish(
            post_id,
            "failed",
            reason=reason,
            comment_text=comment_text,
            screenshot_path=screenshot_path,
            job_id=job_id,
        )

    def _finish(
        self,
        post_id: int,
        status: str,
        *,
        reason: str = "",
        comment_text: str | None,
        screenshot_path: str = "",
        job_id: str = "",
        note: str = "",
    ) -> Post:
        now = self.clock()
        stamp = now.isoformat()
        with db.immediate(self.db_path) as conn:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone()
            if row is None:
                raise LookupError(f"예약 {post_id}이 없습니다.")
            if row["status"] != "reserved":
                raise ValueError(
                    f"예약 {post_id}은 {row['status']} 상태라 {status}(으)로 바꿀 수 없습니다."
                )
            conn.execute(
                "UPDATE posts SET status=?, reason=?, updated_at=?, posted_at=? WHERE id=?",
                (status, reason, stamp, stamp if status == "posted" else None, int(post_id)),
            )
            if comment_text is None:
                draft = conn.execute(
                    "SELECT body FROM drafts WHERE id = ?", (row["draft_id"],)
                ).fetchone()
                comment_text = draft["body"] if draft else ""
            ledger.insert(
                conn,
                at=stamp,
                day=kst_day(now),
                action="post",
                result="success" if status == "posted" else "failure",
                video_id=row["video_id"],
                profile=row["profile"],
                comment_text=comment_text,
                target=row["target"],
                reason=reason or note,
                screenshot_path=screenshot_path,
                job_id=job_id,
                draft_id=row["draft_id"],
                post_id=int(post_id),
            )
        return self.get(post_id)

    # ------------------------------------------------------------ 조회

    def get(self, post_id: int) -> Post:
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),)).fetchone()
        if row is None:
            raise LookupError(f"예약 {post_id}이 없습니다.")
        return _post(row)

    def find(self, video_id: str, target: str) -> Post | None:
        check_target(target)
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM posts WHERE target = ? AND video_id = ?", (target, video_id)
            ).fetchone()
        return _post(row) if row else None

    def used_today(self, target: str) -> int:
        check_target(target)
        with db.session(self.db_path) as conn:
            return _count_today(conn, target, kst_day(self.clock()))

    def remaining_today(self, target: str, *, daily_limit: int | None = None) -> int:
        """오늘 그 대상에 더 달 수 있는 수(0 이상)."""
        return max(0, self.effective_limit(daily_limit) - self.used_today(target))

    def is_commented(self, video_id: str, target: str) -> bool:
        """그 대상에 댓글을 단(게시 완료) 영상인지."""
        post = self.find(video_id, target)
        return bool(post and post.status == "posted")

    def commented_map(self, video_ids: Iterable[str]) -> dict[str, dict[str, bool]]:
        """영상마다 {sandbox: 게시 완료?, youtube: 게시 완료?}. 목록 응답에 붙인다."""
        ids = list(dict.fromkeys(video_ids))
        out = {vid: {t: False for t in POST_TARGETS} for vid in ids}
        if not ids:
            return out
        marks = ",".join("?" * len(ids))
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT video_id, target FROM posts WHERE status='posted' "
                f"AND video_id IN ({marks})",
                ids,
            ).fetchall()
        for r in rows:
            out[r["video_id"]][r["target"]] = True
        return out


def _count_today(conn: sqlite3.Connection, target: str, day: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM posts WHERE target=? AND day=? "
            "AND status IN ('reserved', 'posted')",
            (target, day),
        ).fetchone()[0]
    )


def _post(row: sqlite3.Row) -> Post:
    return Post(
        id=int(row["id"]),
        target=row["target"],
        video_id=row["video_id"],
        profile=row["profile"],
        draft_id=int(row["draft_id"]),
        status=row["status"],
        day=row["day"],
        attempts=int(row["attempts"]),
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        posted_at=row["posted_at"],
    )
