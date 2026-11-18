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
    "concern": "연락 횟수 때문에 맨날 싸우는데 우리 괜찮은 걸까",
    "tone": "진지한 사연 읽기",
    "viewer_needs": "연락 다툼을 줄이는 방법",
    "evidence": [
        {"quote": Q_COMMENT, "source": "comment"},
        {"quote": INVENTED, "source": "transcript"},  # 자료에 없다 → 버린다
        {"quote": "서로 기대치 차이 같아요", "source": "transcript"},  # 출처가 틀렸다 → 댓글
    ],
    # C1: 핵심 말. '운명원'(브랜드)·'연애'(흔한 말)·'손편지'(자료에 없음)는 코드가 거른다
    "key_phrases": ["장거리", "하루에 한 번 연락", "기대치 차이", "운명원", "연애", "손편지"],
}
KEYS = ["장거리", "하루에 한 번 연락", "기대치 차이"]
# C1 새 기준(시청자 말투, 핵심 말을 담고 자료를 13자 이상 이어서 옮기지 않음)으로 다시 씀
# 2026-11-17(대표 다섯 조각): 운명원 대목을 「때·이름·연애 사주·잘 본다는 들은 얘기·가 보겠다는
# 말」로 바꿨다(V14가 넓어졌다)
GOOD_BODY = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요ㅠㅠ "
    "요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요."
)
GOOD_CLOSING = "요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요."
GOOD_BODY_2 = (
    "기대치 차이라는 말에 뜨끔했어요. 연애만 하면 마음 속도가 엇갈리는 편이라... "
    "요새 운명원이 연애사주를 꽤 잘 봐준다는 얘기가 있던데, 저도 조만간 상담받아보고 싶네요."
)
NO_BRAND = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글에 공감해요. 연애 사주 상담을 한번 받아 보고 싶네요."
)
NO_BRAND_TAG = "하루에 한 번 연락 갖고 싸웠다는 댓글에 공감해요 #연애 상담을 한번 받아 보고 싶네요."
MANY_FAILS = "운명원 최고! www.example.com #연애"
OTHER_BODY = (
    "썸 타다 끝나는 게 제 전문이라 웃프네요ㅋㅋ 하루에 한 번 연락도 어려운 1인... "
    "최근에 운명원이 연애 쪽 사주로 유명하다던데 저도 한번 방문해 볼까 해요."
)


def draft(body, tone="공감형", quote=Q_COMMENT):
    """AI의 댓글 답(2026-11-18: mood·body·wish·used_quote). `tone`은 기분 칸으로 들어간다."""
    return {"mood": tone, "body": body, "wish": "궁합", "used_quote": quote}


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


def test_analysis_retries_once_when_all_evidence_is_invented_then_stops(setup):
    """실제 데이터 보정: 다시 시켜도 근거가 0개면 제목으로 때우지 않고 no_love_concern으로 멈춘다.

    (예전에는 제목을 근거로 썼다 — fallback. 그 동작은 이 보정에서 바꿨다)
    """
    client, _, use = setup
    invented = dict(ANALYSIS, evidence=[{"quote": INVENTED, "source": "transcript"}])
    llm = use([invented, invented])
    res = client.post(f"/api/analysis/{VID}")
    assert len(llm.calls) == 2
    assert "[다시 요청]" in user_prompts(llm)[1] and INVENTED in user_prompts(llm)[1]
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["kind"] == "no_love_concern"
    assert error["message"] == "이 영상 자료에서 연애 고민을 찾지 못했습니다."
    assert client.get(f"/api/analysis/{VID}").json() is None  # 저장하지 않았다


# ------------------------------------------------- 연애 고민이 없으면 멈춘다(실제 데이터 보정)

NO_CONCERN = {
    "has_love_concern": False,
    "reason": "설명과 댓글이 상품 이벤트 글뿐",
    "topic": "",
    "concern": "",
    "tone": "",
    "viewer_needs": "",
    "evidence": [],
}


def test_no_love_concern_stops_without_a_draft(setup):
    client, services, use = setup
    llm = use([NO_CONCERN, draft(GOOD_BODY)])
    res = client.post("/api/drafts", json={"video_id": VID})  # 분석이 없으면 먼저 한다
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["kind"] == "no_love_concern"
    assert error["message"] == "이 영상 자료에서 연애 고민을 찾지 못했습니다."
    assert "자막을 붙여 넣고 다시 분석하거나 다른 영상을 골라 주세요" in error["action"]
    assert "광고·협찬 위주" in error["action"]
    assert error["detail"] == "설명과 댓글이 상품 이벤트 글뿐"
    assert len(llm.calls) == 1  # 초안은 쓰게 하지 않았다
    assert client.get("/api/drafts", params={"video_id": VID}).json()["items"] == []
    # 작업 기록: 분석 실패(사유)와 초안 실패
    rows = client.get("/api/records").json()["items"]
    analyze = [r for r in rows if r["action"] == "analyze"]
    assert analyze and analyze[0]["result"] == "failure"
    assert "연애 고민을 찾지 못했습니다" in analyze[0]["reason"]
    assert "상품 이벤트 글뿐" in analyze[0]["reason"]


def test_no_love_concern_on_retry_also_stops(setup):
    client, _, use = setup
    invented = dict(ANALYSIS, evidence=[{"quote": INVENTED, "source": "transcript"}])
    llm = use([invented, NO_CONCERN])
    res = client.post(f"/api/analysis/{VID}")
    assert res.status_code == 422 and res.json()["error"]["kind"] == "no_love_concern"
    assert len(llm.calls) == 2


def test_no_love_concern_forgets_the_old_analysis(setup):
    client, _, use = setup
    use([ANALYSIS])
    assert client.post(f"/api/analysis/{VID}").status_code == 200
    use([NO_CONCERN])
    assert client.post(f"/api/analysis/{VID}").status_code == 422
    assert client.get(f"/api/analysis/{VID}").json() is None
    # 예전 분석으로 초안을 만들지 않는다: 초안 요청은 다시 분석부터 한다
    llm = use([NO_CONCERN])
    assert client.post("/api/drafts", json={"video_id": VID}).status_code == 422
    assert len(llm.calls) == 1


def test_promo_quotes_are_not_evidence(setup):
    """자료에 실제로 있어도 광고·협찬·응모 글은 근거로 받지 않는다(버린 근거로 센다)."""
    client, _, use = setup
    promo_line = "오늘 영상은 협찬을 받아 만들었어요"
    text = TRANSCRIPT + f"\n1:10 {promo_line}\n1:20 댓글로 응모하시면 추첨해서 드려요"
    assert client.put(f"/api/videos/{VID}/transcript", json={"text": text}).status_code == 200
    promo = dict(ANALYSIS, has_love_concern=True, reason="연애 고민 있음", evidence=[
        {"quote": promo_line, "source": "transcript"},
        {"quote": "댓글로 응모하시면 추첨해서 드려요", "source": "transcript"},
        {"quote": Q_COMMENT, "source": "comment"},
    ])
    use([promo])
    data = client.post(f"/api/analysis/{VID}").json()
    assert data["has_love_concern"] is True and data["love_reason"] == "연애 고민 있음"
    assert [e["quote"] for e in data["evidence"]] == [Q_COMMENT]
    assert data["dropped_count"] == 2


def test_analysis_prompt_warns_about_ads_when_there_is_no_transcript(setup):
    client, _, use = setup
    llm = use([ANALYSIS])
    client.post(f"/api/analysis/{VID}")
    system = llm.calls[0]["kwargs"]["system"]
    user = llm.calls[0]["kwargs"]["user"]
    assert "연애 고민" in system and "광고·협찬" in system
    assert "has_love_concern" in user
    assert "설명란과 댓글에는 광고·협찬" in user  # 자막이 없을 때만 붙는 안내
    # 자막을 붙여 넣으면 그 안내는 빠진다
    client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT})
    llm = use([ANALYSIS])
    client.post(f"/api/analysis/{VID}")
    assert "설명란과 댓글에는 광고·협찬" not in llm.calls[0]["kwargs"]["user"]


def test_draft_prompt_names_only_the_brand(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY)])
    client.post("/api/drafts", json={"video_id": VID})
    system = llm.calls[1]["kwargs"]["system"]
    # 2026-11-18 지시서: 시스템 글의 [운명원] 칸에는 운명원 하나만 나온다
    # 9회차: 들은 말 요지를 뽑으면 소개 문장 대신 「연애 사주를 보는 곳이다」
    assert "[운명원]\n- 연애 사주를 보는 곳이다." in system
    assert "가 본 적은 없다" in system


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
    # tone_label = "말 높임 / 들은 경로 / 기분"(기분은 AI가 고른 mood)
    assert data["evidence_label"] == "댓글" and data["tone_label"].endswith(" / 공감형")
    assert data["validation"]["passed"] is True and data["validation"]["total"] == 10
    call = llm.calls[1]["kwargs"]
    assert call["temperature"] == 0.8  # 초안은 높은 온도
    assert "광고" not in call["system"]  # 광고 표기는 코드가 붙인다(AI에게 말하지 않음)
    assert f"- (댓글) {Q_COMMENT}" in call["user"] and "40~120자" in call["system"]


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
    assert "- 걸린 까닭: V5 운명원 1~2번 · 연애 사주" in retry


def test_all_three_tries_fail_and_the_least_bad_is_saved(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(NO_BRAND_TAG), draft(NO_BRAND), draft(MANY_FAILS)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert len(llm.calls) == 4 and llm.remaining == 0  # 분석 1 + 초안 3(그 뒤로는 안 부른다)
    assert data["attempts"] == 3 and data["passed"] is False
    assert data["body"] == f"[광고] {NO_BRAND}"  # 실패 1개짜리(두 번째)를 저장
    assert codes(data["validation"]) == {"V5"}
    # 세 번째 프롬프트에는 두 번째 실패가 들어 있다
    assert "V5 운명원 1~2번" in user_prompts(llm)[3]


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
    llm = use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY_2, tone="혼잣말형",
                                                  quote="서로 기대치 차이 같아요")])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    second = client.post("/api/drafts", json={"video_id": VID, "another": True}).json()
    assert first["evidence_quote"] == Q_COMMENT
    assert second["evidence_quote"] == "서로 기대치 차이 같아요"
    assert "- (댓글) 서로 기대치 차이 같아요" in user_prompts(llm)[2]
    # 2026-11-18 지시서: 앞 초안 본문은 보여 주지 않고, 짚은 구절만 피하라고 알린다
    assert GOOD_BODY not in user_prompts(llm)[2]
    assert f"- 이미 짚은 구절: {Q_COMMENT} — 이 장면은 피한다" in user_prompts(llm)[2]
    assert second["passed"] is True and second["tone_label"].endswith(" / 혼잣말형")
    # 직전 초안과 다른 말 높임·들은 경로
    assert first["tone_label"].split(" / ")[:2] != second["tone_label"].split(" / ")[:2]

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
        "[광고] 하루에 한 번 연락 때문에 다툰 적 있다는 댓글에 공감했어요. "
        "요즘 운명원 연애 사주 잘 본다고 하던데 저도 한번 상담받아보고 싶네요."
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
                          json={"body": made["body"].replace("가 보려고요", "가 볼까 해요")}).json()
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
