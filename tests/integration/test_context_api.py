"""3단계 영상 맥락: ContextService와 API 3개.

- 세 경우: 자막 있음 / 자막 없음(제목·설명 대체) / 댓글 막힘(오류가 아니라 빈 목록)
- 인기 댓글 조회가 할당량 1단위로 기록되는지, 저장된 맥락은 댓글을 다시 부르지 않는지
- POST /api/videos/{id}/context · PUT / DELETE /api/videos/{id}/transcript
- 자막 출처 설정이 unofficial이면 알기 쉬운 오류, API 키가 응답·로그에 없음
"""

import logging

import pytest
from yt_helpers import YT

VID = "BBBBBBBBBB2"  # videos.json·comment_threads.json에 있는 영상
TRANSCRIPT = "0:01 오늘은 연락 문제를 얘기해 볼게요\n1:23 하루에 한 번 연락이면 충분할까요?"


def add_video_and_comments(mock, fixture_json, *, comments=None, status=200):
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    mock.add(
        "GET",
        f"{YT}/commentThreads",
        status_code=status,
        json=comments if comments is not None else fixture_json("youtube/comment_threads.json"),
    )
    return mock


def comment_requests(mock):
    return [r for r in mock.requests if r.url.path == f"{YT}/commentThreads"]


@pytest.fixture
def client_and_mock(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(mock_http(), fixture_json)
    return make_client(mock, key=fake_key), mock


def services_of(client):
    return client.app.state.services.get()


# ---------------------------------------------------------------- 세 경우


def test_no_transcript_uses_title_and_description(client_and_mock):
    client, mock = client_and_mock
    res = client.post(f"/api/videos/{VID}/context")
    assert res.status_code == 200
    data = res.json()
    assert data["video_id"] == VID
    assert data["body_source"] == "title_description"
    assert data["transcript_source"] == "none"
    assert (data["transcript_chars"], data["transcript_text"]) == (0, "")
    assert data["comment_count"] == 2
    assert data["comments_disabled"] is False
    assert data["truncated"] is False
    assert data["context_chars"] == 6000
    assert data["built_at"] == "2026-11-16T03:00:00+00:00"

    ctx = services_of(client).context.build(VID)
    video = ctx.video.video
    assert ctx.body == f"{video.title}\n{video.description}"
    assert "[자막] 없음 · 제목과 설명으로 대신" in services_of(client).context.prompt_text(ctx)


def test_with_transcript_body_is_transcript(client_and_mock):
    client, _ = client_and_mock
    res = client.put(f"/api/videos/{VID}/transcript", json={"text": f"  {TRANSCRIPT}  \n\n\n"})
    assert res.status_code == 200
    data = res.json()
    assert data["body_source"] == "transcript"
    assert data["transcript_source"] == "manual"
    assert data["transcript_text"] == TRANSCRIPT  # 정리된 글
    assert data["transcript_chars"] == len(TRANSCRIPT)
    assert data["comment_count"] == 2

    service = services_of(client).context
    ctx = service.build(VID)
    assert ctx.body == TRANSCRIPT
    prompt = service.prompt_text(ctx)
    assert "[자막 · 붙여 넣은 자막]\n0:01 오늘은 연락 문제를" in prompt
    assert "- 저도 하루에 한 번 연락으로 싸운 적 있어요" in prompt
    search = service.search_text(ctx)
    for part in (ctx.video.video.title, ctx.video.video.description, TRANSCRIPT,
                 "연락 문제는 결국 서로 기대치 차이 같아요"):
        assert part in search


def test_comments_disabled_is_not_an_error(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(
        mock_http(), fixture_json, status=403,
        comments=fixture_json("youtube/error_comments_disabled.json"),
    )
    client = make_client(mock, key=fake_key)
    res = client.post(f"/api/videos/{VID}/context")
    assert res.status_code == 200
    data = res.json()
    assert data["comments_disabled"] is True
    assert data["comment_count"] == 0
    ctx = services_of(client).context.build(VID)
    assert ctx.comments == ()
    assert "[인기 댓글] 댓글이 막힌 영상" in services_of(client).context.prompt_text(ctx)


def test_empty_comment_list(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(mock_http(), fixture_json, comments={"items": []})
    data = make_client(mock, key=fake_key).post(f"/api/videos/{VID}/context").json()
    assert (data["comment_count"], data["comments_disabled"]) == (0, False)


# ---------------------------------------------------------------- 할당량 · 저장


def test_comment_fetch_is_recorded_as_one_unit(client_and_mock):
    client, mock = client_and_mock
    data = client.post(f"/api/videos/{VID}/context").json()
    assert data["quota"]["used_today"] == 2  # 영상 상세 1 + 인기 댓글 1
    params = comment_requests(mock)[0].url.params
    assert (params["videoId"], params["order"], params["maxResults"]) == (VID, "relevance", "20")
    assert client.get("/api/status").json()["youtube"]["quota"]["used_today"] == 2


def test_saved_context_does_not_refetch_comments(client_and_mock, clock):
    client, mock = client_and_mock
    client.post(f"/api/videos/{VID}/context")
    clock.advance(minutes=30)  # 영상 상세는 10분이 지나 다시 부르지만 댓글은 저장된 것을 쓴다
    again = client.post(f"/api/videos/{VID}/context").json()
    assert len(comment_requests(mock)) == 1
    assert again["comment_count"] == 2
    assert again["quota"]["used_today"] == 3

    refreshed = client.post(f"/api/videos/{VID}/context", params={"refresh": "true"}).json()
    assert len(comment_requests(mock)) == 2
    assert refreshed["quota"]["used_today"] == 4


def test_transcript_save_and_clear_reuse_saved_comments(client_and_mock):
    client, mock = client_and_mock
    client.post(f"/api/videos/{VID}/context")
    client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT})
    cleared = client.delete(f"/api/videos/{VID}/transcript")
    assert cleared.status_code == 200
    assert len(comment_requests(mock)) == 1
    assert cleared.json()["quota"]["used_today"] == 2


def test_transcript_before_context_builds_once(client_and_mock):
    # 맥락을 만들기 전에 자막부터 붙여 넣어도 된다(그때 댓글을 한 번 부른다).
    client, mock = client_and_mock
    data = client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT}).json()
    assert data["transcript_source"] == "manual"
    assert data["comment_count"] == 2
    assert len(comment_requests(mock)) == 1


# ---------------------------------------------------------------- 자막 API


def test_put_then_delete_switches_source(client_and_mock):
    client, _ = client_and_mock
    assert client.post(f"/api/videos/{VID}/context").json()["transcript_source"] == "none"
    assert (
        client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT}).json()[
            "transcript_source"
        ]
        == "manual"
    )
    assert client.post(f"/api/videos/{VID}/context").json()["transcript_source"] == "manual"
    data = client.delete(f"/api/videos/{VID}/transcript").json()
    assert (data["transcript_source"], data["body_source"]) == ("none", "title_description")
    assert data["transcript_text"] == ""
    # 지울 것이 없어도 같은 요약(멱등)
    assert client.delete(f"/api/videos/{VID}/transcript").json()["transcript_source"] == "none"


def test_put_overwrites_previous_transcript(client_and_mock):
    client, _ = client_and_mock
    client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT})
    data = client.put(f"/api/videos/{VID}/transcript", json={"text": "고친 자막"}).json()
    assert (data["transcript_text"], data["transcript_chars"]) == ("고친 자막", 5)


@pytest.mark.parametrize(
    ("text", "kind"),
    [("", "transcript_empty"), ("  \n\t ", "transcript_empty"),
     ("가" * 20_001, "transcript_too_long")],
)
def test_put_rejects_bad_transcript_without_calling_youtube(client_and_mock, text, kind):
    client, mock = client_and_mock
    res = client.put(f"/api/videos/{VID}/transcript", json={"text": text})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["kind"] == kind
    assert error["message"] and error["action"]
    assert mock.requests == []


def test_put_requires_text_field(client_and_mock):
    client, _ = client_and_mock
    assert client.put(f"/api/videos/{VID}/transcript", json={}).status_code == 422


def test_long_transcript_is_marked_truncated(client_and_mock):
    client, _ = client_and_mock
    text = "0:01 처음 " + "중간 이야기 " * 2000 + "9:59 끝"
    data = client.put(f"/api/videos/{VID}/transcript", json={"text": text}).json()
    assert data["truncated"] is True
    assert data["transcript_truncated"] is True
    service = services_of(client).context
    prompt = service.prompt_text(service.build(VID))
    assert len(prompt) <= 6000
    assert "0:01 처음" in prompt and "9:59 끝" in prompt and "…(중략)…" in prompt


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/videos/bad-id/context"), ("put", "/api/videos/bad-id/transcript"),
     ("delete", "/api/videos/bad-id/transcript")],
)
def test_invalid_video_id(client_and_mock, method, path):
    client, mock = client_and_mock
    kwargs = {"json": {"text": TRANSCRIPT}} if method == "put" else {}
    res = getattr(client, method)(path, **kwargs)
    assert res.status_code == 422
    assert res.json()["error"]["kind"] == "invalid_url"
    assert mock.requests == []


def test_unknown_video(mock_http, fake_key, make_client):
    mock = mock_http().add("GET", f"{YT}/videos", json={"items": []})
    res = make_client(mock, key=fake_key).post("/api/videos/ZZZZZZZZZZ9/context")
    assert res.status_code == 404
    assert res.json()["error"]["kind"] == "video_not_found"


def test_other_comment_errors_are_reported(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(
        mock_http(), fixture_json, status=403, comments=fixture_json("youtube/error_quota.json")
    )
    res = make_client(mock, key=fake_key).post(f"/api/videos/{VID}/context")
    assert res.status_code == 429
    assert res.json()["error"]["kind"] == "quota_exceeded"


def test_missing_key(make_client):
    res = make_client(key=None).post(f"/api/videos/{VID}/context")
    assert res.status_code == 503
    assert res.json()["error"]["kind"] == "missing_key"


# ---------------------------------------------------------------- 자막 출처 설정(D1)


def test_unofficial_provider_gives_clear_error(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(mock_http(), fixture_json)
    client = make_client(mock, key=fake_key, overrides={"transcript": {"provider": "unofficial"}})
    res = client.post(f"/api/videos/{VID}/context")
    assert res.status_code == 503
    error = res.json()["error"]
    assert error["kind"] == "transcript_provider_off"
    assert "켜져 있지 않습니다" in error["message"]
    assert "transcript.provider" in error["action"] and "manual" in error["action"]
    assert comment_requests(mock) == []  # 댓글까지 가지 않는다

    # 붙여 넣은 자막은 그대로 쓸 수 있다(비공식 조회는 붙여넣기가 없을 때만 쓰는 순서)
    ok = client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT})
    assert ok.status_code == 200
    assert ok.json()["transcript_source"] == "manual"


# ---------------------------------------------------------------- 비밀값


def test_context_responses_and_logs_have_no_key(client_and_mock, fake_key, caplog):
    caplog.set_level(logging.DEBUG)
    client, mock = client_and_mock
    texts = [
        client.post(f"/api/videos/{VID}/context").text,
        client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT}).text,
        client.delete(f"/api/videos/{VID}/transcript").text,
        client.post(f"/api/videos/{VID}/context", params={"refresh": "true"}).text,
    ]
    assert comment_requests(mock)[0].url.params["key"] == fake_key  # 키는 실제로 실려 갔다
    for text in [*texts, caplog.text]:
        assert fake_key not in text
        assert fake_key[4:] not in text


def test_context_error_has_no_key(mock_http, fixture_json, fake_key, make_client, caplog):
    caplog.set_level(logging.DEBUG)
    body = {"error": {"code": 400, "message": f"bad key={fake_key}",
                      "errors": [{"reason": "keyInvalid", "message": f"key {fake_key}"}]}}
    mock = add_video_and_comments(mock_http(), fixture_json, status=400, comments=body)
    res = make_client(mock, key=fake_key).post(f"/api/videos/{VID}/context")
    assert res.status_code == 502
    for text in (res.text, caplog.text):
        assert fake_key not in text and fake_key[4:] not in text
