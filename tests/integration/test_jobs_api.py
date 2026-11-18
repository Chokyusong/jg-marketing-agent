"""게시 작업 API와 테스트 페이지(8단계 · R3) — 가짜 YouTube·가짜 LLM·가짜 실행기.

크롬·Playwright·실제 유튜브를 띄우지 않는다(연습 페이지 실행기와 실제 유튜브 실행기 모두 가짜).
여기서는 API 모양, 규칙, 기록, 화면 갱신에 쓰는 값을 본다.

기본은 설정 그대로(게시 직전 확인 끔 → [댓글 달기] 한 번으로 끝까지). 입력 뒤 [게시]를 기다리는
흐름은 `setup_overrides`로 `posting.confirm_before_post`를 켜서 본다.
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
from app.browser.screens import Monitor
from app.errors import AppError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
# 대표 PC처럼 위쪽에 2번 모니터가 있는 배치(이 PC의 실제 모니터에 따라 결과가 바뀌지 않게 고정)
UPPER_AND_MAIN = [Monitor(0, -1080, 1920, 0), Monitor(0, 0, 1920, 1080, primary=True)]


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


CONFIRM_ON = {"posting": {"confirm_before_post": True}}


@pytest.fixture
def setup_overrides() -> dict:
    return {}


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, tmp_path, setup_overrides):
    drivers: list[FakeDriver] = []
    launched: list[list[str]] = []
    options = {"fail_on": "", "screens": UPPER_AND_MAIN, "youtube": [], "settings": []}
    chrome_exe = tmp_path / "chrome.exe"
    chrome_exe.write_bytes(b"")

    def factory(settings):
        options["settings"].append(settings)
        d = FakeDriver(options["fail_on"])
        drivers.append(d)
        return d

    def youtube_factory(settings, video_id):  # 실제 유튜브 실행기 대신(실제 유튜브에 가지 않는다)
        options["youtube"].append(video_id)
        return factory(settings)

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
        youtube_driver_factory=youtube_factory,
        launcher=Proc,
        playwright_ready=lambda: True,
        screens=lambda: options["screens"],
    )
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    client = make_client(mock, key=fake_key, browser_hooks=hooks, overrides=setup_overrides)
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
    assert job["target"] == "sandbox" and job["target_label"] == "연습"
    assert job["profile"] == "유튜브1" and job["folder"] == "profile-1"
    assert job["comment_text"] == d["body"]
    assert job["confirm_before_post"] is False and job["disclosed"] is True
    job = wait_state(client, job["id"], "posted")  # [댓글 달기] 한 번으로 끝까지(기다리지 않는다)
    assert "awaiting_approval" not in [e["state"] for e in job["events"]]
    assert drivers[0].calls == ["open", "type", "click", "verify", "close"]
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


@pytest.mark.parametrize("setup_overrides", [CONFIRM_ON])
def test_confirm_before_post_waits_for_post_button(setup):
    client, services, approve_one, drivers, _, _ = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    assert job["confirm_before_post"] is True
    job = wait_state(client, job["id"], "awaiting_approval")
    assert job["waiting_for"] == "approve" and job["step"] == 3
    assert job["state_label"] == "게시 대기"
    time.sleep(0.2)
    assert "click" not in drivers[0].calls
    approved = client.post(f"/api/jobs/{job['id']}/approve")
    assert approved.status_code == 200
    job = wait_state(client, job["id"], "posted")
    assert job["state"] == "posted" and drivers[0].calls[-2:] == ["verify", "close"]


@pytest.mark.parametrize("setup_overrides", [CONFIRM_ON])
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
    job = wait_state(client, job["id"], "failed")
    assert job["state"] == "failed" and "게시 단추" in job["reason"]
    assert job["has_screenshot"] and job["screenshot_url"] == f"/api/jobs/{job['id']}/screenshot"
    shot = client.get(job["screenshot_url"])
    assert shot.status_code == 200 and shot.headers["content-type"] == "image/png"
    assert shot.content.startswith(b"\x89PNG")
    records = client.get("/api/records").json()["items"]
    assert records[0]["status_label"] == "게시 실패" and records[0]["has_screenshot"] is True
    assert "error_screenshots" not in str(job)  # 캡처 경로(PC 경로)는 싣지 않는다


def test_screenshot_of_past_job_is_found_in_capture_folder(setup):
    # 9단계 전체 기록: 앱을 다시 켜서 메모리에 없는 지난 실패 작업도 캡처를 연다
    client, services, *_ = setup
    folder = Path(services.jobs.browser.screenshot_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "20261117-010101-abcdef.png").write_bytes(PNG)
    shot = client.get("/api/jobs/20261117-010101-abcdef/screenshot")
    assert shot.status_code == 200 and shot.content == PNG
    missing = client.get("/api/jobs/20261117-010101-000000/screenshot")
    assert missing.status_code == 404 and missing.json()["error"]["kind"] == "screenshot_not_found"
    odd = client.get("/api/jobs/bad.id/screenshot")  # 작업 ID 모양이 아니면 폴더를 보지 않는다
    assert odd.status_code == 404 and odd.json()["error"]["kind"] == "job_not_found"


@pytest.mark.parametrize("setup_overrides", [CONFIRM_ON])
def test_wrong_state_unknown_job_and_missing_screenshot(setup):
    client, services, approve_one, *_ = setup
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/approve").json()["error"]["kind"] == "job_not_found"
    d = approve_one()
    job = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"]}).json()
    wait_state(client, job["id"], "awaiting_approval")
    # 옛 「게시했어요」 API는 남아 있지만 R3부터 받을 작업이 없어 늘 거절한다
    confirm = client.post(f"/api/jobs/{job['id']}/confirm", json={"posted": True})
    assert confirm.status_code == 409 and confirm.json()["error"]["kind"] == "job_wrong_state"
    assert client.get(f"/api/jobs/{job['id']}/screenshot").status_code == 404
    cancel = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancel.status_code == 200
    job = wait_state(client, job["id"], "failed")
    assert job["reason"] == "사용자가 게시를 그만뒀습니다"


def test_real_posting_over_the_api_for_any_video(setup):
    """R3: 내 채널 영상 목록 없이 어떤 영상이든 실제 게시(가짜 실행기 — 실제 유튜브에 안 감)."""
    client, services, approve_one, drivers, launched, options = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    assert job["mode"] == "youtube" and job["target"] == "youtube"
    job = wait_state(client, job["id"], "posted")
    assert job["state"] == "posted" and job["verified"] is True
    assert options["youtube"] == [VID] and launched == []  # 그 영상 하나만, 크롬을 따로 안 연다
    assert drivers[0].opened == [f"https://www.youtube.com/watch?v={VID}"]
    assert job["view_url"] == f"https://www.youtube.com/watch?v={VID}"  # [댓글 보기]
    labels = [e["message"] for e in job["events"]]
    assert any("유튜브 영상으로 가는 중" in m for m in labels)
    rec = client.get("/api/records").json()["items"][0]
    assert rec["status_label"] == "게시 완료" and rec["target"] == "youtube"
    assert rec["disclosed"] is True
    item = client.get(f"/api/videos/{VID}").json()
    assert item["item"]["commented"]["youtube"] is True


@pytest.mark.parametrize("name", ["assist", "youtube_auto"])
def test_old_target_names_are_real_posting(setup, name):
    client, services, approve_one, drivers, launched, options = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": name}
    ).json()
    assert job["mode"] == "youtube" and job["target"] == "youtube"
    assert wait_state(client, job["id"], "posted")["state"] == "posted"
    assert options["youtube"] == [VID] and launched == []


def _comments_disabled(services) -> None:
    from app import db

    with db.session(services.settings.db_path) as conn:
        cur = conn.execute(
            "UPDATE video_context SET comments_disabled = 1 WHERE video_id = ?", (VID,)
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO video_context(video_id, comments_disabled) VALUES (?, 1)", (VID,)
            )


def test_real_posting_refused_for_comments_disabled_video(setup):
    client, services, approve_one, drivers, *_ = setup
    d = approve_one()
    _comments_disabled(services)
    res = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"})
    assert res.status_code == 409 and res.json()["error"]["kind"] == "comments_disabled"
    assert res.json()["error"]["action"]  # 무엇을 하면 되는지
    assert drivers == []
    # 연습 모드는 막지 않는다
    ok = client.post("/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "sandbox"})
    assert ok.status_code == 200
    wait_state(client, ok.json()["id"], "posted")


def test_real_posting_refused_for_signed_out_profile(setup, clock):
    client, services, approve_one, drivers, *_ = setup
    d = approve_one()
    from app import db

    with db.session(services.settings.db_path) as conn:
        conn.execute(
            "INSERT INTO profile_logins(profile, state, channel, checked_at, note) "
            "VALUES ('유튜브1', 'signed_out', '', ?, '')",
            (clock().isoformat(),),
        )
    res = client.post(
        "/api/jobs",
        json={"video_id": VID, "draft_id": d["id"], "target": "youtube", "profile": "유튜브1"},
    )
    err = res.json()["error"]
    assert res.status_code == 409 and err["kind"] == "profile_not_signed_in"
    assert "로그인돼 있지 않아" in err["message"] and "[로그인하기]" in err["action"]
    assert drivers == []


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
    assert "연습 페이지 — 실제 유튜브가 아닙니다" in page  # 옛 「통제된 테스트 페이지」
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


# 2026-11-17: 기본 좌표가 없어져(자동) 옛 좌표를 설정에 직접 넣어 옛 방식을 본다
LEGACY = {"browser": {"headless": False, "window_position": "60,-1060"}}


@pytest.mark.parametrize("setup_overrides", [LEGACY])
def test_window_moves_to_main_monitor_when_position_is_off_screen(setup):
    """9단계: 모니터가 하나인 PC(심사자 PC)에서는 60,-1060이 화면 밖 → 주 모니터 60,60으로."""
    client, services, approve_one, drivers, launched, options = setup
    options["screens"] = [Monitor(0, 0, 1920, 1080, primary=True)]
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    job = wait_state(client, job["id"], "posted")
    (settings,) = options["settings"]
    assert settings.window_position == (60, 60)
    notes = [e["message"] for e in job["events"] if "화면 밖" in e["message"]]
    assert notes == ["크롬 창 위치(60,-1060)가 화면 밖이라 주 모니터(60,60)에 띄웁니다"]


@pytest.mark.parametrize("setup_overrides", [LEGACY])
def test_window_stays_on_upper_monitor_when_it_exists(setup):
    client, services, approve_one, drivers, launched, options = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    job = wait_state(client, job["id"], "posted")
    assert options["settings"][0].window_position == (60, -1060)
    assert not any("화면 밖" in e["message"] for e in job["events"])


@pytest.mark.parametrize("setup_overrides", [{"browser": {"headless": False}}])
def test_window_auto_picks_the_monitor_without_the_app(setup):
    """2026-11-17 창 위치 자동: 기본(좌표 없음)이면 작업마다 모니터를 읽어 위쪽 모니터 가운데."""
    client, services, approve_one, drivers, launched, options = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    wait_state(client, job["id"], "posted")
    (settings,) = options["settings"]
    assert settings.window_position == (320, -990) and settings.window_size == (1280, 900)
    assert settings.window_target is not None


@pytest.mark.parametrize(
    "setup_overrides", [{"browser": {"headless": False, "window_screen": "-1920_0_1920_1080"}}])
def test_missing_chosen_monitor_falls_back_with_one_line(setup):
    client, services, approve_one, drivers, launched, options = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "youtube"}
    ).json()
    job = wait_state(client, job["id"], "posted")
    notes = [e["message"] for e in job["events"] if "연결돼 있지 않아" in e["message"]]
    assert notes == ["크롬 창: 고른 모니터가 지금 연결돼 있지 않아 자동으로 고른 화면에 띄웁니다"]
    assert options["settings"][0].window_position == (320, -990)


KEEP_WINDOW = {"posting": {"keep_window_seconds": 60}}

# ---------------------------------------------------------------- 게시 뒤 크롬 창(2026-11-18)


class LingerApiDriver(FakeDriver):
    def show_comment(self, text):
        self.calls.append("show")
        return True

    def wait_closed(self, seconds):
        time.sleep(seconds)
        return False


@pytest.mark.parametrize("setup_overrides", [KEEP_WINDOW])
def test_job_reports_posted_at_once_with_window_open(setup, monkeypatch):
    client, services, approve_one, drivers, _, _ = setup
    monkeypatch.setitem(globals(), "FakeDriver", LingerApiDriver)
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "sandbox"}
    ).json()
    job = wait_state(client, job["id"], "posted")
    assert job["state"] == "posted" and job["finished"] and job["verified"] is True
    assert job["window_open"] is True
    assert drivers[0].calls == ["open", "type", "click", "verify", "show"]
    assert services.jobs.active_id() is None  # 화면은 바쁘지 않다(다음 [댓글 달기]를 받는다)
    assert services.jobs.busy() is False
    assert services.jobs.release_window() is True
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["window_open"] is False and drivers[0].calls[-1] == "close"


def test_job_api_says_window_closed_by_default(setup):
    client, _, approve_one, drivers, _, _ = setup
    d = approve_one()
    job = client.post(
        "/api/jobs", json={"video_id": VID, "draft_id": d["id"], "target": "sandbox"}
    ).json()
    job = wait_state(client, job["id"], "posted")
    assert job["window_open"] is False and drivers[0].calls[-1] == "close"


def test_job_service_refuses_to_start_while_the_window_will_not_close(setup, monkeypatch):
    client, services, approve_one, _, _, _ = setup
    d = approve_one()
    monkeypatch.setattr(services.jobs, "release_window", lambda timeout=0: False)
    with pytest.raises(AppError) as err:
        services.jobs.start(VID, d["id"], None, "sandbox", base_url="http://127.0.0.1:80")
    assert err.value.kind == "job_busy"
