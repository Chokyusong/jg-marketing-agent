"""8단계 e2e: 창 없는 크롬(설치된 Google Chrome, Playwright)으로 테스트 페이지 전 과정.

- 성공: 프로필 실행 → 한 글자씩 입력 → 승인 대기(승인 전에는 댓글이 달리지 않음)
  → 게시 → 확인 → 게시 완료.
  입력된 글이 초안과 같고, 입력 이벤트 수가 글자 수와 같다(한 글자씩 입력).
- 같은 영상 두 번째 시작은 거절(이미 댓글 단 영상), 하루 상한.
- `fail=hide_button`: 실패 사유와 화면 캡처 파일. `fail=reject`: 페이지가 저장을 거절한 사유.
- 같은 프로필 폴더를 다른 크롬이 쓰고 있으면 "그 프로필의 크롬 창을 닫아 주세요".
- 크롬이 간 주소는 이 서버의 `/sandbox/`뿐.
"""

from __future__ import annotations

import time

import pytest

from app.browser.chrome import profile_in_use

pytestmark = pytest.mark.e2e


def wait_job(app, job_id: str, state: str, timeout: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout
    job: dict = {}
    while time.monotonic() < deadline:
        job = app.http.get(f"/api/jobs/{job_id}").json()
        if job["state"] == state or job["finished"]:
            return job
        time.sleep(0.1)
    return job


def comments(app, video_id: str) -> list[dict]:
    return app.http.get(f"/sandbox/api/comments?v={video_id}").json()["items"]


def start(app, video_id: str, draft_id: int, **extra):
    return app.http.post(
        "/api/jobs", json={"video_id": video_id, "draft_id": draft_id, "target": "sandbox", **extra}
    )


def assert_only_sandbox_visited(app) -> None:
    for driver in app.drivers:
        assert driver.visited, "크롬이 아무 데도 가지 않았다"
        for url in driver.visited:
            assert url.startswith(f"{app.base}/sandbox/"), url
        assert not any("youtube" in u for u in driver.blocked)


def test_full_sandbox_flow_types_letter_by_letter_and_waits_for_approval(live_app):
    app = live_app
    vid = "E2EVIDEO001"
    draft_id, body = app.add_approved_draft(vid)
    res = start(app, vid, draft_id)
    assert res.status_code == 200, res.text
    job = wait_job(app, res.json()["id"], "awaiting_approval")
    assert job["state"] == "awaiting_approval", job
    # 승인 전에는 댓글이 달리지 않는다(잠깐 기다려도)
    time.sleep(1.0)
    assert comments(app, vid) == []
    assert app.http.get(f"/api/jobs/{job['id']}").json()["state"] == "awaiting_approval"
    assert app.http.post(f"/api/jobs/{job['id']}/approve").status_code == 200
    job = wait_job(app, job["id"], "posted")
    assert job["state"] == "posted", job
    assert job["verified"] is True
    states = [e["state"] for e in job["events"]]
    for s in ("launching", "typing", "awaiting_approval", "posting", "verifying", "posted"):
        assert s in states
    (saved,) = comments(app, vid)
    assert saved["body"] == body  # 입력된 글이 승인한 초안과 같다
    assert saved["input_events"] == len(body)  # 글자마다 입력 이벤트 하나(한 글자씩)
    assert saved["profile"] == "유튜브1"
    assert_only_sandbox_visited(app)
    # 기록과 통계
    rec = app.http.get("/api/records").json()["items"][0]
    assert rec["action"] == "post" and rec["status_label"] == "게시 완료"
    assert app.http.get("/api/stats/today?target=sandbox").json()["posted"] == 1
    # 크롬이 닫혀 프로필 폴더 잠금이 풀렸다
    assert profile_in_use(app.profiles_root / "profile-1") is False

    # 같은 영상 두 번째 시작은 거절(다른 프로필이어도)
    again = start(app, vid, draft_id, profile="유튜브2")
    assert again.status_code == 409 and again.json()["error"]["kind"] == "already_commented"
    # 하루 상한(화면에서 1건으로 낮춤): 오늘 1건을 이미 달아 다른 영상도 거절
    other_id, _ = app.add_approved_draft("E2EVIDEO002")
    limited = start(app, "E2EVIDEO002", other_id, daily_limit=1)
    assert limited.status_code == 429 and limited.json()["error"]["kind"] == "daily_limit_reached"
    assert len(app.drivers) == 1  # 거절된 시작은 크롬을 열지 않는다


def test_hide_button_fails_with_reason_and_screenshot(live_app):
    app = live_app
    vid = "E2EVIDEO003"
    draft_id, _ = app.add_approved_draft(vid)
    job = start(app, vid, draft_id, fail="hide_button").json()
    job = wait_job(app, job["id"], "awaiting_approval")
    app.http.post(f"/api/jobs/{job['id']}/approve")
    job = wait_job(app, job["id"], "failed")
    assert job["state"] == "failed", job
    assert "게시 단추" in job["reason"]
    assert job["has_screenshot"] is True
    shot = app.shots / f"{job['id']}.png"
    assert shot.is_file() and shot.stat().st_size > 1000
    png = app.http.get(job["screenshot_url"])
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    assert comments(app, vid) == []
    rec = app.http.get("/api/records").json()["items"][0]
    assert rec["status_label"] == "게시 실패" and rec["has_screenshot"] is True
    # 실패는 다시 시도할 수 있다(같은 영상, 이번엔 정상)
    again = start(app, vid, draft_id)
    assert again.status_code == 200, again.text
    retry = wait_job(app, again.json()["id"], "awaiting_approval")
    app.http.post(f"/api/jobs/{retry['id']}/approve")
    assert wait_job(app, retry["id"], "posted")["state"] == "posted"
    assert_only_sandbox_visited(app)


def test_reject_switch_reports_page_reason(live_app):
    app = live_app
    vid = "E2EVIDEO004"
    draft_id, _ = app.add_approved_draft(vid)
    job = start(app, vid, draft_id, fail="reject").json()
    wait_job(app, job["id"], "awaiting_approval")
    app.http.post(f"/api/jobs/{job['id']}/approve")
    job = wait_job(app, job["id"], "failed")
    assert job["state"] == "failed" and "거절" in job["reason"], job
    assert job["has_screenshot"] is True


def test_profile_in_use_asks_to_close_that_chrome(live_app):
    from playwright.sync_api import sync_playwright

    app = live_app
    vid = "E2EVIDEO005"
    draft_id, _ = app.add_approved_draft(vid)
    folder = app.profiles_root / "profile-2"
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        other = p.chromium.launch_persistent_context(str(folder), channel="chrome", headless=True)
        try:
            assert profile_in_use(folder) is True
            res = start(app, vid, draft_id, profile="유튜브2")
            assert res.status_code == 409
            error = res.json()["error"]
            assert error["kind"] == "profile_in_use"
            assert "그 프로필의 크롬 창을 닫아 주세요" in error["action"]
        finally:
            other.close()
    assert profile_in_use(folder) is False
    assert app.http.get("/api/records").json()["items"] == []  # 거절은 예약·기록을 남기지 않는다
