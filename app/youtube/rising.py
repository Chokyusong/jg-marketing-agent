"""뜨기 직전 영상 찾기(가점, DESIGN 7절 · PLAYBOOK 10단계 1번). **초안까지만** 만든다.

- 조회수 1,000~5,000이면서 시간당 150회 이상이려면 올린 지 약 33시간(5,000 ÷ 150) 안이어야 한다.
  그래서 `publishedAfter = 지금 − 34시간`, 검색어 `rising.query`(기본 "연애"), 최신순, 최대 50개
  (검색 1회 = 100단위) → 영상 상세(1단위) → `min_views ≤ 조회수 ≤ max_views`이면서
  `조회수 ÷ 올린 뒤 지난 시간 ≥ min_views_per_hour` → 시간당 조회수가 큰 순서.
- 지난 시간이 6분보다 짧으면 0.1시간으로 본다
  (막 올린 영상의 시간당 조회수가 터무니없이 커지지 않게).
- 시간당 조회수는 조회수를 받은 때(`fetched_at`) 기준으로 센다.
  10분 저장한 결과를 다시 보여도 같은 값.
- 쇼츠 빼기는 ①칸의 「쇼츠 빼기」를 따른다(기준 길이는 `discover.shorts_under_seconds`).
- 같은 요청(검색어·조건·쇼츠 빼기)은 10분 동안 저장한 결과를 쓴다(`search_cache`, 할당량 절약).
- 이 목록의 영상은 `videos.source = 'rising'`로 저장한다. 게시 작업은 그 출처의 영상을 거절한다
  (`app/browser/jobs.py`). 같은 영상을 [영상 불러오기]나 링크로 다시 불러오면 출처가 바뀌어
  게시할 수 있다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app import db
from app.youtube.quota import Clock
from app.youtube.service import StoredVideo, VideoService, is_short

if TYPE_CHECKING:  # 설정 모듈과 서로 부르지 않게 모양만 가져온다
    from app.config import RisingSettings

RISING_WINDOW = timedelta(hours=34)
RISING_POOL = 50  # 검색으로 받는 후보 수(최대)
MIN_HOURS = 0.1  # 6분보다 짧으면 0.1시간으로 본다


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def hours_since(published_at: str, now: datetime) -> float | None:
    """올린 뒤 지난 시간(시간 단위). 6분 미만은 0.1. 올린 때를 모르면 None."""
    published = _parse_time(published_at)
    if published is None:
        return None
    hours = (now - published).total_seconds() / 3600
    return max(hours, MIN_HOURS)


def views_per_hour(view_count: int | None, published_at: str, now: datetime) -> float | None:
    hours = hours_since(published_at, now)
    if hours is None or view_count is None:
        return None
    return view_count / hours


def is_rising(view_count: int | None, per_hour: float | None, rule: RisingSettings) -> bool:
    """조회수 범위 안이고 시간당 조회수가 하한 이상인지(경계값 포함)."""
    if view_count is None or per_hour is None:
        return False
    return rule.min_views <= view_count <= rule.max_views and per_hour >= rule.min_views_per_hour


@dataclass(frozen=True)
class RisingItem:
    stored: StoredVideo
    views_per_hour: float


@dataclass(frozen=True)
class RisingResult:
    query: str
    cached: bool
    items: list[RisingItem]
    rule: RisingSettings
    checked: int = 0  # 검색으로 받아 조건을 본 영상 수
    exclude_shorts: bool = False
    shorts_excluded: int = 0


def rising_cache_key(rule: RisingSettings, *, exclude_shorts: bool, shorts_under: int) -> str:
    body = {
        "rising": " ".join(rule.query.split()),
        "min": rule.min_views,
        "max": rule.max_views,
        "per_hour": rule.min_views_per_hour,
        "no_shorts": bool(exclude_shorts),
        "short_s": int(shorts_under) if exclude_shorts else None,
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


class RisingService:
    def __init__(self, videos: VideoService, *, rule: RisingSettings, clock: Clock) -> None:
        self.videos = videos
        self.rule = rule
        self.clock = clock

    def _per_hour(self, stored: StoredVideo) -> float | None:
        fetched = _parse_time(stored.fetched_at) or self.clock()
        return views_per_hour(stored.video.view_count, stored.video.published_at, fetched)

    def _rank(self, stored: list[StoredVideo]) -> list[RisingItem]:
        items = []
        for s in stored:
            per_hour = self._per_hour(s)
            if is_rising(s.video.view_count, per_hour, self.rule):
                assert per_hour is not None
                items.append(RisingItem(s, per_hour))
        items.sort(key=lambda i: i.views_per_hour, reverse=True)  # 같으면 검색 순서(최신순)
        return items

    def find(self, *, exclude_shorts: bool) -> RisingResult:
        """뜨기 직전 영상 목록. 검색 1회(100단위) + 상세(1단위). 10분 안의 같은 요청은 저장한 것."""
        rule = self.rule
        under = self.videos.shorts_under_seconds
        key = rising_cache_key(rule, exclude_shorts=exclude_shorts, shorts_under=under)
        cache = self.videos.cache

        entry = cache.get_entry(key)
        if entry is not None:
            data = self._cached(key)
            ids = data.get("ids") or []
            stored = self.videos.load(ids)
            if all(i in stored for i in ids):
                ordered = [stored[i] for i in ids]
                self.videos.mark_source(ids, "rising")
                ordered = [StoredVideo(s.video, "rising", s.fetched_at) for s in ordered]
                return RisingResult(
                    rule.query, True, self._rank(ordered), rule,
                    checked=int(data.get("checked") or 0),
                    exclude_shorts=exclude_shorts,
                    shorts_excluded=int(data.get("shorts_excluded") or 0),
                )

        published_after = self.clock() - RISING_WINDOW
        ids = self.videos.client.search_video_ids(
            rule.query, max_results=RISING_POOL, order="date", published_after=published_after
        )
        found = self.videos.client.get_videos(ids) if ids else []
        checked = len(found)
        excluded = 0
        if exclude_shorts:
            kept = [v for v in found if not is_short(v, under)]
            excluded = len(found) - len(kept)
            found = kept
        # 조건을 보기 전에 저장한다(조회수를 받은 때가 fetched_at). 고른 것만 rising으로 남긴다
        fetched_at = self.clock().isoformat()
        candidates = [StoredVideo(v, "rising", fetched_at) for v in found]
        items = self._rank(candidates)
        saved = self.videos.save_videos([i.stored.video for i in items], source="rising")
        by_id = {s.video.video_id: s for s in saved}
        items = [RisingItem(by_id[i.stored.video.video_id], i.views_per_hour) for i in items]
        self._store(key, [i.stored.video.video_id for i in items], checked, excluded)
        return RisingResult(
            rule.query, False, items, rule, checked=checked,
            exclude_shorts=exclude_shorts, shorts_excluded=excluded,
        )

    # -- 10분 저장(search_cache 표를 같이 쓴다. 값은 객체)

    def _store(self, key: str, ids: list[str], checked: int, excluded: int) -> None:
        value = {"ids": ids, "shorts_excluded": excluded, "checked": checked}
        with db.session(self.videos.cache.db_path) as conn:
            conn.execute(
                "INSERT INTO search_cache(cache_key, video_ids, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "video_ids = excluded.video_ids, created_at = excluded.created_at",
                (key, json.dumps(value), self.videos.cache.clock().isoformat()),
            )

    def _cached(self, key: str) -> dict:
        with db.session(self.videos.cache.db_path) as conn:
            row = conn.execute(
                "SELECT video_ids FROM search_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        data = json.loads(row["video_ids"]) if row else {}
        return data if isinstance(data, dict) else {"ids": list(data)}
