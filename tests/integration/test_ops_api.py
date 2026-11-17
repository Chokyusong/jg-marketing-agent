"""운영 규칙과 기록 API(7단계) — 가짜 YouTube, 가짜 LLM.

- `GET /api/profiles` · `GET /api/records` · `GET /api/stats/today`
- 분석·초안 생성·승인이 작업 기록(runs)에 남는다(info, 오류면 failure와 사유).
- 영상 목록·영상 항목 응답에 `commented: {sandbox, youtube}`가 붙는다(기존 필드는 그대로).
- 게시 예약·완료는 8단계 작업 서비스 몫이라 여기서는 서비스(`services.rules`)로 직접 부른다.
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, NO_BRAND, NO_BRAND_TAG, OTHER, VID, draft
from yt_helpers import YT, add_search_and_videos


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    client = make_client(mock, key=fake_key)
    services = client.app.state.services.get()

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        services.llm = llm
        return llm

    return client, services, use


def approved_draft(client, use) -> dict:
    use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{VID}")
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    res = client.post(f"/api/drafts/{made['id']}/approve")
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------- 프로필


def test_profiles_list_names_folders_and_auto(setup):
    client, services, use = setup
    data = client.get("/api/profiles").json()
    assert data["target"] == "sandbox"
    assert [(p["name"], p["folder"], p["last_used_at"]) for p in data["items"]] == [
        ("유튜브1", "profile-1", None),
        ("유튜브2", "profile-2", None),
        ("유튜브3", "profile-3", None),
    ]
    assert data["auto"] == "유튜브1"
    # 예약하면 자동 배정이 다음 프로필로(대상마다 따로)
    d = approved_draft(client, use)
    services.rules.reserve(VID, "sandbox", "유튜브1", d["id"])
    data = client.get("/api/profiles", params={"target": "sandbox"}).json()
    assert data["auto"] == "유튜브2" and data["items"][0]["last_used_at"]
    assert client.get("/api/profiles", params={"target": "youtube"}).json()["auto"] == "유튜브1"


def _set_login(services, profile: str, state: str) -> None:
    from app import db

    with db.session(services.settings.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profile_logins(profile, state, channel, checked_at, note) "
            "VALUES (?, ?, '', ?, '')",
            (profile, state, services.jobs.clock().isoformat()),
        )


def test_profiles_auto_prefers_signed_in_for_real_posting(setup):
    """2026-11-17: 유튜브1·2 로그인됨, 유튜브3 확인한 적 없음 → 실제 게시 자동 배정에 3이 없다."""
    client, services, use = setup
    d = approved_draft(client, use)
    services.rules.reserve(VID, "youtube", "유튜브1", d["id"])
    data = client.get("/api/profiles", params={"target": "youtube"}).json()
    assert data["auto"] == "유튜브2" and data["auto_confirmed"] is False  # 아직 확인한 것이 없다
    assert "로그인을 확인한 프로필이 없어" in data["auto_note"]
    _set_login(services, "유튜브1", "signed_in")
    data = client.get("/api/profiles", params={"target": "youtube"}).json()
    assert (data["auto"], data["auto_confirmed"], data["auto_note"]) == ("유튜브1", True, "")
    _set_login(services, "유튜브2", "signed_in")
    data = client.get("/api/profiles", params={"target": "youtube"}).json()
    assert data["auto"] == "유튜브2"
    # 연습 모드는 로그인이 필요 없다
    sandbox = client.get("/api/profiles", params={"target": "sandbox"}).json()
    assert sandbox["auto"] == "유튜브1" and sandbox["auto_confirmed"] is None
    # 상태 응답에도 같은 값(③칸 「자동 배정 · 이번에는 유튜브2」)
    from app.api.status import browser_status

    picks = browser_status(services).model_dump()["auto_pick"]
    assert picks["youtube"] == {"name": "유튜브2", "confirmed": True, "note": ""}
    assert picks["sandbox"]["name"] == "유튜브1" and picks["sandbox"]["confirmed"] is None


def test_profiles_reject_unknown_target(setup):
    client, _, _ = setup
    assert client.get("/api/profiles", params={"target": "assist"}).status_code == 422


def test_profiles_follow_config(make_client):
    client = make_client(overrides={"profiles": ["메인", "보조"]})
    names = [p["name"] for p in client.get("/api/profiles").json()["items"]]
    assert names == ["메인", "보조"]
    page = client.get("/").text
    assert '<option value="메인">메인</option>' in page


def test_no_full_folder_paths_in_profiles(setup):
    client, _, _ = setup
    text = client.get("/api/profiles").text
    assert "AppData" not in text and "\\\\" not in text and "JGMarketingAgent" not in text


# ---------------------------------------------------------------- 작업 기록


def test_records_empty(setup):
    client, _, _ = setup
    assert client.get("/api/records").json() == {"items": [], "total": 0}


def test_analyze_draft_approve_are_recorded_newest_first(setup, clock):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{VID}")
    clock.advance(seconds=10)
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    clock.advance(seconds=10)
    client.post(f"/api/drafts/{made['id']}/approve")
    data = client.get("/api/records").json()
    assert data["total"] == 3
    rows = data["items"]
    assert [r["action"] for r in rows] == ["approve", "draft", "analyze"]
    assert [r["action_label"] for r in rows] == ["초안 승인", "초안 생성", "AI 분석"]
    assert {r["result"] for r in rows} == {"info"}
    assert {r["status_label"] for r in rows} == {"완료"}
    approve, made_row, analyze = rows
    assert approve["comment_text"] == made["body"] and approve["reason"] == "사람이 승인"
    assert made_row["comment_text"] == made["body"]
    assert made_row["reason"] == "규칙 검사 통과 · 1번째 시도"
    assert analyze["reason"] == f"핵심 고민 · {ANALYSIS['concern']}"
    assert analyze["comment_text"] == ""
    for r in rows:
        assert r["video_id"] == VID and r["video_title"]  # 제목은 videos에서
        assert r["video_url"] == f"https://www.youtube.com/watch?v={VID}"
        assert r["profile"] == "" and r["target"] == "" and r["has_screenshot"] is False
    assert rows[0]["at"] > rows[1]["at"] > rows[2]["at"]


def test_failed_steps_are_recorded_with_reason(setup):
    client, _, use = setup
    use([ANALYSIS, draft(NO_BRAND_TAG), draft(NO_BRAND), draft(NO_BRAND)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()  # 분석도 함께 돈다
    assert client.post(f"/api/drafts/{made['id']}/approve").status_code == 409
    rows = client.get("/api/records").json()["items"]
    assert [(r["action"], r["result"]) for r in rows] == [
        ("approve", "failure"), ("draft", "info"), ("analyze", "info")
    ]
    assert rows[0]["status_label"] == "실패"
    assert rows[0]["reason"] == "규칙 검사 1개 걸림 · 승인 안 됨"
    assert rows[1]["reason"] == "규칙 검사 1개 걸림 · 3번 시도"


def test_llm_down_is_recorded_as_failure(make_client, mock_http, fixture_json, fake_key):
    mock = mock_http()
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    client = make_client(mock, key=fake_key)  # Ollama 꺼짐
    assert client.post(f"/api/analysis/{VID}").status_code == 503
    row = client.get("/api/records").json()["items"][0]
    assert (row["action"], row["result"]) == ("analyze", "failure")
    assert "Ollama" in row["reason"]


def test_records_limit(setup):
    client, services, _ = setup
    for i in range(8):
        services.ledger.record("draft", "info", reason=str(i))
    data = client.get("/api/records", params={"limit": 5}).json()
    assert len(data["items"]) == 5 and data["total"] == 8
    assert [r["reason"] for r in data["items"]] == ["7", "6", "5", "4", "3"]
    assert client.get("/api/records", params={"limit": 0}).status_code == 422
    assert client.get("/api/records", params={"limit": 201}).status_code == 422


def test_post_rows_show_result_profile_target(setup):
    client, services, use = setup
    d = approved_draft(client, use)
    post_id = services.rules.reserve(VID, "sandbox", "유튜브2", d["id"])
    services.rules.mark_failed(post_id, "게시 단추를 찾지 못했습니다",
                               screenshot_path="error_screenshots/job-1.png")
    row = client.get("/api/records").json()["items"][0]
    assert (row["action_label"], row["status_label"]) == ("댓글 게시", "게시 실패")
    assert (row["profile"], row["target"], row["target_label"]) == ("유튜브2", "sandbox",
                                                                    "테스트 페이지")
    assert row["has_screenshot"] is True
    assert "error_screenshots" not in client.get("/api/records").text  # 경로는 싣지 않는다
    services.rules.reserve(VID, "sandbox", "유튜브3", d["id"])  # 실패 뒤 다시 시도
    services.rules.mark_posted(post_id)
    row = client.get("/api/records").json()["items"][0]
    assert row["status_label"] == "게시 완료" and row["comment_text"] == d["body"]


# ---------------------------------------------------------------- 오늘 통계


def test_stats_empty_have_no_success_rate(setup):
    client, _, _ = setup
    data = client.get("/api/stats/today").json()
    assert data == {
        "target": "sandbox", "target_label": "테스트 페이지", "day": "2026-11-16",
        "videos": 0, "daily_limit": 10, "remaining": 10, "drafts": 0, "posted": 0,
        "failed": 0, "success_rate": None,
    }


def test_stats_follow_drafts_and_posts(setup):
    client, services, use = setup
    d = approved_draft(client, use)
    assert client.get("/api/stats/today").json()["drafts"] == 1  # 승인까지 하면 초안 1
    post_id = services.rules.reserve(VID, "sandbox", "유튜브1", d["id"])
    data = client.get("/api/stats/today").json()
    assert (data["videos"], data["remaining"], data["posted"]) == (1, 9, 0)
    services.rules.mark_posted(post_id)
    data = client.get("/api/stats/today").json()
    assert (data["videos"], data["posted"], data["success_rate"]) == (1, 1, 1.0)
    other = client.get("/api/stats/today", params={"target": "youtube"}).json()
    assert (other["videos"], other["posted"], other["success_rate"]) == (0, 0, None)
    assert other["target_label"] == "유튜브"


def test_stats_lowered_limit_and_bad_target(setup):
    client, _, _ = setup
    data = client.get("/api/stats/today", params={"daily_limit": 3}).json()
    assert (data["daily_limit"], data["remaining"]) == (3, 3)
    assert client.get("/api/stats/today", params={"daily_limit": 50}).json()["daily_limit"] == 10
    assert client.get("/api/stats/today", params={"target": "assist"}).status_code == 422


def test_stats_reset_after_korean_midnight(setup, clock):
    client, services, use = setup
    d = approved_draft(client, use)
    services.rules.mark_posted(services.rules.reserve(VID, "sandbox", "유튜브1", d["id"]))
    assert client.get("/api/stats/today").json()["posted"] == 1
    clock.advance(hours=21)  # 2026-11-16 03:00 UTC(한국 12:00) → 한국 다음 날 09:00
    data = client.get("/api/stats/today").json()
    assert data["day"] == "2026-11-17"
    assert (data["videos"], data["drafts"], data["posted"], data["success_rate"]) == (0, 0, 0,
                                                                                    None)


# ---------------------------------------------------------------- 영상 응답의 commented


def test_video_list_has_commented_field_and_keeps_old_fields(setup):
    client, services, use = setup
    before = client.get("/api/videos").json()["items"]
    assert all(v["commented"] == {"sandbox": False, "youtube": False} for v in before)
    for key in ("video_id", "url", "title", "channel_title", "view_count", "source", "fetched_at"):
        assert key in before[0]
    d = approved_draft(client, use)
    services.rules.mark_posted(services.rules.reserve(VID, "sandbox", "유튜브1", d["id"]))
    items = {v["video_id"]: v["commented"] for v in client.get("/api/videos").json()["items"]}
    assert items[VID] == {"sandbox": True, "youtube": False}
    assert items[OTHER] == {"sandbox": False, "youtube": False}
    one = client.get(f"/api/videos/{VID}").json()["item"]
    assert one["commented"] == {"sandbox": True, "youtube": False}
    resolved = client.post("/api/videos/resolve", json={"url": f"https://youtu.be/{VID}"}).json()
    assert resolved["item"]["commented"]["sandbox"] is True


def test_reserved_only_is_not_commented_yet(setup):
    client, services, use = setup
    d = approved_draft(client, use)
    services.rules.reserve(VID, "youtube", "유튜브1", d["id"])
    one = client.get(f"/api/videos/{VID}").json()["item"]
    assert one["commented"] == {"sandbox": False, "youtube": False}


# ---------------------------------------------------------------- 규칙이 API 흐름과 이어지는지


def test_only_approved_draft_can_be_reserved(setup):
    from app.errors import AppError

    client, services, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    with pytest.raises(AppError) as exc:
        services.rules.reserve(VID, "sandbox", "유튜브1", made["id"])
    assert str(exc.value.kind) == "draft_not_approved"
    client.post(f"/api/drafts/{made['id']}/approve")
    assert services.rules.reserve(VID, "sandbox", "유튜브1", made["id"]) > 0


def test_posted_comment_is_compared_by_v11_for_other_videos(setup):
    client, services, use = setup
    d = approved_draft(client, use)
    post_id = services.rules.reserve(VID, "sandbox", "유튜브1", d["id"])
    posted_text = "[광고] 실제로 올린 글은 승인한 초안과 조금 달랐어요. 운명원에서 상담받아 보세요."
    services.rules.mark_posted(post_id, comment_text=posted_text)
    previous = services.drafts.previous_texts(OTHER)
    assert posted_text in previous and d["body"] in previous
    assert posted_text not in services.drafts.previous_texts(VID)  # 같은 영상은 비교하지 않는다


def test_ops_responses_do_not_contain_the_api_key(setup, fake_key):
    client, _, use = setup
    approved_draft(client, use)
    for path in ("/api/records", "/api/stats/today", "/api/profiles", "/api/videos"):
        assert fake_key not in client.get(path).text
