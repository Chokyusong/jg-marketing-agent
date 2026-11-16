"""통합 테스트가 함께 쓰는 값과 도우미(conftest와 테스트 파일 양쪽에서 import)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

YT = "/youtube/v3"


def make_fake_key() -> str:
    return "AIza" + "x" * 35  # 실행할 때 조립(파일에 키 모양 문자열을 남기지 않는다)


class Clock:
    """고정 시계. advance(minutes=…)로 시간을 흘린다."""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 11, 16, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: Any) -> None:
        self.now += timedelta(**kwargs)


def add_search_and_videos(mock, fixture_json) -> None:
    mock.add("GET", f"{YT}/search", json=fixture_json("youtube/search.json"))
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
