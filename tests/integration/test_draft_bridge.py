"""② 잇는 한 문장이 초안 만들기에 들어가는지(2026-11-18) — 가짜 YouTube, 가짜 LLM.

- 프롬프트가 잇는 문장을 넣게 하고, 앞서 보인 초안의 잇는 문장을 「이미 쓴 잇는 문장」으로 넘긴다.
- 잇는 문장·까닭이 둘 다 없는 초안은 다듬기 검사 S11로 한 번 다시 쓰게 한다(승인은 막지 않는다).
- 좋은 예의 잇는 문장을 그대로 옮기면 S12로 다시 쓰게 한다.
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, add_youtube, draft

from app.llm import prompts as P

pytestmark = pytest.mark.usefixtures("bridge_check_on")

BRIDGED = (
    "하루에 한 번 연락 갖고 싸웠다니ㅠㅠ 결국 맞는 사람 문제인가 싶네요. "
    "요즘 운명원 연애 사주 잘 본다고 하던데 저도 언제 한번 가 보려고요."
)
BRIDGED_2 = (
    "기대치 차이라는 말이 계속 남네요. 다 때가 있는 건가 봐요. "
    "요새 운명원이 연애사주를 꽤 잘 봐준다는 얘기가 있던데, 저도 조만간 상담받아보고 싶네요."
)


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


def users(llm):
    return [c["kwargs"]["user"] for c in llm.calls]


def test_prompt_asks_for_a_bridge(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(BRIDGED)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["passed"] and data["attempts"] == 1
    assert "**잇는 한 문장**" in users(llm)[1]
    assert "② **잇는 한 문장**" in llm.calls[1]["kwargs"]["system"]


def test_draft_without_bridge_or_reason_is_rewritten_once_with_s11(setup):
    client, _, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), draft(BRIDGED)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["attempts"] == 2 and data["passed"]
    assert "결국 맞는 사람 문제인가" in data["body"]
    retry = users(llm)[2]
    assert "S11 잇는 문장 없음" in retry and f"앞의 본문: {GOOD_BODY}" in retry


def test_last_attempt_keeps_a_passing_draft_without_bridge(setup):
    # S11은 승인을 막지 않는다: 세 번 다 잇는 문장이 없으면 통과한 글을 그대로 둔다
    client, _, use = setup
    use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY), draft(GOOD_BODY)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert data["passed"] and data["attempts"] == 3
    approved = client.post(f"/api/drafts/{data['id']}/approve")
    assert approved.status_code == 200


def test_earlier_bridge_is_passed_as_used_and_repeating_it_is_rewritten(setup):
    client, _, use = setup
    use([ANALYSIS, draft(BRIDGED)])
    client.post("/api/drafts", json={"video_id": VID})
    same = BRIDGED_2.replace("다 때가 있는 건가 봐요.", "결국 맞는 사람 문제인가 싶어요.")
    llm = use([draft(same, tone="혼잣말형"), draft(BRIDGED_2, tone="혼잣말형")])
    data = client.post("/api/drafts", json={"video_id": VID, "another": True}).json()
    first = users(llm)[0]
    assert "이미 쓴 잇는 문장: '결국 맞는 사람 문제인가 싶네요.'" in first
    assert "S12 잇는 문장 되풀이" in users(llm)[1]
    assert data["attempts"] == 2 and "다 때가 있는 건가 봐요" in data["body"]


def test_copying_a_good_example_bridge_is_rewritten(setup):
    client, _, use = setup
    copied = BRIDGED.replace("결국 맞는 사람 문제인가 싶네요.", P.EXAMPLE_BRIDGES[1])
    llm = use([ANALYSIS, draft(copied), draft(BRIDGED)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    assert "S12 잇는 문장 되풀이" in users(llm)[2]
    assert data["body"].endswith(BRIDGED)


def test_human_edit_without_bridge_still_passes(setup):
    client, _, use = setup
    use([ANALYSIS, draft(BRIDGED)])
    data = client.post("/api/drafts", json={"video_id": VID}).json()
    edited = client.patch(f"/api/drafts/{data['id']}", json={"body": "[광고] " + GOOD_BODY}).json()
    assert edited["passed"]
