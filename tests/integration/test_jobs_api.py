"""게시 작업 API와 테스트 페이지(8단계) — 가짜 YouTube·가짜 LLM·가짜 테스트 페이지 실행기.

크롬·Playwright를 띄우지 않는다(그건 tests/e2e).
여기서는 API 모양, 규칙, 기록, 화면 갱신에 쓰는 값을 본다.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, draft
from yt_helpers import YT, add_search_and_videos

from app.browser import sandbox as sandbox_mod
from app.browser.hooks import BrowserHooks
from app.browser.sandbox_driver import DriverError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeDriver:
    def __init__(self, fail_on: str = ""):
        self.fail_on = fail_on
        self.calls: list[str] = []
        self.opened: list[str] = []
        self.visited: list[str] = []

    def open(self, user_data_dir, url):
        self.opened.append(url)
        self.calls.append("open")

    def type_comment(self, text, delay_ms, should_stop):
        self.calls.append("type")

    def click_post(self):
        self.calls.append("click")
        if self.fail_on == "click":
            raise DriverError("게시 단추(「댓글」)를 찾지 못했거나 누르지 못했습니다.")

    def verify_posted(self, text):
        self.calls.append("verify")

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(PNG)
        return True

    def close(self):
        self.calls.append("close")


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, tmp_path):
    drivers: list[FakeDriver] = []
    launched: list[list[str]] = []
    options = {"fail_on": ""}
    chrome_exe = tmp_path / "chrome.exe"
    chrome_exe.write_bytes(b"")

    def factory(settings):
        d = FakeDriver(options["fail_on"])
        drivers.append(d)
        return d

    class Proc:
        def __init__(self, args):
            launched.append(list(args))

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    hooks = BrowserHooks(
        chrome_finder=lambda: chrome_exe,
        driver_factory=factory,
        launcher=Proc,
        playwright_ready=lambda: True,
    )
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    client = make_client(mock, key=fake_key, browser_hooks=hooks)
    services = client.app.state.services.get()

    def approve_one() -> dict:
        llm = fake_llm([ANALYSIS, draft(GOOD_BODY)])
        llm.model = "fake-model"
        services.llm = llm
        client.get("/api/videos")
        client.post(f"/api/analysis/{VID}")
        made = client.post("/api/drafts", json={"video_id": VID}).json()
        res = client.post(f"/api/drafts/{made['id']}/approve")
        assert res.status_code == 200, res.text
        return res.json()

    yield client, services, approve_one, drivers, launched, options
    services.jobs.shutdown(timeout=5)


def wait_state(client, job_id: str, state: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] == state or job["finished"]:
            return job
        time.sleep(0.02)
    return client.get(f"/api/jobs/{job_id}").json()


def test_sandbox_job_over_the_api(setup):
    client, services, approve_one, drivers, _, _ = setup
    d = approve_one()
    res = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "sandbox"})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["mode"] == "sandbox"
    assert job["target"] == "sandbox" and job["target_label"] == "테스트 페이지"
    assert job["profile"] == "유튜브1" and job["folder"] == "profile-1"
    assert job["comment_text"] == d["body"]
    job = wait_state(client, job["id"], "awaiting_approval")
    assert job["waiting_for"] == "approve" and job["step"] == 3
    assert "click" not in drivers[0].calls
    approved = client.post(f"/api/jobs/{job['id']}/approve")
    assert approved.status_code == 200
    job = wait_state(client, job["id"], "posted")
    assert job["state"] == "posted" and job["state_label"] == "게시 완료"
    assert job["verified"] is True
    assert job["view_url"].startswith(f"http://127.0.0.1:80/sandbox/watch?v={VID}")
    assert [e["state"] for e in job["events"]][0] == "queued"
    # 테스트 페이지 주소는 머리말(Host)이 아니라 이 PC의 로컬 주소로 만든다
    assert drivers[0].opened[0].startswith(f"http://127.0.0.1:80/sandbox/watch?v={VID}")
    seen = client.get(f"/api/jobs/{job['id']}", headers={"Host": "evil.test"}).json()
    assert "evil.test" not in seen["view_url"]
    # 기록·통계·01칸 표시가 바로 바뀐다
    records = client.get("/api/records").json()["items"]
    assert records[0]["action"] == "post" and records[0]["status_label"] == "게시 완료"
    assert records[0]["job_id"] == job["id"]
    stats = client.get("/api/stats/today?target=sandbox").json()
    assert stats["posted"] == 1 and stats["videos"] == 1
    item = client.get(f"/api/videos/{VID}").json()
    assert item["item"]["commented"]["sandbox"] is True


def test_second_start_on_same_video_is_refused(setup):
    client, services, approve_one, *_ = setup
    d = approve_one()
    body = {"video_id": VID, "draft_id": d["id"], "target": "sandbox"}
    job = client.post("/api/jobs", json=body).json()
    busy = client.post("/api/jobs", json=body)
    assert busy.status_code == 409 and busy.json()["error"]["kind"] == "job_busy"
    wait_state(client, job["id"], "awaiting_approval")
    client.post(f"/api/jobs/{job['id']}/approve")
    wait_state(client, job["id"], "posted")
    again = client.post("/api/jobs", json=body)
    assert again.status_code == 409 and again.json()["error"]["kind"] == "already_commented"


def test_daily_limit_from_screen_is_enforced(setup):
    client, services, approve_one, *_ = setup
    d = approve_one()
    res = client.post(
        "/api/jobs",
        json={"video_id": VID, "draft_id": d["id"], "target": "sandbox", "daily_limit": 0},
    )
    assert res.status_code == 429 and res.json()["error"]["kind"] == "daily_limit_reached"


def test_unapproved_or_unknown_draft_is_refused(setup):
    client, services, approve_one, *_ = setup
    res = client.post("/api/jobs", json={"video_id": VID, "draft_id": 999, "target": "sandbox"})
    assert res.status_code == 404 and res.json()["error"]["kind"] == "draft_not_found"
    bad = client.post("/api/jobs", json={"video_id": VID, "draft_id": 1, "target": "everywhere"})
    assert bad.status_code == 422


def test_failed_job_has_reason_and_screenshot(setup):
    client, services, approve_one, drivers, _, options = setup
    options["fail_on"] = "click"
    d = approve_one()
    job = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"]}).json()
    wait_state(client, job["id"], "awaiting_approval")
    client.post(f"/api/jobs/{job['id']}/approve")
    job = wait_state(client, job["id"], "failed")
    assert job["state"] == "failed" and "게시 단추" in job["reason"]
    assert job["has_screenshot"] and job["screenshot_url"] == f"/api/jobs/{job['id']}/screenshot"
    shot = client.get(job["screenshot_url"])
    assert shot.status_code == 200 and shot.headers["content-type"] == "image/png"
    assert shot.content.startswith(b"\x89PNG")
    records = client.get("/api/records").json()["items"]
    assert records[0]["status_label"] == "게시 실패" and records[0]["has_screenshot"] is True
    assert "error_screenshots" not in str(job)  # 캡처 경로(PC 경로)는 싣지 않는다


def test_wrong_state_unknown_job_and_missing_screenshot(setup):
    client, services, approve_one, *_ = setup
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/approve").json()["error"]["kind"] == "job_not_found"
    d = approve_one()
    job = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"]}).json()
    confirm = client.post(f"/api/jobs/{job['id']}/confirm", json={"posted": True})
    assert confirm.status_code == 409 and confirm.json()["error"]["kind"] == "job_wrong_state"
    assert client.get(f"/api/jobs/{job['id']}/screenshot").status_code == 404
    cancel = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancel.status_code == 200
    job = wait_state(client, job["id"], "failed")
    assert job["reason"] == "사용자가 작업을 취소했습니다"


def test_assist_job_over_the_api(setup):
    client, services, approve_one, drivers, launched, _ = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "assist"}
    ).json()
    assert job["mode"] == "assist" and job["target"] == "youtube"
    job = wait_state(client, job["id"], "awaiting_confirm")
    assert job["waiting_for"] == "confirm"
    assert drivers == []  # Playwright 실행기는 만들지도 않는다
    (args,) = launched
    assert args[-1] == f"https://www.youtube.com/watch?v={VID}"
    assert any(a.startswith("--user-data-dir=") and a.endswith("profile-1") for a in args)
    assert "--window-position=60,-1060" in args
    res = client.post(f"/api/jobs/{job['id']}/confirm", json={"posted": True})
    assert res.status_code == 200
    job = wait_state(client, job["id"], "posted")
    # 가짜 commentThreads 응답에 내 댓글이 없으니 「확인 못 함」으로 끝난다
    assert job["state"] == "posted" and job["verified"] is False
    assert job["view_url"] == f"https://www.youtube.com/watch?v={VID}"
    rec = client.get("/api/records").json()["items"][0]
    assert rec["status_label"] == "게시 완료" and rec["reason"] == "게시됨(확인 못 함)"
    assert rec["target"] == "youtube"


def test_status_reports_browser_without_paths(setup, tmp_path):
    client, *_ = setup
    data = client.get("/api/status").json()
    browser = data["browser"]
    assert browser["chrome_found"] is True and browser["playwright_ready"] is True
    assert [p["name"] for p in browser["profiles"]] == ["유튜브1", "유튜브2", "유튜브3"]
    assert [p["folder"] for p in browser["profiles"]] == ["profile-1", "profile-2", "profile-3"]
    assert all(p["exists"] is False for p in browser["profiles"])
    assert browser["active_job_id"] is None
    assert str(tmp_path) not in client.get("/api/status").text
    assert "youtube" in data and "ai" in data  # 기존 필드 그대로


def test_status_without_chrome(make_client):
    client = make_client(key=None, browser_hooks=BrowserHooks(chrome_finder=lambda: None))
    assert client.get("/api/status").json()["browser"]["chrome_found"] is False


# ---------------------------------------------------------------- 테스트 페이지


@pytest.fixture
def plain(make_client):
    return make_client(key=None)


def test_sandbox_page_is_our_own_marked_page(plain):
    res = plain.get(f"/sandbox/watch?v={VID}&profile=유튜브1")
    assert res.status_code == 200
    page = res.text
    assert "통제된 테스트 페이지 — 실제 유튜브가 아닙니다" in page
    assert 'placeholder="댓글 추가..."' in page
    assert ">취소</button>" in page and ">댓글</button>" in page
    assert 'id="comment-list"' in page and "영상 자리" in page
    assert f"테스트 영상 {VID}" in page  # 저장된 영상이 없으면 ID로
    assert "youtube.com" not in page and "ytimg" not in page and "https://" not in page
    assert 'name="robots" content="noindex"' in page


def test_sandbox_page_uses_stored_title(setup):
    client, services, approve_one, *_ = setup
    approve_one()
    title = services.videos.stored(VID).video.title
    assert title in client.get(f"/sandbox/watch?v={VID}").text


def test_sandbox_hide_button_switch(plain):
    page = plain.get(f"/sandbox/watch?v={VID}&fail=hide_button").text
    assert 'id="comment-submit"' not in page and 'data-fail="hide_button"' in page
    assert 'data-fail=""' in plain.get(f"/sandbox/watch?v={VID}&fail=whatever").text


def test_sandbox_page_needs_video_id(plain):
    assert plain.get("/sandbox/watch?v=bad").status_code == 422
    assert plain.get("/sandbox/api/comments?v=bad").status_code == 422


def test_sandbox_comments_round_trip(plain):
    assert plain.get(f"/sandbox/api/comments?v={VID}").json() == {"video_id": VID, "items": []}
    body = {"video_id": VID, "body": "[광고] 테스트 댓글", "profile": "유튜브1", "input_events": 11}
    res = plain.post("/sandbox/api/comments", json=body)
    assert res.status_code == 200
    saved = res.json()
    assert saved["body"] == "[광고] 테스트 댓글" and saved["input_events"] == 11
    items = plain.get(f"/sandbox/api/comments?v={VID}").json()["items"]
    assert [i["body"] for i in items] == ["[광고] 테스트 댓글"]


def test_sandbox_reject_and_slow_switches(plain, monkeypatch):
    rejected = plain.post(
        "/sandbox/api/comments", json={"video_id": VID, "body": "x", "fail": "reject"}
    )
    assert rejected.status_code == 503
    assert rejected.json()["error"]["kind"] == "sandbox_rejected"
    assert plain.get(f"/sandbox/api/comments?v={VID}").json()["items"] == []
    monkeypatch.setattr(sandbox_mod, "SLOW_SECONDS", 0.2)
    started = time.monotonic()
    slow = plain.post("/sandbox/api/comments", json={"video_id": VID, "body": "y", "fail": "slow"})
    assert slow.status_code == 200 and time.monotonic() - started >= 0.2


def test_sandbox_assets_are_local(plain):
    js = plain.get("/static/js/sandbox.js").text
    assert "/sandbox/api/comments" in js and "inputEvents" in js
    assert "innerHTML" not in js and "youtube" not in js.lower()
    css = plain.get("/static/css/sandbox.css")
    assert css.status_code == 200 and "@import" not in css.text and "http" not in css.text
