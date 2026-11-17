"""C1 댓글 말투(대표 지시 2026-11-17) — 가짜 YouTube, 가짜 LLM.

- 분석: 고민 한 줄이 요약 꼴이면 한 번 더 시킨다. 핵심 말은 자료와 대조해 거르고 저장한다.
- 예전(C1 전) 분석: 화면은 제목·해시태그에서 뽑은 핵심 말을 보여 주고, 초안을 만들 때는
  다시 분석한다.
- 초안: 핵심 말·말투 선택지·운명원 꺼내는 말이 프롬프트에 들어가고, 검사는 핵심 말로 V7을 본다.
- 사람이 고친 글·직접 쓰는 검사(POST /api/validate)도 같은 근거·핵심 말로 검사한다.
"""

import json

import pytest
from test_drafts_api import (
    ANALYSIS,
    GOOD_BODY,
    GOOD_BODY_2,
    KEYS,
    OTHER,
    OTHER_BODY,
    VID,
    add_youtube,
    draft,
)

from app import db


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm):
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


def failed(validation):
    return [c["code"] for c in validation["checks"] if not c["passed"]]


SUMMARY = dict(ANALYSIS, concern="장거리 커플의 연락 문제 해결 방법")


# ---------------------------------------------------------------- 분석


def test_key_phrases_are_checked_against_the_material_and_stored(setup):
    client, services, use = setup
    use([ANALYSIS])
    data = client.post(f"/api/analysis/{VID}").json()
    # 브랜드·흔한 말·자료에 없는 말은 버린다
    assert data["key_phrases"] == KEYS
    with db.session(services.drafts.db_path) as conn:
        row = conn.execute("SELECT key_phrases_json, key_phrases_source FROM analyses "
                           "WHERE video_id = ?", (VID,)).fetchone()
    assert json.loads(row["key_phrases_json"]) == KEYS and row["key_phrases_source"] == "model"
    assert client.get(f"/api/analysis/{VID}").json()["key_phrases"] == KEYS


def test_summary_shaped_concern_is_asked_again(setup):
    client, _, use = setup
    llm = use([SUMMARY, ANALYSIS])
    data = client.post(f"/api/analysis/{VID}").json()
    assert data["concern"] == ANALYSIS["concern"] and len(llm.calls) == 2
    retry = user_prompts(llm)[1]
    assert "[다시 요청]" in retry
    assert f"고민 한 줄 '{SUMMARY['concern']}'이 영상 요약입니다" in retry
    assert "근거 구절이 영상 자료에 그대로 있지 않아" not in retry  # 근거는 괜찮았다


def test_summary_concern_twice_keeps_the_answer_instead_of_stopping(setup):
    # 고민 꼴만 틀리면 멈추지 않는다(근거가 있으니 초안은 만들 수 있다)
    client, _, use = setup
    llm = use([SUMMARY, SUMMARY])
    res = client.post(f"/api/analysis/{VID}")
    assert res.status_code == 200 and res.json()["concern"] == SUMMARY["concern"]
    assert len(llm.calls) == 2


def test_all_key_phrases_dropped_asks_again_then_falls_back_to_the_title(setup):
    client, services, use = setup
    junk = dict(ANALYSIS, key_phrases=["연애", "손편지"])
    llm = use([junk, junk])
    data = client.post(f"/api/analysis/{VID}").json()
    assert len(llm.calls) == 2
    assert "핵심 말이 영상 자료에 그대로 없거나 너무 흔한 말이라" in user_prompts(llm)[1]
    # 두 번 다 없으면 제목·해시태그에서 코드가 뽑는다(그러면 V7은 넉넉하게 본다)
    assert data["key_phrases"] and "장거리" in data["key_phrases"]
    analysis = services.drafts.stored_analysis(VID)
    assert analysis.key_phrases_derived and analysis.checked_phrases is None


# ---------------------------------------------------------------- 예전 분석


def _make_legacy(services):
    """C1 전에 저장된 분석처럼 핵심 말 칸을 비운다."""
    with db.session(services.drafts.db_path) as conn:
        conn.execute("UPDATE analyses SET key_phrases_json = '[]', key_phrases_source = '' "
                     "WHERE video_id = ?", (VID,))


def test_legacy_analysis_is_shown_with_title_phrases_and_redone_for_drafts(setup):
    client, services, use = setup
    use([ANALYSIS])
    client.post(f"/api/analysis/{VID}")
    _make_legacy(services)
    shown = client.get(f"/api/analysis/{VID}").json()
    assert shown["concern"] == ANALYSIS["concern"]
    assert "장거리" in shown["key_phrases"]  # 제목에서 뽑았다
    # 검사는 예전 분석으로도 깨지지 않는다
    check = client.post("/api/validate", json={"video_id": VID, "text": f"[광고] {GOOD_BODY}"})
    assert check.status_code == 200 and check.json()["passed"] is True
    # 초안을 만들 때는 다시 분석한다(분석 1 + 초안 1)
    llm = use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    assert made["passed"] is True and len(llm.calls) == 2
    assert "[영상 자료 시작]" in user_prompts(llm)[0]
    assert services.drafts.stored_analysis(VID).legacy is False


# ---------------------------------------------------------------- 초안


def test_draft_prompt_carries_key_phrases_tones_and_hearsay(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY)])
    client.post("/api/drafts", json={"video_id": VID})
    user = user_prompts(llm)[1]
    assert "[핵심 말] '장거리', '하루에 한 번 연락', '기대치 차이'" in user
    assert "[말투] 이번 말투는 다음 중" in user
    assert "운명원을 꺼내는 말은 이번에 이런 식으로" in user
    assert "바람의 끝말은 이번에 이런 식으로" in user
    assert "과제가 보여 준 예시 댓글" in llm.calls[1]["kwargs"]["system"]


def test_draft_without_any_key_phrase_fails_v7_and_is_rewritten(setup):
    client, _, use = setup
    plain = ("연락 문제로 다투는 얘기 남 일 같지 않네요ㅠㅠ "
             "요즘 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요.")
    llm = use([ANALYSIS, draft(plain), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 2 and data["passed"] is True
    assert "V7 영상의 핵심 말을 담음" in user_prompts(llm)[2]


def test_long_copy_fails_v13_and_is_rewritten(setup):
    client, _, use = setup
    copy = ("저도 하루에 한 번 연락으로 싸운 적 있어요 정말 공감돼요. "
            "요즘 운명원 연애 사주 잘 본다던데 저도 가 보려고요.")
    llm = use([ANALYSIS, draft(copy), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 2 and data["passed"] is True
    retry = user_prompts(llm)[2]
    assert "V13 영상 글을 길게 베끼지 않음" in retry and "그대로 옮겼습니다" in retry


def test_abrupt_brand_fails_v14_and_is_rewritten(setup):
    # 대표가 본 초안(2026-11-17)과 같은 꼴: 고민 뒤에 곧바로 운명원
    client, _, use = setup
    abrupt = ("하루에 한 번 연락 얘기가 제 고민 같아 눈길이 가네요. 연락 문제를 어디서부터 풀지 "
              "막막한데 운명원에서 연애 사주를 한번 보고 싶어요.")
    llm = use([ANALYSIS, draft(abrupt), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 2 and data["passed"] is True
    retry = user_prompts(llm)[2]
    # 2026-11-17 다섯 조각: 빠진 조각(때·잘 본다는 들은 얘기)을 이름으로 알린다
    assert "V14 브랜드 대목 다섯 조각" in retry and "'요즘/요새'가 없습니다" in retry
    assert "잘 본다는 평판(~다고 하던데)이 없습니다" in retry
    # 사람이 고쳐 써도 같은 검사를 거친다
    edited = client.patch(f"/api/drafts/{data['id']}", json={"body": f"[광고] {abrupt}"}).json()
    assert failed(edited["validation"]) == ["V14"]


def test_next_video_cannot_reuse_the_last_approved_tone(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY, tone="한탄형"), ANALYSIS,
               draft(OTHER_BODY, tone="유쾌형")])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    assert first["tone_label"] == "한탄형"
    assert client.post(f"/api/drafts/{first['id']}/approve").status_code == 200
    other = client.post("/api/drafts", json={"video_id": OTHER}).json()
    assert other["passed"] is True and other["tone_label"] == "유쾌형"
    enum = llm.calls[3]["kwargs"]["schema"]["properties"]["tone_label"]["enum"]
    assert "한탄형" not in enum and len(enum) == 3
    # 앞 영상에서 쓴 운명원 꺼내는 말의 조각(잘 본다 · 고 하던데)은 이번 권유에서 뒤로 밀린다
    line = next(x for x in user_prompts(llm)[3].splitlines() if "꺼내는 말은" in x)
    assert "잘 본다고 하던데" not in line
    assert "이미 쓴 첫 반응(다른 영상에 승인됨)" in user_prompts(llm)[3]


def test_first_draft_asks_for_a_reason_and_the_next_may_skip_it(setup):
    # 2026-11-18(기획 담당): 같은 영상 초안 가운데 적어도 하나는 ⑤에 이 영상 고민에서 온 까닭
    client, _, use = setup
    reasoned = ("하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요ㅠㅠ 요즘 운명원 연애 "
                "사주 잘 본다고 하던데 저도 연락 문제로 언제 한번 가 보려고요.")
    llm = use([ANALYSIS, draft(reasoned), draft(GOOD_BODY_2)])
    first = client.post("/api/drafts", json={"video_id": VID}).json()
    assert first["passed"] is True
    ask = user_prompts(llm)[1]
    assert "이번 끝말에는 '저도' 뒤, 가 보겠다는 말 앞에 이 영상의 고민에서 온 짧은 까닭" in ask
    assert f"고민 한 줄('{ANALYSIS['concern']}')을 쉬운 내 말로 줄여서" in ask
    second = client.post("/api/drafts", json={"video_id": VID}).json()
    assert second["passed"] is True
    free = user_prompts(llm)[2]
    assert "이번 끝말은 까닭 없이 본보기 꼴" in free and "이번 끝말에는" not in free


# ---------------------------------------------------------------- 사람이 고친 글 · 직접 검사


def test_human_edit_is_checked_with_the_same_basis(setup):
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY)])
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    # 한 글자 고쳐도 근거(V6)가 그대로 살아 있다
    small = client.patch(f"/api/drafts/{made['id']}",
                         json={"body": made["body"].replace("가 보려고요", "가 보려고")}).json()
    assert small["passed"] is True, failed(small["validation"])
    assert small["evidence_quote"] == made["evidence_quote"]
    # 핵심 말을 빼면 V7, 영상 글을 길게 옮기면 V13
    no_key = client.patch(f"/api/drafts/{made['id']}", json={
        "body": "[광고] 연락 때문에 다툰 얘기 남 일 같지 않네요. 요즘 운명원 연애 사주 잘 "
                "본다던데 저도 한번 가 보려고요."
    }).json()
    assert failed(no_key["validation"]) == ["V7"]
    copied = client.patch(f"/api/drafts/{made['id']}", json={
        "body": "[광고] 저도 하루에 한 번 연락으로 싸운 적 있어요. 요즘 운명원 연애 사주 잘 "
                "본다던데 저도 한번 가 보려고요."
    }).json()
    assert failed(copied["validation"]) == ["V13"]


def test_validate_api_uses_the_stored_key_phrases_and_concern(setup):
    client, _, use = setup
    use([ANALYSIS])
    client.post(f"/api/analysis/{VID}")

    def check(text):
        return client.post("/api/validate", json={"video_id": VID, "text": text}).json()

    good = check(f"[광고] {GOOD_BODY}")
    assert good["passed"] is True and good["total"] == 14
    v7 = next(c for c in good["checks"] if c["code"] == "V7")
    assert "'하루에 한 번 연락'" in v7["message"]
    # 고민 한 줄을 그대로 옮기면 V13
    concern = check(f"[광고] {ANALYSIS['concern']} 하루에 한 번 연락 문제예요. "
                    "요즘 운명원 연애 사주 잘 본다던데 저도 한번 가 보려고요.")
    v13 = next(c for c in concern["checks"] if c["code"] == "V13")
    assert v13["passed"] is False and "고민 한 줄" in v13["message"]
