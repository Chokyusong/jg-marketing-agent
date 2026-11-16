"""할당량 기록(한국 날짜)과 같은 검색 10분 저장."""

from datetime import UTC, datetime, timedelta

from app import db
from app.youtube.quota import (
    DAILY_QUOTA,
    QuotaTracker,
    SearchCache,
    kst_day,
    search_cache_key,
)


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def test_kst_day_boundary():
    # UTC 14:59 = 한국 23:59, UTC 15:00 = 한국 다음 날 00:00
    assert kst_day(datetime(2026, 11, 16, 14, 59, tzinfo=UTC)) == "2026-11-16"
    assert kst_day(datetime(2026, 11, 16, 15, 0, tzinfo=UTC)) == "2026-11-17"


def test_quota_adds_per_kst_day(tmp_db_path):
    db.init_db(tmp_db_path)
    clock = Clock(datetime(2026, 11, 16, 14, 0, tzinfo=UTC))
    quota = QuotaTracker(tmp_db_path, clock=clock)
    assert quota.used_today() == 0
    quota.add(100)
    quota.add(1)
    assert quota.used_today() == 101
    clock.advance(hours=1)  # 한국 자정을 넘김
    assert quota.used_today() == 0
    quota.add(1)
    assert quota.summary() == {"used_today": 1, "daily_limit": DAILY_QUOTA}


def test_cache_key_normalizes_spaces_and_separates_filters():
    a = search_cache_key("  연애   고민 ", order="date", period="week", max_results=12)
    b = search_cache_key("연애 고민", order="date", period="week", max_results=12)
    assert a == b
    assert a != search_cache_key("연애 고민", order="viewCount", period="week", max_results=12)
    assert a != search_cache_key("연애 고민", order="date", period="day", max_results=12)
    assert a != search_cache_key("연애 고민", order="date", period="week", max_results=20)


def test_cache_expires_after_ten_minutes(tmp_db_path):
    db.init_db(tmp_db_path)
    clock = Clock(datetime(2026, 11, 16, 3, 0, tzinfo=UTC))
    cache = SearchCache(tmp_db_path, clock=clock)
    assert cache.get("k") is None
    cache.put("k", ["AAAAAAAAAA1", "BBBBBBBBBB2"])
    clock.advance(minutes=9, seconds=59)
    assert cache.get("k") == ["AAAAAAAAAA1", "BBBBBBBBBB2"]
    clock.advance(seconds=1)
    assert cache.get("k") is None
    cache.put("k", ["CCCCCCCCCC3"])  # 새로 저장하면 다시 10분
    assert cache.get("k") == ["CCCCCCCCCC3"]
