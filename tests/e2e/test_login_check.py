"""R2 로그인 확인(`app/browser/login.check_login`)을 가짜 유튜브 페이지로 돌린다.

창 없는(headless) 설치된 크롬, 임시 프로필 폴더. `https://www.youtube.com/` 요청은 가짜 페이지
(`tests/fixtures/fake_youtube_watch.html`과 같은 요소 이름)로 바꾸고, 계정 이름 주소는 가짜 응답,
그 밖의 요청은 모두 막는다. 실제 유튜브에 접속하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.browser import login as login_mod
from app.browser.youtube_driver import SELECTORS

pytestmark = pytest.mark.e2e

PAGE = (Path(__file__).resolve().parents[1] / "fixtures" / "fake_youtube_watch.html").read_text(
    encoding="utf-8"
)
ACCOUNT = ")]}'\n" + json.dumps({"data": {"actions": [{"getMultiPageMenuAction": {"menu": {
    "multiPageMenuRenderer": {"sections": [{"accountSectionListRenderer": {"contents": [
        {"accountItemSectionRenderer": {"contents": [{"accountItem": {
            "accountName": {"simpleText": "가짜 \"채널\" 이름"}}}]}}]}}]}}}}]}}, ensure_ascii=False)


def fake_youtube(mode: str, seen: list[str], *, account: bool = True):
    def prepare(ctx) -> None:
        def handle(route) -> None:
            url = route.request.url
            seen.append(url)
            if url == "https://www.youtube.com/":
                html = PAGE.replace("__MODE__", mode)
                if mode == "blank":
                    html = "<!doctype html><title>빈 화면</title><p>아무것도 없음</p>"
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            elif account and url.startswith("https://www.youtube.com" + SELECTORS.account_endpoint):
                route.fulfill(status=200, content_type="application/json", body=ACCOUNT)
            else:
                route.abort()

        ctx.route("**/*", handle)

    return prepare


def test_signed_in_reads_channel_name(tmp_path):
    seen: list[str] = []
    result = login_mod.check_login(tmp_path / "profile-1", prepare_context=fake_youtube(
        "signed_in", seen))
    assert result.state == "signed_in" and result.channel == '가짜 "채널" 이름'
    assert seen[0] == "https://www.youtube.com/"


def test_signed_in_without_name(tmp_path):
    result = login_mod.check_login(
        tmp_path / "profile-1", prepare_context=fake_youtube("signed_in", [], account=False)
    )
    assert result.state == "signed_in" and result.channel == ""


def test_signed_out(tmp_path):
    result = login_mod.check_login(tmp_path / "profile-1", prepare_context=fake_youtube(
        "signed_out", []))
    assert result.state == "signed_out" and result.channel == ""


def test_unknown_when_neither_mark_is_found(tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "SIGN_WAIT_MS", 1500)
    result = login_mod.check_login(tmp_path / "profile-1", prepare_context=fake_youtube(
        "blank", []))
    assert result.state == "unknown" and "로그인 표시" in result.note
