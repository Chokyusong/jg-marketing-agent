"""5단계 분석과 초안(DraftService + API 5개) — 가짜 YouTube, 가짜 LLM(fake_llm).

- 분석: 모델이 지어낸 근거는 영상 자료와 대조해 버린다. 출처는 코드가 자료에서 찾는다.
- 초안: 모델은 본문만 쓰고 [광고]는 코드가 붙인다. 검사에 걸리면 실패 문구를 넣어 최대 3번.
  세 번 다 걸리면 실패가 가장 적은 것을 저장한다.
- 사람이 고친 글은 다시 검사한다. 검사에 걸린 초안은 승인 API가 409로 거절한다.
- [다른 초안]은 이미 쓴 근거를 피한다. V11은 다른 영상에서 승인한 초안과 비교한다.
"""

import pytest
from yt_helpers import YT

VID = "BBBBBBBBBB2"  # 장거리 연애 1년차, 연락 문제로 자주 싸워요
OTHER = "AAAAAAAAAA1"  # 썸 타다 끝나는 이유 3가지
TRANSCRIPT = (
    "0:10 퇴근하고 영상통화를 하자고 했는데 피곤하다고 거절당했어요\n"
    "0:40 주말마다 기차를 타고 내려가는 게 점점 지쳐요"
)
Q_TRANSCRIPT = "퇴근하고 영상통화를 하자고 했는데"
Q_COMMENT = "하루에 한 번 연락으로 싸운 적 있어요"
INVENTED = "매일 밤 손편지를 써서 보냈대요"

ANALYSIS = {
    "topic": "장거리 연애 연락 문제",
    "concern": "연락 빈도 차이로 자주 다투는 장거리 커플",
    "tone": "진지한 사연 읽기",
    "viewer_needs": "연락 다툼을 줄이는 방법",
    "evidence": [
        {"quote": Q_COMMENT, "source": "comment"},
        {"quote": INVENTED, "source": "transcript"},  # 자료에 없다 → 버린다
        {"quote": "서로 기대치 차이 같아요", "source": "transcript"},  # 출처가 틀렸다 → 댓글
    ],
}
GOOD_BODY = (
    "'하루에 한 번 연락으로 싸운 적 있어요'라는 댓글이 마음에 남네요. "
    "운명원에서 연애 사주 상담을 받아 보셔도 좋겠어요."
)
GOOD_BODY_2 = (
    "'서로 기대치 차이 같아요'라는 말처럼 마음의 속도가 다를 때가 있죠. "
    "운명원의 연애 사주 상담으로 흐름을 짚어 보세요."
)
NO_BRAND = "'하루에 한 번 연락으로 싸운 적 있어요'라는 말에 공감해요. 연애 사주 상담을 받아 보세요."
NO_BRAND_TAG = (
    "'하루에 한 번 연락으로 싸운 적 있어요'라는 말에 공감해요 #연애 상담을 받아 보세요."
)
MANY_FAILS = "운명원 최고! www.example.com #연애"
OTHER_BODY = (
    "요즘 '하루에 한 번 연락으로 싸운 적 있어요' 같은 고민이 많죠. 썸에서 연애로 넘어가는 흐름이 "
    "궁금하면 운명원의 사주 풀이를 권해요."
)


def draft(body, tone="공감형", quote=Q_COMMENT):
    return {"body": body, "used_quote": quote, "tone_label": tone}


def add_youtube(mock, fixture_json):
    mock.add("GET", f"{YT}/videos", json=fixture_json("youtube/videos.json"))
    mock.add("GET", f"{YT}/commentThreads", json=fixture_json("youtube/comment_threads.json"))
    return mock


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm):
    """(client, services, llm 넣기). 가짜 LLM은 `use([...])`로 응답을 정한다."""
    client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key)
    services = client.app.state.services.get()

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        services.llm = llm
        return llm

    return client, services, use


def user_prompts(llm):
    return [c["kwargs"]["user"] for c in llm.calls]


def codes(validation):
    return {c["code"] for c in validation["checks"] if not c["passed"]}


# ---------------------------------------------------------------- 분석


def test_analysis_drops_invented_evidence_and_fixes_source(setup):
    client, _, use = setup
    llm = use([ANALYSIS])
    res = client.post(f"/api/analysis/{VID}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["concern"] == ANALYSIS["concern"]
    assert (data["topic"], data["tone"], data["viewer_needs"]) == (
        ANALYSIS["topic"], ANALYSIS["tone"], ANALYSIS["viewer_needs"])
    quotes = [e["quote"] for e in data["evidence"]]
    assert INVENTED not in quotes  # 모델이 지어낸 근거는 버렸다
    assert data["dropped_count"] == 1
    assert data["evidence"][0] == {"quote": Q_COMMENT, "source": "comment", "source_label": "댓글"}
    assert data["evidence"][1]["source"] == "comment"  # 모델은 transcript라 했지만 댓글에 있다
    assert data["model"] == "fake-model" and data["fallback"] is False
    assert len(llm.calls) == 1
    call = llm.calls[0]["kwargs"]
    assert call["temperature"] == 0.2  # 분석은 낮은 온도
    assert "[영상 자료 시작]" in call["user"] and "장거리 연애 1년차" in call["user"]
    # 저장했다: 모델을 부르지 않고 다시 읽는다
    again = client.get(f"/api/analysis/{VID}").json()
    assert again["concern"] == data["concern"] and len(llm.calls) == 1


def test_analysis_retries_once_when_all_evidence_is_invented_then_falls_back_to_title(setup):
    client, _, use = setup
    invented = dict(ANALYSIS, evidence=[{"quote": INVENTED, "source": "transcript"}])
    llm = use([invented, invented])
    data = client.post(f"/api/analysis/{VID}").json()
    assert len(llm.calls) == 2
    assert "[다시 요청]" in user_prompts(llm)[1] and INVENTED in user_prompts(llm)[1]
    assert data["fallback"] is True
    assert data["evidence"] == [{"quote": "장거리 연애 1년차, 연락 문제로 자주 싸워요",
                                 "source": "title", "source_label": "제목"}]


def test_analysis_uses_pasted_transcript_first(setup):
    client, _, use = setup
    assert client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT}).status_code == 200
    use([dict(ANALYSIS, evidence=ANALYSIS["evidence"] + [
        {"quote": "퇴근하고 영상통화를 하자고 했는데 피곤하다고 거절당했어요",
         "source": "comment"}])])
    data = client.post(f"/api/analysis/{VID}").json()
    sources = {e["quote"]: e["source"] for e in data["evidence"]}
    # 원문 안의 한 마디로 줄이고(40자 넘으면), 출처는 자막으로 고친다
    assert any(q.startswith("퇴근하고 영상통화를") and s == "transcript"
               for q, s in sources.items())


def test_stored_analysis_is_null_before_running(setup):
    client, _, _ = setup
    res = client.get(f"/api/analysis/{VID}")
    assert res.status_code == 200 and res.json() is None


def test_analysis_reports_llm_down(make_client, mock_http, fixture_json, fake_key):
    # 가짜 LLM을 넣지 않으면 make_client는 「Ollama 꺼짐」이다
    client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key)
    res = client.post(f"/api/analysis/{VID}")
    assert res.status_code == 503
    assert res.json()["error"]["kind"] == "llm_down"


def test_analysis_rejects_bad_video_id(setup):
    client, _, _ = setup
    assert client.post("/api/analysis/not-an-id").status_code == 422


# ---------------------------------------------------------------- 초안: 시도 횟수


def test_draft_passes_on_first_try_and_code_adds_disclosure(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{VID}")
    res = client.post("/api/drafts", json={"video_id": VID})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["body"] == f"[광고] {GOOD_BODY}"  # 모델은 본문만, 표기는 코드가
    assert data["passed"] is True and data["first_passed"] is True
    assert data["attempts"] == 1 and data["status"] == "draft"
    assert data["evidence_quote"] == Q_COMMENT and data["evidence_source"] == "comment"
    assert data["evidence_label"] == "댓글" and data["tone_label"] == "공감형"
    assert data["validation"]["passed"] is True and data["validation"]["total"] == 12
    call = llm.calls[1]["kwargs"]
    assert call["temperature"] == 0.8  # 초안은 높은 온도
    assert "[광고]는 쓰지 않는다" in call["system"]
    assert f"'{Q_COMMENT}'" in call["user"] and "35~115자" in call["user"]


def test_disclosure_written_by_model_is_not_doubled(setup):
    client, _, use = setup
    use([ANALYSIS, draft(f"[광고] {GOOD_BODY}\n")])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["body"] == f"[광고] {GOOD_BODY}"
    assert data["body"].count("[광고]") == 1 and "\n" not in data["body"]


def test_draft_passes_on_second_try_with_failure_lines_in_prompt(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(NO_BRAND), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()  # 분석이 없으면 먼저 한다
    assert data["passed"] is True and data["attempts"] == 2 and data["first_passed"] is False
    retry = user_prompts(llm)[2]
    assert "[다시 쓰기]" in retry
    assert f"앞의 본문: {NO_BRAND}" in retry
    assert "V5 브랜드 이름 1~2번" in retry


def test_all_three_tries_fail_and_the_least_bad_is_saved(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(NO_BRAND_TAG), draft(NO_BRAND), draft(MANY_FAILS)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert len(llm.calls) == 4 and llm.remaining == 0  # 분석 1 + 초안 3(그 뒤로는 안 부른다)
    assert data["attempts"] == 3 and data["passed"] is False
    assert data["body"] == f"[광고] {NO_BRAND}"  # 실패 1개짜리(두 번째)를 저장
    assert codes(data["validation"]) == {"V5"}
    # 세 번째 프롬프트에는 두 번째 실패가 들어 있다
    assert "V5 브랜드 이름" in user_prompts(llm)[3]


def test_llm_error_after_a_try_keeps_the_best_so_far(setup):
    from app.errors import AppError, ErrorKind

    client, _, use = setup
    use([ANALYSIS, draft(NO_BRAND), AppError(ErrorKind.LLM_TIMEOUT)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 1 and data["passed"] is False


def test_llm_error_before_any_draft_is_reported(setup):
    from app.errors import AppError, ErrorKind

    client, _, use = setup
    use([ANALYSIS, AppError(ErrorKind.LLM_TIMEOUT)])
    res = client.post("/api/drafts", json={"video_id": VID})
    assert res.status_code == 504 and res.json()["error"]["kind"] == "llm_timeout"


# ---------------------------------------------------------------- 다른 초안 · 목록


def test_another_draft_uses_a_different_quote(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY_2, tone="조언형",
                                                  quote="서로 기대치 차이 같아요")])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    second = client.post("/api/drafts", json={"video_id": VID, "another": True}).json()
    assert first["evidence_quote"] == Q_COMMENT
    assert second["evidence_quote"] == "서로 기대치 차이 같아요"
    assert "'서로 기대치 차이 같아요'" in user_prompts(llm)[2]
    assert GOOD_BODY in user_prompts(llm)[2]  # 같은 영상의 앞 초안과 다르게 쓰라고 알린다
    assert second["passed"] is True and second["tone_label"] == "조언형"

    listed = client.get("/api/drafts", params={"video_id": VID}).json()
    assert [d["id"] for d in listed["items"]] == [second["id"], first["id"]]  # 최신이 위
    assert [d["status"] for d in listed["items"]] == ["draft", "superseded"]


def test_avoid_quotes_from_the_client_are_respected(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY_2, quote="서로 기대치 차이 같아요")])
    data = client.post("/api/drafts", json={"video_id": VID, "avoid_quotes": [Q_COMMENT]}).json()
    assert data["evidence_quote"] == "서로 기대치 차이 같아요"


def test_list_is_empty_for_new_video(setup):
    client, _, _ = setup
    assert client.get("/api/drafts", params={"video_id": VID}).json() == {"video_id": VID,
                                                                           "items": []}
    assert client.get("/api/drafts").status_code == 422  # video_id가 필요하다


# ---------------------------------------------------------------- 사람이 고침 · 승인


def test_human_edit_is_checked_again(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    broken = client.patch(f"/api/drafts/{made['id']}",
                          json={"body": made["body"] + " www.example.com"}).json()
    assert broken["passed"] is False and "V2" in codes(broken["validation"])
    assert broken["edited_by_human"] is True and broken["attempts"] == 1
    fixed_text = (
        "[광고] 하루에 한 번 연락으로 싸운 적 있다는 댓글에 공감했어요. "
        "운명원 연애 사주 상담도 있어요."
    )
    fixed = client.patch(f"/api/drafts/{made['id']}", json={"body": fixed_text}).json()
    assert fixed["passed"] is True and fixed["body"] == fixed_text


def test_failed_draft_cannot_be_approved(setup):
    client, _, use = setup
    use([ANALYSIS, draft(NO_BRAND_TAG), draft(NO_BRAND), draft(NO_BRAND)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    assert made["passed"] is False
    res = client.post(f"/api/drafts/{made['id']}/approve")
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["kind"] == "draft_not_passed"
    assert [f["code"] for f in error["failures"]] == ["V5"]
    assert {"code", "name", "passed", "message"} == set(error["failures"][0])
    items = client.get("/api/drafts", params={"video_id": VID}).json()["items"]
    assert items[0]["status"] == "draft"


def test_human_breaking_a_passed_draft_blocks_approval(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    client.patch(f"/api/drafts/{made['id']}", json={"body": made["body"] + " #연애"})
    res = client.post(f"/api/drafts/{made['id']}/approve")
    assert res.status_code == 409 and "V3" in [f["code"] for f in res.json()["error"]["failures"]]


def test_approve_passed_draft(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY_2, quote="서로 기대치 차이 같아요")])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    res = client.post(f"/api/drafts/{first['id']}/approve")
    assert res.status_code == 200
    approved = res.json()
    assert approved["status"] == "approved" and approved["approved_at"]
    # 새 초안을 만들어도 승인한 것은 그대로, 새것을 승인하면 앞의 승인은 밀려난다(영상당 하나)
    second = client.post("/api/drafts", json={"video_id": VID, "another": True}).json()
    items = {d["id"]: d["status"] for d in
             client.get("/api/drafts", params={"video_id": VID}).json()["items"]}
    assert items == {first["id"]: "approved", second["id"]: "draft"}
    client.post(f"/api/drafts/{second['id']}/approve")
    items = {d["id"]: d["status"] for d in
             client.get("/api/drafts", params={"video_id": VID}).json()["items"]}
    assert items == {first["id"]: "superseded", second["id"]: "approved"}
    # 밀려난 초안은 고치거나 승인할 수 없다
    assert client.post(f"/api/drafts/{first['id']}/approve").json()["error"]["kind"] == (
        "draft_superseded")


def test_editing_an_approved_draft_needs_approval_again(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    client.post(f"/api/drafts/{made['id']}/approve")
    edited = client.patch(f"/api/drafts/{made['id']}",
                          json={"body": made["body"].replace("좋겠어요", "좋아요")}).json()
    assert edited["status"] == "draft" and edited["approved_at"] is None


def test_unknown_draft_is_404(setup):
    client, _, _ = setup
    assert client.post("/api/drafts/999/approve").status_code == 404
    res = client.patch("/api/drafts/999", json={"body": "x"})
    assert res.status_code == 404 and res.json()["error"]["kind"] == "draft_not_found"


# ---------------------------------------------------------------- V11: 승인한 초안과 비교


def test_v11_compares_with_drafts_approved_for_other_videos(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), ANALYSIS, draft(GOOD_BODY), draft(OTHER_BODY)])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    assert client.post(f"/api/drafts/{first['id']}/approve").status_code == 200
    # 다른 영상에 같은 글 → V11에 걸려 다시 쓴다
    other = client.post("/api/drafts", json={"video_id": OTHER}).json()
    assert other["attempts"] == 2
    assert "V11 이전 글과 다름" in user_prompts(llm)[4]
    assert other["body"] == f"[광고] {OTHER_BODY}" and other["passed"] is True
    # 직접 쓰는 검사(POST /api/validate)도 승인한 초안과 비교한다
    check = client.post("/api/validate", json={"video_id": OTHER, "text": first["body"]}).json()
    assert "V11" in codes(check)
    # 같은 영상 안에서는 비교하지 않는다(승인한 초안을 다시 검사해도 걸리지 않음)
    same = client.post("/api/validate", json={"video_id": VID, "text": first["body"]}).json()
    assert "V11" not in codes(same)


def test_responses_do_not_contain_the_api_key(setup, fake_key):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    for res in (client.post(f"/api/analysis/{VID}"),
                client.post("/api/drafts", json={"video_id": VID}),
                client.get("/api/drafts", params={"video_id": VID})):
        assert fake_key not in res.text


# ---------------------------------------------------------------- 5단계 점검: V12와 권유 문장


HANJA_BODY = GOOD_BODY.replace("마음에 남네요", "마음이揪입니다")


def test_hanja_in_draft_fails_v12_and_is_rewritten(setup):
    # 실제 qwen3.8:27b 초안에 섞여 나온 한자(揪) → V12에 걸려 다시 쓴다
    client, _, use = setup
    llm = use([ANALYSIS, draft(HANJA_BODY), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 2 and data["passed"] is True and data["first_passed"] is False
    retry = user_prompts(llm)[2]
    assert "[다시 쓰기]" in retry and f"앞의 본문: {HANJA_BODY}" in retry
    assert "V12" in retry and "'揪'(한자)" in retry
    assert data["body"] == f"[광고] {GOOD_BODY}"


def test_hanja_draft_that_never_gets_fixed_cannot_be_approved(setup):
    client, _, use = setup
    use([ANALYSIS, draft(HANJA_BODY), draft(HANJA_BODY), draft(HANJA_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["passed"] is False and codes(data["validation"]) == {"V12"}
    res = client.post(f"/api/drafts/{data['id']}/approve")
    assert res.status_code == 409
    assert [f["code"] for f in res.json()["error"]["failures"]] == ["V12"]


def test_draft_prompt_lists_closings_of_drafts_approved_for_other_videos(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), ANALYSIS, draft(OTHER_BODY)])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    assert "이미 쓴 권유 문장" not in user_prompts(llm)[1]  # 승인한 초안이 아직 없다
    assert client.post(f"/api/drafts/{first['id']}/approve").status_code == 200
    client.post("/api/drafts", json={"video_id": OTHER})
    prompt = user_prompts(llm)[3]
    assert "이미 쓴 권유 문장(다른 영상에 승인됨)" in prompt
    assert "- 운명원에서 연애 사주 상담을 받아 보셔도 좋겠어요." in prompt
    assert "핵심 고민(" in prompt
