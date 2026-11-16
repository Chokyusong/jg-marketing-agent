"""YouTube Data API v3 호출(httpx) — 검색, 영상 상세, 인기 댓글.

- 키는 요청 주소의 `key=`로 보낸다(공식 방식). 그래서 httpx 로그에 주소가 찍힐 때
  `key=` 값을 가리는 필터를 붙여 둔다. 오류 문구에도 키를 넣지 않는다.
- 응답을 받은 호출마다 할당량 단위를 `on_units`로 알린다(quota.py가 DB에 적는다).
- 오류는 `AppError` 6종(키 없음·키 거부·할당량 초과·댓글 막힘·영상 없음·네트워크)과
  그 밖의 `youtube_error`로 나눈다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.errors import AppError, ErrorKind, redact

BASE_URL = "https://www.googleapis.com/youtube/v3"
UNIT_COSTS = {"search": 100, "videos": 1, "commentThreads": 1}

log = logging.getLogger("app.youtube")


class _RedactKeyFilter(logging.Filter):
    """httpx가 남기는 "HTTP Request: GET https://...?key=..." 줄에서 키를 가린다."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, ()
        return True


def install_log_redaction() -> None:
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _RedactKeyFilter) for f in logger.filters):
            logger.addFilter(_RedactKeyFilter())


install_log_redaction()


# ---------------------------------------------------------------- 결과 모양


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    description: str
    published_at: str
    thumbnail_url: str
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None


@dataclass(frozen=True)
class Comment:
    text: str
    like_count: int
    published_at: str


_DURATION = re.compile(
    r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$"
)


def parse_duration(value: str | None) -> int | None:
    """ISO 8601 길이(PT1H2M3S) → 초. 생방송 등 길이가 없으면 None."""
    if not value:
        return None
    match = _DURATION.match(value)
    if not match:
        return None
    d, h, m, s = (int(match.group(k) or 0) for k in "dhms")
    total = ((d * 24 + h) * 60 + m) * 60 + s
    return total or None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _best_thumbnail(thumbnails: dict[str, Any]) -> str:
    for size in ("medium", "high", "standard", "default", "maxres"):
        url = (thumbnails.get(size) or {}).get("url")
        if url:
            return url
    return ""


def video_from_item(item: dict[str, Any]) -> Video:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    details = item.get("contentDetails") or {}
    return Video(
        video_id=item["id"],
        title=snippet.get("title", ""),
        channel_id=snippet.get("channelId", ""),
        channel_title=snippet.get("channelTitle", ""),
        description=snippet.get("description", ""),
        published_at=snippet.get("publishedAt", ""),
        thumbnail_url=_best_thumbnail(snippet.get("thumbnails") or {}),
        duration_seconds=parse_duration(details.get("duration")),
        view_count=_int_or_none(stats.get("viewCount")),
        like_count=_int_or_none(stats.get("likeCount")),
        comment_count=_int_or_none(stats.get("commentCount")),
    )


def comment_from_item(item: dict[str, Any]) -> Comment:
    top = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
    # 작성자 이름·채널은 쓰지 않는다(개인정보를 남기지 않는다).
    return Comment(
        text=top.get("textOriginal") or top.get("textDisplay") or "",
        like_count=_int_or_none(top.get("likeCount")) or 0,
        published_at=top.get("publishedAt", ""),
    )


# ---------------------------------------------------------------- 오류 분류

_QUOTA_REASONS = {
    "quotaExceeded",
    "dailyLimitExceeded",
    "dailyLimitExceededUnreg",
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "RATE_LIMIT_EXCEEDED",
}
_KEY_REASONS = {
    "keyInvalid",
    "keyExpired",
    "badRequest_keyInvalid",
    "accessNotConfigured",
    "ipRefererBlocked",
    "API_KEY_INVALID",
    "API_KEY_EXPIRED",
    "API_KEY_SERVICE_BLOCKED",
    "API_KEY_HTTP_REFERRER_BLOCKED",
    "API_KEY_IP_ADDRESS_BLOCKED",
    "SERVICE_DISABLED",
}
_NOT_FOUND_REASONS = {"videoNotFound", "notFound"}


def _error_reasons(body: Any) -> tuple[list[str], str]:
    if not isinstance(body, dict):
        return [], ""
    error = body.get("error") or {}
    if not isinstance(error, dict):
        return [], str(error)
    reasons = [e.get("reason", "") for e in error.get("errors") or [] if isinstance(e, dict)]
    reasons += [d.get("reason", "") for d in error.get("details") or [] if isinstance(d, dict)]
    if error.get("status"):
        reasons.append(str(error["status"]))
    return [r for r in reasons if r], str(error.get("message", ""))


def classify_error(status_code: int, body: Any) -> ErrorKind:
    reasons, message = _error_reasons(body)
    found = set(reasons)
    if found & _QUOTA_REASONS:
        return ErrorKind.QUOTA_EXCEEDED
    if "commentsDisabled" in found:
        return ErrorKind.COMMENTS_DISABLED
    if found & _NOT_FOUND_REASONS or status_code == 404:
        return ErrorKind.VIDEO_NOT_FOUND
    if found & _KEY_REASONS or (status_code in (400, 403) and "api key" in message.lower()):
        return ErrorKind.KEY_REJECTED
    return ErrorKind.YOUTUBE_ERROR


# ---------------------------------------------------------------- 클라이언트


class YouTubeClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        on_units: Callable[[int], None] | None = None,
    ) -> None:
        self._api_key = api_key or None
        self._on_units = on_units
        self._http = httpx.Client(base_url=BASE_URL, transport=transport, timeout=timeout)

    def __repr__(self) -> str:  # 키를 보이지 않는다
        return f"YouTubeClient(key_configured={self._api_key is not None})"

    def close(self) -> None:
        self._http.close()

    # -- 공통 호출

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise AppError(ErrorKind.MISSING_KEY)
        secrets = [self._api_key]
        query = {k: v for k, v in params.items() if v is not None}
        query["key"] = self._api_key
        try:
            response = self._http.get(f"/{endpoint}", params=query)
        except httpx.TimeoutException:
            raise AppError(ErrorKind.NETWORK, detail="응답 시간 초과") from None
        except httpx.TransportError as exc:
            detail = redact(f"{type(exc).__name__}: {exc}", secrets)
            raise AppError(ErrorKind.NETWORK, detail=detail) from None

        if self._on_units is not None:
            self._on_units(UNIT_COSTS.get(endpoint, 1))
        log.info("YouTube %s 호출: HTTP %s", endpoint, response.status_code)

        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code >= 400:
            kind = classify_error(response.status_code, body)
            reasons, message = _error_reasons(body)
            detail = redact(
                f"HTTP {response.status_code} {','.join(reasons)} {message}".strip(), secrets
            )
            log.warning("YouTube %s 오류: %s (%s)", endpoint, kind, detail)
            raise AppError(kind, detail=detail) from None
        if not isinstance(body, dict):
            raise AppError(ErrorKind.YOUTUBE_ERROR, detail="응답이 JSON이 아님") from None
        return body

    # -- 기능

    def search_video_ids(
        self,
        query: str,
        *,
        max_results: int,
        order: str = "date",
        published_after: datetime | None = None,
    ) -> list[str]:
        """최신 영상 검색(100단위). 영상 ID만 돌려준다 — 상세는 get_videos로."""
        after = None
        if published_after is not None:
            after = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = self._get(
            "search",
            {
                "part": "id",
                "q": query,
                "type": "video",
                "order": order,
                "maxResults": max(1, min(int(max_results), 50)),
                "regionCode": "KR",
                "relevanceLanguage": "ko",
                "publishedAfter": after,
            },
        )
        ids: list[str] = []
        for item in body.get("items") or []:
            video_id = (item.get("id") or {}).get("videoId")
            if video_id and video_id not in ids:
                ids.append(video_id)
        return ids

    def get_videos(self, video_ids: Iterable[str]) -> list[Video]:
        """영상 상세·조회수(50개당 1단위). 입력 순서를 지키고 없는 영상은 뺀다."""
        ids = list(dict.fromkeys(video_ids))
        found: dict[str, Video] = {}
        for start in range(0, len(ids), 50):
            chunk = ids[start : start + 50]
            body = self._get(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(chunk),
                    "maxResults": len(chunk),
                },
            )
            for item in body.get("items") or []:
                video = video_from_item(item)
                found[video.video_id] = video
        return [found[i] for i in ids if i in found]

    def get_video(self, video_id: str) -> Video:
        videos = self.get_videos([video_id])
        if not videos:
            raise AppError(ErrorKind.VIDEO_NOT_FOUND, detail="videos.list 결과 없음")
        return videos[0]

    def get_top_comments(self, video_id: str, *, max_results: int = 20) -> list[Comment]:
        """인기 댓글(order=relevance, 1단위). 댓글이 막혔으면 COMMENTS_DISABLED."""
        body = self._get(
            "commentThreads",
            {
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "maxResults": max(1, min(int(max_results), 100)),
                "textFormat": "plainText",
            },
        )
        return [comment_from_item(item) for item in body.get("items") or []]

    def search_comments(
        self, video_id: str, search_terms: str, *, max_results: int = 20
    ) -> list[Comment]:
        """그 영상의 최근 댓글 중 글이 들어간 것(order=time, searchTerms, 1단위).

        8단계 assist에서 사람이 [게시했어요]를 눌렀을 때 정말 달렸는지 찾아보는 데만 쓴다
        (읽기 전용).
        """
        body = self._get(
            "commentThreads",
            {
                "part": "snippet",
                "videoId": video_id,
                "order": "time",
                "searchTerms": search_terms[:100],
                "maxResults": max(1, min(int(max_results), 100)),
                "textFormat": "plainText",
            },
        )
        return [comment_from_item(item) for item in body.get("items") or []]
