"""프로필(이름 ↔ 폴더, 자동 배정)과 작업 기록(시간순, 오늘 통계) — 7단계."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from test_ops_rules import PROFILES, Clock, add_draft, vid

from app import db
from app.errors import AppError
from app.ops.ledger import Ledger
from app.ops.profiles import ProfileService
from app.ops.rules import PostRules


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def path(tmp_db_path):
    db.init_db(tmp_db_path)
    return tmp_db_path


@pytest.fixture
def rules(path, clock) -> PostRules:
    return PostRules(path, daily_limit=10, profiles=PROFILES, clock=clock)


@pytest.fixture
def profiles(path) -> ProfileService:
    return ProfileService(PROFILES, db_path=path)


@pytest.fixture
def ledger(path, clock) -> Ledger:
    return Ledger(path, daily_limit=10, clock=clock)


# ---------------------------------------------------------------- 프로필


def test_names_map_to_english_folders_in_order(profiles):
    items = profiles.list_profiles()
    assert [(p.name, p.folder, p.index) for p in items] == [
        ("유튜브1", "profile-1", 1),
        ("유튜브2", "profile-2", 2),
        ("유튜브3", "profile-3", 3),
    ]
    assert profiles.folder_of("유튜브3") == "profile-3"
    assert all(p.folder.isascii() for p in items)  # 한글 폴더 이름을 쓰지 않는다
    with pytest.raises(AppError) as exc:
        profiles.get("유튜브4")
    assert str(exc.value.kind) == "profile_unknown"


def test_auto_assignment_cycles_through_three(profiles, rules, path, clock):
    picked = []
    for n in range(7):
        p = profiles.pick_auto("sandbox")
        picked.append(p.name)
        rules.reserve(vid(n), "sandbox", p.name, add_draft(path, vid(n)))
        clock.advance(minutes=1)
    assert picked == ["유튜브1", "유튜브2", "유튜브3", "유튜브1", "유튜브2", "유튜브3", "유튜브1"]


def test_auto_assignment_cycles_even_when_clock_stands_still(profiles, rules, path):
    picked = []
    for n in range(6):
        p = profiles.pick_auto("sandbox")
        picked.append(p.name)
        rules.reserve(vid(n), "sandbox", p.name, add_draft(path, vid(n)))
    assert picked == ["유튜브1", "유튜브2", "유튜브3"] * 2


def test_auto_picks_least_recently_used_not_round_robin(profiles, rules, path, clock):
    for n, name in enumerate(["유튜브1", "유튜브2", "유튜브3"]):
        rules.reserve(vid(n), "sandbox", name, add_draft(path, vid(n)))
        clock.advance(minutes=1)
    # 사람이 유튜브1을 직접 골라 한 번 더 쓰면, 자동 배정은 가장 오래 안 쓴 유튜브2
    rules.reserve(vid(9), "sandbox", "유튜브1", add_draft(path, vid(9)))
    assert profiles.pick_auto("sandbox").name == "유튜브2"


def test_never_used_profile_comes_first(profiles, rules, path, clock):
    rules.reserve(vid(1), "sandbox", "유튜브2", add_draft(path, vid(1)))
    assert profiles.pick_auto("sandbox").name == "유튜브1"
    rules.reserve(vid(2), "sandbox", "유튜브1", add_draft(path, vid(2)))
    assert profiles.pick_auto("sandbox").name == "유튜브3"


def test_auto_assignment_is_per_target(profiles, rules, path):
    rules.reserve(vid(1), "sandbox", "유튜브1", add_draft(path, vid(1)))
    assert profiles.pick_auto("sandbox").name == "유튜브2"
    assert profiles.pick_auto("youtube").name == "유튜브1"


def test_failed_use_still_counts_as_used(profiles, rules, path):
    post_id = rules.reserve(vid(1), "sandbox", "유튜브1", add_draft(path, vid(1)))
    rules.mark_failed(post_id, "실패")
    assert profiles.pick_auto("sandbox").name == "유튜브2"


def test_resolve_auto_or_named(profiles):
    assert profiles.resolve("", "sandbox").name == "유튜브1"
    assert profiles.resolve(None, "sandbox").name == "유튜브1"
    assert profiles.resolve("auto", "sandbox").name == "유튜브1"
    assert profiles.resolve("유튜브3", "sandbox").name == "유튜브3"
    with pytest.raises(AppError):
        profiles.resolve("모르는 이름", "sandbox")


def _login(path, profile: str, state: str, at: datetime) -> None:
    with db.session(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profile_logins(profile, state, channel, checked_at, note) "
            "VALUES (?, ?, '', ?, '')",
            (profile, state, at.isoformat()),
        )


def _choose(profiles, clock, target="youtube", login=True):
    return profiles.choose_auto(target, login=login, now=clock(), trust=timedelta(hours=1))


def test_choose_auto_only_from_signed_in_profiles(profiles, rules, path, clock):
    """2026-11-17: 유튜브1·2는 로그인됨, 유튜브3은 확인한 적 없음 → 1과 2만 돌아가며."""
    _login(path, "유튜브1", "signed_in", clock())
    _login(path, "유튜브2", "signed_in", clock())
    picked = []
    for n in range(5):
        pick = _choose(profiles, clock)
        assert pick.confirmed is True and pick.note == ""
        picked.append(pick.profile.name)
        rules.reserve(vid(n), "youtube", pick.profile.name, add_draft(path, vid(n)))
        clock.advance(minutes=1)
    assert picked == ["유튜브1", "유튜브2", "유튜브1", "유튜브2", "유튜브1"]


def test_choose_auto_skips_never_used_but_unchecked_profile(profiles, rules, path, clock):
    """한 번도 안 쓴 프로필이 먼저였지만, 로그인을 확인하지 않았으면 고르지 않는다."""
    _login(path, "유튜브1", "signed_in", clock())
    _login(path, "유튜브2", "signed_in", clock())
    rules.reserve(vid(1), "youtube", "유튜브1", add_draft(path, vid(1)))
    rules.reserve(vid(2), "youtube", "유튜브2", add_draft(path, vid(2)))
    assert profiles.pick_auto("youtube").name == "유튜브3"  # 예전 규칙
    assert _choose(profiles, clock).profile.name == "유튜브1"  # 새 규칙


def test_choose_auto_single_signed_in_profile(profiles, path, clock):
    _login(path, "유튜브2", "signed_in", clock() - timedelta(days=3))  # 오래된 확인도 로그인됨
    _login(path, "유튜브1", "signed_out", clock() - timedelta(days=3))
    pick = _choose(profiles, clock)
    assert (pick.profile.name, pick.confirmed) == ("유튜브2", True)


def test_choose_auto_without_any_confirmed_profile_warns(profiles, path, clock):
    pick = _choose(profiles, clock)
    assert (pick.profile.name, pick.confirmed) == ("유튜브1", False)
    assert "로그인을 확인한 프로필이 없어 유튜브1로 해 봅니다" in pick.note
    assert "[로그인 확인]" in pick.note
    # 최근 「로그인 안 됨」은 뒤로 미룬다(예전과 같다)
    _login(path, "유튜브1", "signed_out", clock())
    pick = _choose(profiles, clock)
    assert pick.profile.name == "유튜브2" and pick.confirmed is False
    assert "유튜브2로" in pick.note


def test_choose_auto_all_signed_out(profiles, path, clock):
    for name in PROFILES:
        _login(path, name, "signed_out", clock())
    pick = _choose(profiles, clock)
    assert pick.confirmed is False and "로그인된 프로필이 없습니다" in pick.note


def test_choose_auto_practice_mode_ignores_login(profiles, path, clock):
    _login(path, "유튜브2", "signed_in", clock())
    pick = _choose(profiles, clock, target="sandbox", login=False)
    assert (pick.profile.name, pick.confirmed, pick.note) == ("유튜브1", None, "")


def test_choose_auto_ignores_unknown_profile_rows(profiles, path, clock):
    _login(path, "옛프로필", "signed_in", clock())
    assert _choose(profiles, clock).confirmed is False


def test_with_ro_particle():
    from app.ops.profiles import with_ro

    assert [with_ro(f"유튜브{i}") for i in (1, 2, 3, 6, 7)] == [
        "유튜브1로", "유튜브2로", "유튜브3으로", "유튜브6으로", "유튜브7로"
    ]
    assert with_ro("서울") == "서울로" and with_ro("계정") == "계정으로" and with_ro("") == ""


def test_empty_profile_list(path):
    with pytest.raises(AppError) as exc:
        ProfileService((), db_path=path).pick_auto("sandbox")
    assert str(exc.value.kind) == "profile_unknown"


# ---------------------------------------------------------------- 작업 기록


def test_recent_is_newest_first(ledger, clock):
    for action in ("analyze", "draft", "approve"):
        ledger.record(action, "info", video_id=vid(1))
        clock.advance(seconds=30)
    rows = ledger.recent(10)
    assert [r.action for r in rows] == ["approve", "draft", "analyze"]
    assert rows[0].at > rows[1].at > rows[2].at


def test_same_time_rows_keep_insert_order(ledger):
    ids = [ledger.record("draft", "info", reason=str(i)) for i in range(4)]
    assert [r.id for r in ledger.recent(10)] == ids[::-1]


def test_recent_limit_is_bounded(ledger):
    for i in range(7):
        ledger.record("draft", "info", reason=str(i))
    assert len(ledger.recent(5)) == 5
    assert len(ledger.recent(0)) == 1  # 최소 1
    assert ledger.count() == 7


def test_record_fills_title_and_korean_day(ledger, path, clock):
    add_draft(path, vid(1))  # videos에 「영상 VID00000001」
    clock.now = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)  # 한국 17일 00:30
    ledger.record("analyze", "info", video_id=vid(1), reason="핵심 고민 · 연락 문제")
    r = ledger.recent(1)[0]
    assert r.video_title == f"영상 {vid(1)}"
    assert r.day == "2026-11-17"
    assert r.result == "info" and r.reason == "핵심 고민 · 연락 문제"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action": "delete", "result": "info"},
        {"action": "post", "result": "ok"},
        {"action": "post", "result": "success", "target": "assist"},
    ],
)
def test_record_rejects_unknown_values(ledger, kwargs):
    action = kwargs.pop("action")
    result = kwargs.pop("result")
    with pytest.raises(ValueError):
        ledger.record(action, result, **kwargs)


def test_today_stats_empty_has_no_success_rate(ledger):
    s = ledger.today_stats("sandbox")
    assert (s.videos, s.drafts, s.posted, s.failed) == (0, 0, 0, 0)
    assert s.daily_limit == 10 and s.remaining == 10
    assert s.success_rate is None  # 기록 없음 → 화면은 –
    assert s.day == "2026-11-16" and s.target == "sandbox"


def test_today_stats_counts_videos_drafts_posts_and_rate(ledger, rules, path, clock):
    ledger.record("draft", "info", video_id=vid(1))
    ledger.record("draft", "info", video_id=vid(2))
    ledger.record("draft", "failure", video_id=vid(3), reason="AI 꺼짐")  # 만들지 못한 초안
    ledger.record("analyze", "info", video_id=vid(1))
    ids = [rules.reserve(vid(n), "sandbox", "유튜브1", add_draft(path, vid(n))) for n in range(4)]
    rules.mark_posted(ids[0])
    rules.mark_posted(ids[1])
    rules.mark_failed(ids[2], "게시 단추 없음")  # ids[3]은 예약 중
    s = ledger.today_stats("sandbox")
    assert s.videos == 3  # 예약 1 + 게시 2(실패는 세지 않는다)
    assert s.remaining == 7
    assert s.drafts == 2
    assert (s.posted, s.failed) == (2, 1)
    assert s.success_rate == pytest.approx(2 / 3)
    # 다른 대상은 따로
    y = ledger.today_stats("youtube")
    assert (y.videos, y.posted, y.failed, y.success_rate) == (0, 0, 0, None)
    assert y.drafts == 2  # 초안 수는 대상과 상관없다


def test_today_stats_only_today_in_korea(ledger, rules, path, clock):
    clock.now = datetime(2026, 11, 16, 14, 50, tzinfo=UTC)  # 한국 23:50
    ledger.record("draft", "info")
    rules.mark_posted(rules.reserve(vid(1), "sandbox", "유튜브1", add_draft(path, vid(1))))
    clock.advance(minutes=20)  # 한국 다음 날 00:10
    s = ledger.today_stats("sandbox")
    assert (s.videos, s.drafts, s.posted, s.success_rate) == (0, 0, 0, None)
    assert s.day == "2026-11-17"


def test_today_stats_lowered_limit(ledger, rules, path):
    for n in range(2):
        rules.reserve(vid(n), "sandbox", "유튜브1", add_draft(path, vid(n)))
    s = ledger.today_stats("sandbox", daily_limit=3)
    assert (s.videos, s.daily_limit, s.remaining) == (2, 3, 1)
    assert ledger.today_stats("sandbox", daily_limit=99).daily_limit == 10  # 설정값 위로는 못 올림


def test_all_failures_mean_zero_percent(ledger, rules, path):
    rules.mark_failed(rules.reserve(vid(1), "sandbox", "유튜브1", add_draft(path, vid(1))), "x")
    assert ledger.today_stats("sandbox").success_rate == 0.0


def test_today_stats_unknown_target(ledger):
    with pytest.raises(ValueError):
        ledger.today_stats("assist")
