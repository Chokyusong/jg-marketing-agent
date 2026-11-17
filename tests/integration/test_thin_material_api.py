"""자료가 얇은 영상 알리기(2026-11-18 기획 담당, 대표 승인) — 가짜 YouTube.

- ① 목록: 이미 읽은 영상에만 「자막 있음」/「자막 없음」(`transcript`: yes·no·빈 글). 자막을 미리
  읽지 않는다(목록을 불러도 자막 공급처를 부르지 않는다).
- 자막이 없으면 초안 프롬프트가 인기 댓글 내용을 ① 재료로 쓰게 하고, 근거도 댓글을 먼저 고른다.
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, draft
from yt_helpers import YT, add_search_and_videos

VID = "BBBBBBBBBB2"


@pytest.fixture
def client(mock_http, fixture_json, fake_key, make_client):
    mock = mock_http()
    add_search_and_videos(mock, fixture_json)
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    return make_client(mock, key=fake_key)


def badges(client):
    items = client.get("/api/videos").json()["items"]
    return {v["video_id"]: v["transcript"] for v in items}


def test_badge_only_on_videos_already_read(client, monkeypatch):
    from app.transcript import auto

    asked = []
    monkeypatch.setattr(auto, "default_lister", lambda timeout=10.0: asked.append)
    first = badges(client)
    assert set(first.values()) == {""}  # 아직 읽은 영상이 없다
    assert asked == []  # 목록만 불러서는 자막을 읽지 않는다

    assert client.post(f"/api/videos/{VID}/context").status_code == 200
    after = badges(client)
    assert after[VID] == "no"
    assert {v for k, v in after.items() if k != VID} == {""}
    assert client.get(f"/api/videos/{VID}").json()["item"]["transcript"] == "no"

    client.put(f"/api/videos/{VID}/transcript", json={"text": "0:01 하루에 한 번 연락 얘기"})
    assert badges(client)[VID] == "yes"


def test_draft_prompt_uses_comments_when_there_is_no_transcript(client, fake_llm):
    services = client.app.state.services.get()
    llm = fake_llm([ANALYSIS, draft(GOOD_BODY)])
    llm.model = "fake-model"
    services.llm = llm
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["passed"]
    user = llm.calls[1]["kwargs"]["user"]
    assert "**자막이 없는 영상**" in user and "인기 댓글" in user
    # 근거: 자막이 없으면 댓글을 먼저(제목 낱말을 되풀이하지 않게)
    assert data["evidence_source"] == "comment"


def test_draft_prompt_without_thin_note_when_transcript_exists(client, fake_llm):
    services = client.app.state.services.get()
    text = "0:01 하루에 한 번 연락으로 싸웠어요"
    client.put(f"/api/videos/{VID}/transcript", json={"text": text})
    llm = fake_llm([ANALYSIS, draft(GOOD_BODY)])
    llm.model = "fake-model"
    services.llm = llm
    client.post("/api/drafts", json={"video_id": VID})
    assert "**자막이 없는 영상**" not in llm.calls[1]["kwargs"]["user"]


# ---------------------------------------------------------- 자료 상태 세 가지(2026-11-18 덧붙임)


@pytest.fixture
def thin_client(mock_http, fixture_json, fake_key, make_client):
    # 설명이 해시태그뿐인 영상(목록을 부를 때마다 YouTube 설명으로 다시 저장되므로 응답을 바꾼다)
    videos = fixture_json("youtube/videos.json")
    for item in videos["items"]:
        if item["id"] == VID:
            item["snippet"]["description"] = "#인팁특징 #연애 https://example.com"
    mock = mock_http()
    mock.add("GET", f"{YT}/search", json=fixture_json("youtube/search.json"))
    mock.add("GET", f"{YT}/videos", json=videos)
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    return make_client(mock, key=fake_key), mock


def _drop_comments(client):
    from app import db

    services = client.app.state.services.get()
    with db.session(services.context.db_path) as conn:
        conn.execute("UPDATE video_context SET comments_json = '[]' WHERE video_id = ?", (VID,))


def test_title_only_video_is_marked_thin_in_the_list_and_the_context(thin_client):
    client, _ = thin_client
    assert badges(client)[VID] == ""  # 안 읽은 영상은 셋 중 어느 것으로도 표시하지 않는다
    # 설명은 해시태그·주소뿐이고 쓸 만한 댓글은 2개(문턱 3개 미만) → 자료 부족
    assert client.post(f"/api/videos/{VID}/context").json()["material"] == "thin"
    after = badges(client)
    assert after[VID] == "thin"
    assert {v for k, v in after.items() if k != VID} == {""}
    assert client.post(f"/api/videos/{VID}/context").json()["material"] == "thin"


def test_transcript_beats_thin(thin_client):
    client, _ = thin_client
    client.post(f"/api/videos/{VID}/context")
    _drop_comments(client)
    client.put(f"/api/videos/{VID}/transcript", json={"text": "0:01 하루에 한 번 연락 얘기"})
    assert badges(client)[VID] == "yes"


def test_list_makes_no_extra_requests_after_videos_are_read(thin_client):
    # 목록을 띄울 때 드는 요청(=할당량)은 영상을 읽기 전과 같다: 자료 상태는 DB만 본다
    client, mock = thin_client

    def requests_for_list(q: str) -> int:
        before = len(mock.requests)
        assert client.get("/api/videos", params={"q": q}).status_code == 200
        return len(mock.requests) - before

    unread = requests_for_list("연애 검색 하나")
    client.post(f"/api/videos/{VID}/context")
    _drop_comments(client)
    assert requests_for_list("연애 검색 둘") == unread > 0
