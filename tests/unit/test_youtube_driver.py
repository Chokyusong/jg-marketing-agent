"""내 채널 영상 자동 게시 실행기의 주소 규칙(브라우저를 띄우지 않는다)."""

from __future__ import annotations

import pytest

from app.browser.youtube_driver import (
    SELECTORS,
    PlaywrightYouTubeDriver,
    is_watch_url_for,
    may_stay,
    normalize,
)

OWN = "OWNVIDEO001"


def test_watch_url_must_be_that_exact_video():
    assert is_watch_url_for(f"https://www.youtube.com/watch?v={OWN}", OWN)
    assert is_watch_url_for(f"https://www.youtube.com/watch?v={OWN}&t=30s", OWN)
    for bad in (
        "https://www.youtube.com/watch?v=OTHERVID001",
        f"http://www.youtube.com/watch?v={OWN}",
        f"https://m.youtube.com/watch?v={OWN}",
        f"https://www.youtube.com/shorts/{OWN}",
        f"https://evil.example/watch?v={OWN}",
        f"https://www.youtube.com.evil.example/watch?v={OWN}",
        f"https://www.youtube.com/watch?v={OWN}&v=OTHERVID001",
        "not a url",
    ):
        assert not is_watch_url_for(bad, OWN), bad
    assert not is_watch_url_for("https://www.youtube.com/watch?v=bad", "bad")


def test_page_may_stay_only_on_that_video_or_consent_and_sign_in():
    assert may_stay(f"https://www.youtube.com/watch?v={OWN}", OWN)
    assert may_stay("https://consent.youtube.com/m?x=1", OWN)
    assert may_stay("https://accounts.google.com/ServiceLogin", OWN)
    assert may_stay("about:blank", OWN)
    assert not may_stay("https://www.youtube.com/watch?v=OTHERVID001", OWN)
    assert not may_stay("https://www.youtube.com/", OWN)
    assert not may_stay("https://example.com/", OWN)


def test_driver_refuses_other_addresses_before_launching(tmp_path):
    driver = PlaywrightYouTubeDriver(video_id=OWN, headless=True, window_position=(60, -1060))
    for url in ("https://www.youtube.com/watch?v=OTHERVID001", "http://127.0.0.1:8765/sandbox/watch"):
        with pytest.raises(ValueError):
            driver.open(tmp_path / "profile", url)
    assert driver._pw is None and driver._ctx is None  # 크롬을 열지 않았다
    assert not (tmp_path / "profile").exists()


def test_driver_needs_a_video_id():
    with pytest.raises(ValueError):
        PlaywrightYouTubeDriver(video_id="nope", headless=True, window_position=(0, 0))


def test_normalize_and_selectors():
    assert normalize("  가  나\n다 ") == "가 나 다"
    assert SELECTORS.submit.startswith("ytd-commentbox")
