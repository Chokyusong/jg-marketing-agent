"""할당량 사용 기록과 같은 검색 10분 저장(DESIGN 7절).

- 하루 10,000단위. 날짜는 한국 시각 기준으로 센다(실제 초기화는 태평양 자정이라
  화면에는 "오늘 사용량"의 참고값으로만 보인다).
- 같은 검색(검색어·정렬·기간·결과 수)은 10분 동안 SQLite에 저장한 결과를 쓴다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from app import db

KST = timezone(timedelta(hours=9), "KST")  # 한국은 서머타임이 없어 고정 시차로 충분하다
DAILY_QUOTA = 10_000
CACHE_TTL = timedelta(minutes=10)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def kst_day(moment: datetime) -> str:
    return moment.astimezone(KST).strftime("%Y-%m-%d")


class QuotaTracker:
    def __init__(self, db_path: Path, *, clock: Clock = utc_now) -> None:
        self.db_path = db_path
        self.clock = clock

    def add(self, units: int) -> None:
        day = kst_day(self.clock())
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO quota_usage(day, units) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET units = units + excluded.units",
                (day, int(units)),
            )

    def used_today(self) -> int:
        day = kst_day(self.clock())
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT units FROM quota_usage WHERE day = ?", (day,)).fetchone()
        return int(row["units"]) if row else 0

    def summary(self) -> dict[str, int]:
        return {"used_today": self.used_today(), "daily_limit": DAILY_QUOTA}


def search_cache_key(
    query: str, *, order: str, period: str, max_results: int, exclude_shorts: bool = False
) -> str:
    """같은 검색 10분 저장의 키. 쇼츠 제외 여부도 키에 든다(결과가 다르다)."""
    return json.dumps(
        {"q": " ".join(query.split()), "order": order, "period": period, "n": max_results,
         "no_shorts": bool(exclude_shorts)},
        ensure_ascii=False,
        sort_keys=True,
    )


class SearchCache:
    def __init__(self, db_path: Path, *, clock: Clock = utc_now, ttl: timedelta = CACHE_TTL):
        self.db_path = db_path
        self.clock = clock
        self.ttl = ttl

    def get(self, key: str) -> list[str] | None:
        entry = self.get_entry(key)
        return None if entry is None else entry[0]

    def get_entry(self, key: str) -> tuple[list[str], int] | None:
        """(영상 ID들, 뺀 쇼츠 수). 10분이 지났거나 없으면 None."""
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT video_ids, created_at FROM search_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        created = datetime.fromisoformat(row["created_at"])
        if self.clock() - created >= self.ttl:
            return None
        data = json.loads(row["video_ids"])
        if isinstance(data, dict):  # 쇼츠 제외 검색: {"ids": [...], "shorts_excluded": n}
            return list(data.get("ids") or []), int(data.get("shorts_excluded") or 0)
        return list(data), 0

    def put(self, key: str, video_ids: list[str], *, shorts_excluded: int | None = None) -> None:
        """`shorts_excluded`를 주면 뺀 쇼츠 수도 함께 저장한다(표는 그대로, 값만 객체로)."""
        value: object = list(video_ids)
        if shorts_excluded is not None:
            value = {"ids": list(video_ids), "shorts_excluded": int(shorts_excluded)}
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO search_cache(cache_key, video_ids, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "video_ids = excluded.video_ids, created_at = excluded.created_at",
                (key, json.dumps(value), self.clock().isoformat()),
            )
