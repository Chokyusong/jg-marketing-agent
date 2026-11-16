"""실제 게시 실행기(R3, 어떤 영상이든)의 주소 규칙과 화면 요소 이름(브라우저를 띄우지 않는다)."""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.browser.youtube_driver import (
    LABELS,
    SELECTORS,
    PlaywrightYouTubeDriver,
    YouTubeSelectors,
    is_watch_url_for,
    may_stay,
    missing_text,
    normalize,
)

OWN = "OWNVIDEO001"  # 이번 작업의 영상(아무 영상)


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
    # 가짜 페이지 자리를 채워 둔다(conftest가 실제 실행기를 막는 것보다 주소 거절이 먼저인지 본다)
    driver = PlaywrightYouTubeDriver(
        video_id=OWN, headless=True, window_position=(60, -1060), prepare_context=lambda ctx: None
    )
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


def test_selectors_live_in_one_place_with_a_label_each():
    names = {f.name for f in fields(YouTubeSelectors)}
    assert set(LABELS) == names
    for name in names:
        css = getattr(SELECTORS, name)
        # 화면 글자(한국어)로 찾지 않는다 — 언어와 상관없는 요소 이름만
        assert css and not any("\uac00" <= ch <= "\ud7a3" for ch in css), name


def test_missing_text_names_the_element_and_its_selector():
    text = missing_text("placeholder")
    assert text.startswith("유튜브 화면에서 찾지 못한 요소: 댓글 입력 자리")
    assert "#simplebox-placeholder" in text and "화면 캡처" in text
    custom = YouTubeSelectors(submit="#my-submit")
    assert "#my-submit" in missing_text("submit", custom)
