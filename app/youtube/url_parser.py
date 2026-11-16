"""유튜브 링크 → 영상 ID(11자).

받는 형태: watch?v=, youtu.be/, shorts/, embed/, live/, v/, 시간·목록 꼬리표가 붙은 주소,
주소 앞의 https:// 생략, m./music./www. 하위 주소, youtube-nocookie.com, 영상 ID만 넣은 경우.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from app.errors import AppError, ErrorKind

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_PREFIXES = ("shorts", "embed", "live", "v", "e")


def is_video_id(value: str) -> bool:
    return bool(VIDEO_ID.match(value))


def parse_video_id(text: str) -> str:
    """영상 ID를 돌려준다. 읽을 수 없으면 `AppError(INVALID_URL)`."""
    raw = (text or "").strip()
    if not raw:
        raise AppError(ErrorKind.INVALID_URL, detail="빈 입력")
    if is_video_id(raw):
        return raw

    candidate = raw if "://" in raw else "https://" + raw
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise AppError(ErrorKind.INVALID_URL, detail="주소 형식 오류") from exc
    if parts.scheme not in ("http", "https"):
        raise AppError(ErrorKind.INVALID_URL, detail="http(s) 주소가 아님")

    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    video_id: str | None = None

    if host in _SHORT_HOSTS:
        video_id = segments[0] if segments else None
    elif host in _YOUTUBE_HOSTS:
        if segments[:1] == ["watch"] or (not segments and "v" in parse_qs(parts.query)):
            values = parse_qs(parts.query).get("v") or []
            video_id = values[0] if values else None
        elif len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            video_id = segments[1]
    else:
        raise AppError(ErrorKind.INVALID_URL, detail="유튜브 주소가 아님")

    if not video_id or not is_video_id(video_id):
        raise AppError(ErrorKind.INVALID_URL, detail="영상 ID를 찾지 못함")
    return video_id


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
