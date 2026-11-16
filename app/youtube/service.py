"""영상 불러오기 서비스: 클라이언트 + 할당량 + 10분 저장 + `videos` 표.

라우터는 이 모듈만 부른다(라우터에 판단 로직을 두지 않는다, DESIGN 3.2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app import db
from app.errors import AppError, ErrorKind
from app.youtube.client import Video, YouTubeClient
from app.youtube.quota import CACHE_TTL, Clock, QuotaTracker, SearchCache, search_cache_key
from app.youtube.url_parser import is_video_id, parse_video_id

PERIODS: dict[str, timedelta | None] = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "any": None,
}
ORDERS = ("date", "relevance", "viewCount")


@dataclass(frozen=True)
class StoredVideo:
    video: Video
    source: str
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self.video), "source": self.source, "fetched_at": self.fetched_at}


@dataclass(frozen=True)
class SearchResult:
    query: str
    order: str
    period: str
    max_results: int
    cached: bool
    videos: list[StoredVideo]


VIDEO_FIELDS = tuple(f.name for f in fields(Video))
_VIDEO_COLUMNS = ", ".join(VIDEO_FIELDS)


def _row_to_stored(row: Any) -> StoredVideo:
    video = Video(**{name: row[name] for name in VIDEO_FIELDS})
    return StoredVideo(video=video, source=row["source"], fetched_at=row["fetched_at"])


class VideoService:
    def __init__(
        self,
        client: YouTubeClient,
        *,
        db_path: Path,
        quota: QuotaTracker,
        cache: SearchCache,
        clock: Clock,
    ) -> None:
        self.client = client
        self.db_path = db_path
        self.quota = quota
        self.cache = cache
        self.clock = clock

    # -- videos 표

    def _save(self, videos: list[Video], source: str) -> list[StoredVideo]:
        fetched_at = self.clock().isoformat()
        rows = [(*(getattr(v, n) for n in VIDEO_FIELDS), fetched_at, source) for v in videos]
        placeholders = ", ".join("?" * (len(VIDEO_FIELDS) + 2))
        with db.session(self.db_path) as conn:
            conn.executemany(
                f"INSERT INTO videos({_VIDEO_COLUMNS}, fetched_at, source) "
                f"VALUES ({placeholders}) ON CONFLICT(video_id) DO UPDATE SET "
                "title=excluded.title, channel_id=excluded.channel_id, "
                "channel_title=excluded.channel_title, description=excluded.description, "
                "published_at=excluded.published_at, thumbnail_url=excluded.thumbnail_url, "
                "duration_seconds=excluded.duration_seconds, view_count=excluded.view_count, "
                "like_count=excluded.like_count, comment_count=excluded.comment_count, "
                "fetched_at=excluded.fetched_at, source=excluded.source",
                rows,
            )
        return [StoredVideo(video=v, source=source, fetched_at=fetched_at) for v in videos]

    def _load(self, video_ids: list[str]) -> dict[str, StoredVideo]:
        if not video_ids:
            return {}
        marks = ", ".join("?" * len(video_ids))
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT {_VIDEO_COLUMNS}, fetched_at, source FROM videos "
                f"WHERE video_id IN ({marks})",
                video_ids,
            ).fetchall()
        return {row["video_id"]: _row_to_stored(row) for row in rows}

    def _is_fresh(self, stored: StoredVideo) -> bool:
        return self.clock() - datetime.fromisoformat(stored.fetched_at) < CACHE_TTL

    # -- 기능

    def search(
        self, query: str, *, order: str, period: str, max_results: int
    ) -> SearchResult:
        query = " ".join(query.split())
        key = search_cache_key(query, order=order, period=period, max_results=max_results)

        cached_ids = self.cache.get(key)
        if cached_ids is not None:
            stored = self._load(cached_ids)
            if all(i in stored for i in cached_ids):
                videos = [stored[i] for i in cached_ids]
                return SearchResult(query, order, period, max_results, True, videos)

        span = PERIODS[period]
        published_after = self.clock() - span if span else None
        ids = self.client.search_video_ids(
            query, max_results=max_results, order=order, published_after=published_after
        )
        videos = self._save(self.client.get_videos(ids), source="search") if ids else []
        self.cache.put(key, [s.video.video_id for s in videos])
        return SearchResult(query, order, period, max_results, False, videos)

    def get(self, video_id: str, *, source: str = "link") -> StoredVideo:
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        stored = self._load([video_id]).get(video_id)
        if stored is not None and self._is_fresh(stored):
            return stored
        video = self.client.get_video(video_id)
        keep_source = stored.source if stored is not None else source
        return self._save([video], source=keep_source)[0]

    def resolve(self, url: str) -> StoredVideo:
        return self.get(parse_video_id(url), source="link")
