"""운영 규칙(7단계, 평가 15점): 영상당 1개 · 하루 상한(한국 날짜) · 승인한 초안만 · 동시 요청.

DB 거래(`BEGIN IMMEDIATE`)와 `UNIQUE(target, video_id)` 제약으로 막는지를 임시 SQLite로 확인한다.
네트워크·LLM 없이 돈다. 시간은 고정 시계로만 흘린다.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.errors import AppError
from app.ops.rules import PostRules

PROFILES = ("유튜브1", "유튜브2", "유튜브3")
P1 = PROFILES[0]


class Clock:
    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 11, 16, 3, 0, tzinfo=UTC)  # 한국 12:00

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


def vid(n: int) -> str:
    return f"VID{n:08d}"  # 11자 영상 ID


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def path(tmp_db_path):
    db.init_db(tmp_db_path)
    return tmp_db_path


def add_draft(path, video_id: str, *, status: str = "approved", body: str | None = None) -> int:
    """영상과 초안 한 개를 넣고 초안 id를 돌려준다(5단계 표를 그대로 쓴다)."""
    now = "2026-11-16T03:00:00+00:00"
    body = body or f"[광고] {video_id} 영상의 '첫 장면' 이야기에 공감해요. 운명원에 상담해 보세요."
    with db.session(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO videos(video_id, title, fetched_at, source) "
            "VALUES (?, ?, ?, 'search')",
            (video_id, f"영상 {video_id}", now),
        )
        cur = conn.execute(
            "INSERT INTO drafts(video_id, body, validation_json, passed, status, created_at, "
            "updated_at, approved_at) VALUES (?, ?, '{}', 1, ?, ?, ?, ?)",
            (video_id, body, status, now, now, now if status == "approved" else None),
        )
        return int(cur.lastrowid)


@pytest.fixture
def make_rules(path, clock):
    def _make(limit: int = 10) -> PostRules:
        return PostRules(path, daily_limit=limit, profiles=PROFILES, clock=clock)

    return _make


@pytest.fixture
def rules(make_rules) -> PostRules:
    return make_rules()


def reserve(rules: PostRules, path, n: int, target: str = "sandbox", **kw) -> int:
    return rules.reserve(vid(n), target, kw.pop("profile", P1), add_draft(path, vid(n)), **kw)


def kind_of(excinfo) -> str:
    return str(excinfo.value.kind)


def post_rows(path) -> list[sqlite3.Row]:
    with db.session(path) as conn:
        return conn.execute("SELECT * FROM posts ORDER BY id").fetchall()


def run_rows(path) -> list[sqlite3.Row]:
    with db.session(path) as conn:
        return conn.execute("SELECT * FROM runs ORDER BY id").fetchall()


# ---------------------------------------------------------------- 예약 기본


def test_reserve_makes_reserved_row_with_korean_day(rules, path, clock):
    clock.now = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)  # 한국 11월 17일 00:30
    post_id = reserve(rules, path, 1)
    post = rules.get(post_id)
    assert post.status == "reserved"
    assert post.day == "2026-11-17"  # UTC 날짜(16일)가 아니라 한국 날짜
    assert post.target == "sandbox" and post.profile == P1 and post.attempts == 1
    assert post.posted_at is None


def test_same_video_twice_second_is_rejected(rules, path):
    first = reserve(rules, path, 1)
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", P1, add_draft(path, vid(1)))
    assert kind_of(exc) == "already_commented"
    assert exc.value.http_status == 409
    assert exc.value.extra["post_id"] == first and exc.value.extra["status"] == "reserved"
    assert len(post_rows(path)) == 1


def test_posted_video_is_rejected_forever_not_just_today(rules, path, clock):
    post_id = reserve(rules, path, 1)
    rules.mark_posted(post_id)
    clock.advance(days=3)  # 날짜가 바뀌어도 영상당 1개는 그대로
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 1)
    assert kind_of(exc) == "already_commented"
    assert exc.value.extra["status"] == "posted"
    assert "게시 완료" in exc.value.detail


def test_same_video_rejected_even_with_other_profile(rules, path):
    reserve(rules, path, 1, profile="유튜브1")
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 1, profile="유튜브2")
    assert kind_of(exc) == "already_commented"


def test_db_unique_constraint_itself_blocks_duplicates(rules, path):
    # 앱 코드를 거치지 않고 넣어도 DB 제약이 막는다
    reserve(rules, path, 1)
    with pytest.raises(sqlite3.IntegrityError), db.session(path) as conn:
        conn.execute(
            "INSERT INTO posts(target, video_id, profile, draft_id, day, created_at, updated_at) "
            "VALUES ('sandbox', ?, '유튜브2', 1, '2026-11-16', 'now', 'now')",
            (vid(1),),
        )


# ---------------------------------------------------------------- 하루 상한


def test_limit_ten_then_eleventh_rejected(rules, path):
    for n in range(10):
        reserve(rules, path, n)
    assert rules.remaining_today("sandbox") == 0
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 10)
    assert kind_of(exc) == "daily_limit_reached"
    assert exc.value.http_status == 429
    assert exc.value.extra == {"used": 10, "daily_limit": 10}
    assert len(post_rows(path)) == 10  # 거절한 것은 넣지 않는다


def test_posted_and_reserved_both_count(rules, path):
    for n in range(10):
        post_id = reserve(rules, path, n)
        if n % 2:
            rules.mark_posted(post_id)
    assert rules.used_today("sandbox") == 10
    with pytest.raises(AppError):
        reserve(rules, path, 99)


def test_korean_midnight_resets_the_count(rules, path, clock):
    clock.now = datetime(2026, 11, 16, 14, 58, tzinfo=UTC)  # 한국 23:58
    for n in range(10):
        reserve(rules, path, n)
    with pytest.raises(AppError):
        reserve(rules, path, 10)
    clock.advance(minutes=1)  # 한국 23:59 — 아직 같은 날
    with pytest.raises(AppError):
        reserve(rules, path, 10)
    clock.advance(minutes=1)  # 한국 00:00(UTC로는 여전히 16일)
    assert clock.now.date().day == 16
    post_id = reserve(rules, path, 10)
    assert rules.get(post_id).day == "2026-11-17"
    assert rules.remaining_today("sandbox") == 9


def test_utc_midnight_does_not_reset(rules, path, clock):
    clock.now = datetime(2026, 11, 16, 23, 50, tzinfo=UTC)  # 한국 17일 08:50
    for n in range(10):
        reserve(rules, path, n)
    clock.advance(minutes=20)  # UTC 날짜는 바뀌지만 한국은 같은 날(09:10)
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 10)
    assert kind_of(exc) == "daily_limit_reached"


def test_lower_limit_from_screen_and_cannot_raise_above_config(rules, path):
    for n in range(3):
        reserve(rules, path, n, daily_limit=3)
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 3, daily_limit=3)
    assert exc.value.extra == {"used": 3, "daily_limit": 3}
    # 설정값(10)보다 높여 달라고 해도 10에서 막힌다
    for n in range(3, 10):
        reserve(rules, path, n, daily_limit=50)
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 10, daily_limit=50)
    assert exc.value.extra["daily_limit"] == 10
    assert rules.effective_limit(-5) == 0 and rules.effective_limit(None) == 10


def test_limit_zero_rejects_first(make_rules, path):
    with pytest.raises(AppError) as exc:
        reserve(make_rules(0), path, 1)
    assert kind_of(exc) == "daily_limit_reached"


def test_negative_limit_is_a_setup_error(path, clock):
    with pytest.raises(ValueError):
        PostRules(path, daily_limit=-1, profiles=PROFILES, clock=clock)


# ---------------------------------------------------------------- 실패와 다시 시도


def test_failure_is_not_counted(rules, path):
    ids = [reserve(rules, path, n) for n in range(10)]
    rules.mark_failed(ids[0], "게시 단추를 찾지 못함")
    assert rules.used_today("sandbox") == 9
    assert rules.remaining_today("sandbox") == 1
    reserve(rules, path, 10)  # 실패한 자리만큼 하나 더 된다
    with pytest.raises(AppError):
        reserve(rules, path, 11)


def test_retry_after_failure_reuses_the_row(rules, path, clock):
    post_id = reserve(rules, path, 1, profile="유튜브1")
    rules.mark_failed(post_id, "응답 지연")
    clock.advance(minutes=5)
    new_draft = add_draft(path, vid(1))
    again = rules.reserve(vid(1), "sandbox", "유튜브2", new_draft)
    assert again == post_id  # 같은 행을 예약으로 되돌린다
    post = rules.get(post_id)
    assert post.status == "reserved" and post.attempts == 2
    assert post.profile == "유튜브2" and post.draft_id == new_draft and post.reason == ""
    assert len(post_rows(path)) == 1
    rules.mark_posted(post_id)
    assert rules.is_commented(vid(1), "sandbox")


def test_retry_counts_again_and_is_rejected_at_limit(rules, path):
    ids = [reserve(rules, path, n) for n in range(10)]
    rules.mark_failed(ids[0], "실패")
    reserve(rules, path, 10)  # 빈 자리를 다른 영상이 썼다
    with pytest.raises(AppError) as exc:
        reserve(rules, path, 0)  # 실패한 영상의 재시도도 상한에 걸린다
    assert kind_of(exc) == "daily_limit_reached"
    assert rules.get(ids[0]).status == "failed"


def test_retry_yesterdays_failure_counts_today(rules, path, clock):
    post_id = reserve(rules, path, 1)
    rules.mark_failed(post_id, "실패")
    clock.advance(days=1)
    reserve(rules, path, 1)
    assert rules.get(post_id).day == "2026-11-17"
    assert rules.used_today("sandbox") == 1


def test_failure_still_leaves_a_record(rules, path):
    post_id = reserve(rules, path, 1)
    rules.mark_failed(post_id, "게시 단추 없음", screenshot_path="error_screenshots/j1.png",
                      job_id="j1")
    rows = run_rows(path)
    assert len(rows) == 1
    r = rows[0]
    assert (r["action"], r["result"], r["reason"]) == ("post", "failure", "게시 단추 없음")
    assert r["screenshot_path"] == "error_screenshots/j1.png" and r["job_id"] == "j1"
    assert r["video_id"] == vid(1) and r["profile"] == P1 and r["target"] == "sandbox"
    assert r["video_title"] == f"영상 {vid(1)}"  # 제목은 videos에서
    assert r["comment_text"].startswith("[광고]")  # 댓글을 안 주면 초안 글
    assert r["post_id"] == post_id


def test_mark_posted_records_success_and_marks_commented(rules, path, clock):
    post_id = reserve(rules, path, 1)
    assert not rules.is_commented(vid(1), "sandbox")  # 예약만으로는 아직 단 것이 아니다
    clock.advance(minutes=2)
    post = rules.mark_posted(post_id, comment_text="[광고] 실제로 올린 글", job_id="j9")
    assert post.status == "posted" and post.posted_at == clock.now.isoformat()
    assert rules.is_commented(vid(1), "sandbox")
    assert not rules.is_commented(vid(1), "youtube")
    r = run_rows(path)[-1]
    assert (r["action"], r["result"]) == ("post", "success")
    assert r["comment_text"] == "[광고] 실제로 올린 글"
    assert r["at"] == clock.now.isoformat() and r["day"] == "2026-11-16"


@pytest.mark.parametrize("first", ["posted", "failed"])
def test_finished_post_cannot_be_finished_again(rules, path, first):
    post_id = reserve(rules, path, 1)
    if first == "posted":
        rules.mark_posted(post_id)
    else:
        rules.mark_failed(post_id, "실패")
    with pytest.raises(ValueError):
        rules.mark_posted(post_id)
    with pytest.raises(ValueError):
        rules.mark_failed(post_id, "또 실패")
    assert len(run_rows(path)) == 1  # 잘못 부른 것은 기록하지 않는다


def test_unknown_post_id(rules):
    with pytest.raises(LookupError):
        rules.mark_posted(999)
    with pytest.raises(LookupError):
        rules.get(999)


# ---------------------------------------------------------------- 대상 나누기


def test_sandbox_and_youtube_are_counted_separately(rules, path):
    for n in range(10):
        reserve(rules, path, n, "sandbox")
    with pytest.raises(AppError):
        reserve(rules, path, 10, "sandbox")
    # 같은 영상도 대상이 다르면 따로(sandbox 예행 뒤 실제 게시)
    for n in range(10):
        rules.reserve(vid(n), "youtube", P1, add_draft(path, vid(n)))
    assert rules.used_today("sandbox") == 10 and rules.used_today("youtube") == 10
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(10), "youtube", P1, add_draft(path, vid(10)))
    assert kind_of(exc) == "daily_limit_reached"


def test_commented_map_per_target(rules, path):
    a = reserve(rules, path, 1, "sandbox")
    rules.mark_posted(a)
    b = rules.reserve(vid(2), "youtube", P1, add_draft(path, vid(2)))
    rules.mark_posted(b)
    reserve(rules, path, 3, "sandbox")  # 예약만
    marks = rules.commented_map([vid(1), vid(2), vid(3), vid(4), vid(1)])
    assert marks == {
        vid(1): {"sandbox": True, "youtube": False},
        vid(2): {"sandbox": False, "youtube": True},
        vid(3): {"sandbox": False, "youtube": False},
        vid(4): {"sandbox": False, "youtube": False},
    }
    assert rules.commented_map([]) == {}


@pytest.mark.parametrize("target", ["assist", "", "SANDBOX"])
def test_unknown_target_is_a_programming_error(rules, path, target):
    with pytest.raises(ValueError):
        rules.reserve(vid(1), target, P1, add_draft(path, vid(1)))
    with pytest.raises(ValueError):
        rules.remaining_today(target)


# ---------------------------------------------------------------- 승인한 초안만


@pytest.mark.parametrize("status", ["draft", "superseded"])
def test_unapproved_draft_is_rejected(rules, path, status):
    draft_id = add_draft(path, vid(1), status=status)
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", P1, draft_id)
    assert kind_of(exc) == "draft_not_approved"
    assert exc.value.http_status == 409
    assert post_rows(path) == []


def test_draft_of_other_video_is_rejected(rules, path):
    other = add_draft(path, vid(2))
    add_draft(path, vid(1))
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", P1, other)
    assert kind_of(exc) == "draft_not_approved"
    assert "다른 영상" in exc.value.detail


def test_missing_draft(rules):
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", P1, 12345)
    assert kind_of(exc) == "draft_not_found"


def test_unapproved_draft_checked_before_limit(make_rules, path):
    rules = make_rules(0)
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", P1, add_draft(path, vid(1), status="draft"))
    assert kind_of(exc) == "draft_not_approved"


def test_unknown_profile_and_bad_video_id(rules, path):
    draft_id = add_draft(path, vid(1))
    with pytest.raises(AppError) as exc:
        rules.reserve(vid(1), "sandbox", "유튜브9", draft_id)
    assert kind_of(exc) == "profile_unknown"
    with pytest.raises(AppError) as exc:
        rules.reserve("not-an-id", "sandbox", P1, draft_id)
    assert kind_of(exc) == "invalid_url"


# ---------------------------------------------------------------- 동시 요청


def _race(n_threads: int, job) -> list[object]:
    """스레드를 한꺼번에 출발시켜 job(i)를 부르고 결과(값 또는 예외)를 모은다."""
    barrier = threading.Barrier(n_threads)
    results: list[object] = [None] * n_threads

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = job(i)
        except Exception as exc:  # noqa: BLE001 — 결과로 모아서 본다
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


@pytest.mark.parametrize("round_no", range(5))
def test_two_threads_same_video_only_one_wins(rules, path, round_no):
    drafts = [add_draft(path, vid(round_no)), add_draft(path, vid(round_no))]
    results = _race(2, lambda i: rules.reserve(vid(round_no), "sandbox", PROFILES[i], drafts[i]))
    wins = [r for r in results if isinstance(r, int)]
    losses = [r for r in results if isinstance(r, AppError)]
    assert len(wins) == 1 and len(losses) == 1, results
    assert str(losses[0].kind) == "already_commented"
    assert len(post_rows(path)) == 1


def test_many_threads_different_videos_never_exceed_limit(rules, path):
    drafts = [add_draft(path, vid(n)) for n in range(25)]
    results = _race(25, lambda i: rules.reserve(vid(i), "sandbox", P1, drafts[i]))
    wins = [r for r in results if isinstance(r, int)]
    losses = [r for r in results if isinstance(r, AppError)]
    assert len(wins) == 10, results
    assert len(losses) == 15 and {str(e.kind) for e in losses} == {"daily_limit_reached"}
    assert rules.used_today("sandbox") == 10
    assert len(post_rows(path)) == 10


def test_many_threads_mixed_same_and_different_videos(rules, path):
    # 영상 6개에 스레드 3개씩(18개): 영상마다 하나만, 합쳐서 상한(10) 이하
    drafts = [add_draft(path, vid(i % 6)) for i in range(18)]
    results = _race(18, lambda i: rules.reserve(vid(i % 6), "sandbox", P1, drafts[i]))
    wins = [r for r in results if isinstance(r, int)]
    assert len(wins) == 6, results
    assert {str(e.kind) for e in results if isinstance(e, AppError)} == {"already_commented"}
    rows = post_rows(path)
    assert sorted(r["video_id"] for r in rows) == [vid(n) for n in range(6)]


def test_threads_on_both_targets_count_separately(rules, path):
    drafts = [add_draft(path, vid(i % 12)) for i in range(24)]
    targets = ["sandbox", "youtube"]
    results = _race(
        24, lambda i: rules.reserve(vid(i % 12), targets[i // 12], P1, drafts[i])
    )
    assert sum(isinstance(r, int) for r in results) == 20  # 대상마다 10개
    assert rules.used_today("sandbox") == 10 and rules.used_today("youtube") == 10


# ---------------------------------------------------------------- 기록은 지우지 않는다


def test_runs_rows_cannot_be_deleted(rules, path):
    rules.mark_failed(reserve(rules, path, 1), "실패")
    with pytest.raises(sqlite3.DatabaseError, match="지우지 않는 기록"), db.session(path) as conn:
        conn.execute("DELETE FROM runs")
    assert len(run_rows(path)) == 1


def test_rejections_write_nothing(rules, path):
    reserve(rules, path, 1)
    for attempt in (
        lambda: reserve(rules, path, 1),
        lambda: rules.reserve(vid(2), "sandbox", P1, add_draft(path, vid(2), status="draft")),
        lambda: rules.reserve(vid(3), "sandbox", "없는 프로필", add_draft(path, vid(3))),
    ):
        with pytest.raises(AppError):
            attempt()
    assert len(post_rows(path)) == 1
    assert run_rows(path) == []  # 예약 거절은 게시 시도가 아니다(성공률에 섞지 않는다)
