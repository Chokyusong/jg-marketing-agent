"""6단계 규칙 검사 API: POST /api/validate — {video_id, text} → Validation.

- 대조 자료는 3단계 맥락의 search_text(제목·설명·자막·댓글). 맥락이 없으면 만들어서 쓴다.
- 입력마다 불러도 YouTube를 다시 부르지 않는다(저장된 맥락을 그대로 쓴다).
- 이전 글 비교(V11)는 5단계 전까지 빈 목록. config.yaml의 brand.facts·extra_patterns를 쓴다.
"""

import logging

import pytest
from yt_helpers import YT

VID = "BBBBBBBBBB2"  # videos.json·comment_threads.json에 있는 영상
# 인기 댓글 "저도 하루에 한 번 연락으로 싸운 적 있어요"를 근거로 쓴 글. 2026-11-17 운명원 대목
# 다섯 조각(때·이름·연애 사주·잘 본다는 들은 얘기·가 보겠다는 말)에 맞췄다
GOOD = (
    "[광고] 하루에 한 번 연락으로 싸운다는 이야기가 와닿았어요. "
    "요즘 운명원 연애 사주 잘 본다던데 저도 한번 상담받아 보고 싶어요."
)


def add_video_and_comments(mock, fixture_json, *, comments=None, status=200):
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    mock.add(
        "GET",
        f"{YT}/commentThreads",
        status_code=status,
        json=comments if comments is not None else fixture_json("youtube/comment_threads.json"),
    )
    return mock


def youtube_requests(mock):
    return [r for r in mock.requests if r.url.path.startswith(YT)]


@pytest.fixture
def client_and_mock(mock_http, fixture_json, fake_key, make_client):
    mock = add_video_and_comments(mock_http(), fixture_json)
    return make_client(mock, key=fake_key), mock


def post(client, text, video_id=VID):
    return client.post("/api/validate", json={"video_id": video_id, "text": text})


def by_code(data):
    return {c["code"]: c for c in data["checks"]}


def test_good_text_passes_and_builds_context_when_missing(client_and_mock):
    client, mock = client_and_mock
    res = post(client, GOOD)
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is True
    assert data["char_count"] == len(GOOD)
    assert (data["min_chars"], data["max_chars"], data["disclosure"]) == (40, 120, "[광고]")
    # 2026-11-18 지시서 5절: V1~V6·V8~V11 열 개
    assert (data["passed_count"], data["total"]) == (10, 10)
    assert [c["code"] for c in data["checks"]] == [
        "V1", "V2", "V3", "V4", "V5", "V6", "V8", "V9", "V10", "V11"]
    assert set(data["checks"][0]) == {"code", "name", "passed", "message"}
    assert data["evidence_quote"] == "하루에 한 번 연락으로 싸운"
    # 맥락이 없어서 만들었다: 영상 상세 1 + 인기 댓글 1
    paths = [r.url.path for r in youtube_requests(mock)]
    assert paths.count(f"{YT}/commentThreads") == 1
    assert client.get("/api/status").json()["youtube"]["quota"]["used_today"] == 2


def test_repeated_checks_do_not_call_youtube_again(client_and_mock, clock):
    client, mock = client_and_mock
    client.post(f"/api/videos/{VID}/context")
    before = len(youtube_requests(mock))
    clock.advance(minutes=30)  # 영상 정보가 오래돼도 검사할 때는 저장된 것을 쓴다
    for text in (GOOD, GOOD + " 응원해요", GOOD.replace("와닿았어요", "공감돼요")):
        assert post(client, text).status_code == 200
    assert len(youtube_requests(mock)) == before


def test_check_does_not_rewrite_saved_context(client_and_mock, clock):
    client, _ = client_and_mock
    built = client.post(f"/api/videos/{VID}/context").json()["built_at"]
    clock.advance(minutes=5)
    post(client, GOOD)
    services = client.app.state.services.get()
    assert services.context.current(VID).built_at == built


def test_link_fails_v2_and_removing_it_passes(client_and_mock):
    client, _ = client_and_mock
    data = post(client, GOOD + " www.example.com").json()
    assert data["passed"] is False
    assert data["passed_count"] == 9
    v2 = by_code(data)["V2"]
    assert v2["passed"] is False and "링크를 지우세요" in v2["message"]
    assert post(client, GOOD).json()["passed"] is True


def test_human_text_without_evidence_fails_v6(client_and_mock):
    client, _ = client_and_mock
    text = (
        "[광고] 연애 고민이 많을 때는 혼자 앓기보다 누군가와 이야기를 나눠 "
        "보세요. 운명원에서 상담받아 보세요."
    )
    checks = by_code(post(client, text).json())
    assert checks["V6"]["passed"] is False
    # 연애 사주 얘기 없이 운명원만 권하면 V5도 걸린다(2026-11-18 지시서 5절)
    assert checks["V5"]["passed"] is False
    assert all(checks[c]["passed"] for c in ("V1", "V2", "V3", "V4", "V8", "V9", "V10"))


def test_pasted_transcript_becomes_evidence(client_and_mock):
    client, _ = client_and_mock
    text = (
        "[광고] 오늘은 연락 문제를 얘기해 볼게요라는 첫마디에 "
        "공감했어요. 운명원에서 상담받아 보세요."
    )
    assert by_code(post(client, text).json())["V6"]["passed"] is False
    transcript = {"text": "0:01 오늘은 연락 문제를 얘기해 볼게요"}
    client.put(f"/api/videos/{VID}/transcript", json=transcript)
    data = post(client, text).json()
    assert by_code(data)["V6"]["passed"] is True
    assert data["evidence_quote"] == "오늘은 연락 문제를 얘기해 볼게요"


def test_comments_disabled_video_is_checked_against_title_and_description(
    mock_http, fixture_json, fake_key, make_client
):
    mock = add_video_and_comments(
        mock_http(), fixture_json, status=403,
        comments=fixture_json("youtube/error_comments_disabled.json"),
    )
    client = make_client(mock, key=fake_key)
    text = (
        "[광고] 연락 빈도 때문에 다투는 커플 얘기 남 일 같지 않네요. "
        "요즘 운명원 연애 사주 잘 본다고 하던데 저도 한번 가 보려고요."
    )
    data = post(client, text).json()
    assert data["passed"] is True, data
    assert data["evidence_quote"] == "연락 빈도 때문에 다투는"
    # 2026-11-18 지시서로 V13(길게 베끼기)은 뺐다: 설명란 글을 길게 옮겨도 규칙 검사는 통과
    long_copy = post(client, "[광고] 연락 빈도 때문에 다투는 장거리 커플 이야기에 공감했어요. "
                             "요즘 운명원 연애 사주 잘 본다던데 저도 가 보려고요.").json()
    assert long_copy["passed"] is True


def test_previous_texts_are_empty_until_stage5(client_and_mock):
    client, _ = client_and_mock
    post(client, GOOD)
    v11 = by_code(post(client, GOOD).json())["V11"]  # 같은 글을 두 번 검사해도 저장·비교하지 않는다
    assert v11["passed"] is True and "이전 글 없음" in v11["message"]


def test_brand_facts_and_extra_patterns_come_from_config(
    mock_http, fixture_json, fake_key, make_client
):
    overrides = {
        "brand": {"facts": ["운명원은 연애 사주만 30년째 하는 제일 오래된 상담소다"]},
        "validator": {"extra_patterns": [{"code": "V9", "pattern": "궁금해서"}]},
    }
    client = make_client(add_video_and_comments(mock_http(), fixture_json), key=fake_key,
                         overrides=overrides)
    fact_text = GOOD.replace("운명원 연애", "제일 오래된 상담소인 운명원 연애")
    assert by_code(post(client, fact_text).json())["V10"]["passed"] is True
    assert by_code(post(client, GOOD + " 궁금해서요").json())["V9"]["passed"] is False

    default_client = make_client(add_video_and_comments(mock_http(), fixture_json), key=fake_key)
    assert by_code(post(default_client, fact_text).json())["V10"]["passed"] is False


def test_invalid_video_id(client_and_mock):
    client, mock = client_and_mock
    res = post(client, GOOD, video_id="bad id!")
    assert res.status_code == 422
    assert res.json()["error"]["kind"] == "invalid_url"
    assert youtube_requests(mock) == []


def test_missing_key_without_saved_context(make_client):
    res = post(make_client(key=None), GOOD)
    assert res.status_code == 503
    assert res.json()["error"]["kind"] == "missing_key"


@pytest.mark.parametrize("body", [{"video_id": VID}, {"text": GOOD}, {"video_id": "", "text": GOOD},
                                  {"video_id": VID, "text": "가" * 2001}])
def test_bad_body_is_422(client_and_mock, body):
    client, _ = client_and_mock
    assert client.post("/api/validate", json=body).status_code == 422


def test_long_text_is_checked_not_rejected(client_and_mock):
    client, _ = client_and_mock
    data = post(client, GOOD + " 응원해요" * 20).json()
    v1 = by_code(data)["V1"]
    assert v1["passed"] is False and "줄이세요" in v1["message"]


def test_response_and_logs_have_no_key(client_and_mock, fake_key, caplog):
    client, _ = client_and_mock
    with caplog.at_level(logging.DEBUG):
        res = post(client, GOOD + " http://example.com")
    assert fake_key not in res.text
    assert fake_key not in caplog.text
