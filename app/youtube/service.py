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
# 쇼츠 제외(실제 데이터 보정): 길이가 이 초 미만이거나 길이 정보가 없는 영상은 뺀다.
# 최신순 상위가 거의 쇼츠(댓글 0~3개)라 댓글 달 만한 영상이 보이지 않았다.
# R2: 기준은 설정값(`discover.shorts_under_seconds`, 화면의 「쇼츠 길이」).
# 유튜브 쇼츠는 3분까지라
# 기본 181초(3분 이하를 쇼츠로 본다). 예전 기준은 61초였다.
SHORTS_MIN_SECONDS = 181
# 쇼츠를 빼고도 max_results개를 채우려고 검색으로 받는 영상 수(검색 1회 = 100단위는 같다)
SHORTS_SEARCH_POOL = 50


def is_short(video: Video, under: int = SHORTS_MIN_SECONDS) -> bool:
    return video.duration_seconds is None or video.duration_seconds < under


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
    exclude_shorts: bool = False
    shorts_excluded: int = 0  # 검색으로 받은 후보 중 쇼츠라 뺀 수


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
        shorts_under_seconds: int = SHORTS_MIN_SECONDS,
    ) -> None:
        self.client = client
        self.shorts_under_seconds = int(shorts_under_seconds)
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

    # R4: 뜨기 직전 영상(rising.py)이 쓰는 공개 도우미
    def save_videos(self, videos: list[Video], *, source: str) -> list[StoredVideo]:
        return self._save(videos, source) if videos else []

    def load(self, video_ids: list[str]) -> dict[str, StoredVideo]:
        return self._load(video_ids)

    def mark_source(self, video_ids: list[str], source: str) -> None:
        """영상의 출처만 바꾼다(마지막으로 불러온 목록이 출처가 된다).

        뜨기 직전 목록에서 고른 영상은 초안까지만 되고(rising), 같은 영상을 [영상 불러오기]나
        링크로 다시 불러오면 search·link로 바뀌어 평소처럼 게시할 수 있다.
        """
        if not video_ids:
            return
        marks = ", ".join("?" * len(video_ids))
        with db.session(self.db_path) as conn:
            conn.execute(
                f"UPDATE videos SET source = ? WHERE video_id IN ({marks})",
                [source, *video_ids],
            )

    def _is_fresh(self, stored: StoredVideo) -> bool:
        return self.clock() - datetime.fromisoformat(stored.fetched_at) < CACHE_TTL

    # -- 기능

    def search(
        self,
        query: str,
        *,
        order: str,
        period: str,
        max_results: int,
        exclude_shorts: bool = False,
    ) -> SearchResult:
        """검색(100단위) + 상세(50개당 1단위). 같은 검색은 10분 동안 저장한 결과를 쓴다.

        `exclude_shorts`면 영상 ID를 넉넉히(최대 50개) 받아 상세를 본 뒤
        쇼츠(설정한 길이 미만·길이 없음)를
        빼고, 원래 순서대로 `max_results`개만 돌려준다. 검색 횟수와 단위는 그대로다.
        """
        query = " ".join(query.split())
        key = search_cache_key(
            query, order=order, period=period, max_results=max_results,
            exclude_shorts=exclude_shorts,
            shorts_under=self.shorts_under_seconds if exclude_shorts else None,
        )

        entry = self.cache.get_entry(key)
        if entry is not None:
            cached_ids, excluded = entry
            stored = self._load(cached_ids)
            if all(i in stored for i in cached_ids):
                self.mark_source(cached_ids, "search")  # R4: 뜨기 직전 목록에서 온 출처를 되돌린다
                videos = [
                    StoredVideo(stored[i].video, "search", stored[i].fetched_at) for i in cached_ids
                ]
                return SearchResult(
                    query, order, period, max_results, True, videos, exclude_shorts, excluded
                )

        span = PERIODS[period]
        published_after = self.clock() - span if span else None
        pool = max(max_results, SHORTS_SEARCH_POOL) if exclude_shorts else max_results
        ids = self.client.search_video_ids(
            query, max_results=pool, order=order, published_after=published_after
        )
        found = self.client.get_videos(ids) if ids else []
        excluded = 0
        if exclude_shorts:
            kept = [v for v in found if not is_short(v, self.shorts_under_seconds)]
            excluded = len(found) - len(kept)
            found = kept[:max_results]
        videos = self._save(found, source="search") if found else []
        ids_out = [s.video.video_id for s in videos]
        if exclude_shorts:
            self.cache.put(key, ids_out, shorts_excluded=excluded)
        else:
            self.cache.put(key, ids_out)
        return SearchResult(
            query, order, period, max_results, False, videos, exclude_shorts, excluded
        )

    def get(self, video_id: str, *, source: str = "link") -> StoredVideo:
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        stored = self._load([video_id]).get(video_id)
        if stored is not None and self._is_fresh(stored):
            return stored
        video = self.client.get_video(video_id)
        keep_source = stored.source if stored is not None else source
        return self._save([video], source=keep_source)[0]

    def stored(self, video_id: str) -> StoredVideo | None:
        """저장해 둔 영상 정보(오래됐어도 그대로). 없으면 None. YouTube를 부르지 않는다."""
        if not is_video_id(video_id):
            return None
        return self._load([video_id]).get(video_id)

    def resolve(self, url: str) -> StoredVideo:
        """링크로 불러오기. R4: 앞서 뜨기 직전 목록에서 불러온 영상이어도 출처를 link로 바꾼다."""
        stored = self.get(parse_video_id(url), source="link")
        if stored.source != "link":
            self.mark_source([stored.video.video_id], "link")
            stored = StoredVideo(stored.video, "link", stored.fetched_at)
        return stored

    def source_of(self, video_id: str) -> str | None:
        stored = self.stored(video_id)
        return stored.source if stored is not None else None
