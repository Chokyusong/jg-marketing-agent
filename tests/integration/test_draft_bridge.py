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


def test_same_video_mixes_a_bridged_draft_and_a_reason_only_draft(setup):
    # 2026-11-18(기획 담당 C): 같은 영상의 앞 초안이 잇는 문장을 넣었으면 이번 초안은 잇는
    # 문장 없이 까닭으로 잇는다(코드가 정한다). 넣으면 S16으로 한 번 다시 쓴다. 예전 이 시험은
    # 같은 영상 둘째 초안에도 잇는 문장을 넣게 하고 「거의 같은」 잇는 문장을 S12로 잡았다
    client, _, use = setup
    use([ANALYSIS, draft(BRIDGED)])
    client.post("/api/drafts", json={"video_id": VID})
    reason_only = ("기대치 차이라는 말이 계속 남네요. 요새 운명원이 연애사주를 꽤 잘 봐준다는 "
                   "얘기가 있던데, 저도 연락 문제로 조만간 상담받아보고 싶네요.")
    llm = use([draft(BRIDGED_2, tone="혼잣말형"), draft(reason_only, tone="혼잣말형")])
    data = client.post("/api/drafts", json={"video_id": VID, "another": True}).json()
    first = users(llm)[0]
    assert "이번 초안에는 **잇는 문장을 넣지 않는다**" in first
    assert "이번 끝말에는 '저도' 뒤, 가 보겠다는 말 앞에" in first  # 까닭은 꼭
    assert "S16 잇는 문장 빼기" in users(llm)[1]
    assert data["attempts"] == 2 and data["body"].endswith(reason_only)


def test_earlier_bridge_is_passed_as_used_and_only_the_same_sentence_is_rewritten(setup):
    # 다른 영상(앞서 보인 초안)의 잇는 문장은 「이미 쓴 잇는 문장」으로 넘기고, 통째로 같을 때만
    # S12로 다시 쓴다(낱말이 겹치는 것은 괜찮다, 2026-11-18 C)
    client, _, use = setup
    use([ANALYSIS, draft(BRIDGED)])
    client.post("/api/drafts", json={"video_id": VID})
    used = P.bridge_sentence(BRIDGED, "운명원")
    same = BRIDGED_2.replace("다 때가 있는 건가 봐요.", used)
    from app.analysis import style as S

    issues = S.style_issues(f"[광고] {same}", brand="운명원", disclosure="[광고]",
                            used_bridges=[used])
    assert any(i.startswith("S12 잇는 문장 되풀이") for i in issues)
    near = BRIDGED_2.replace("다 때가 있는 건가 봐요.", "결국 맞는 사람 문제인가 싶어요.")
    issues = S.style_issues(f"[광고] {near}", brand="운명원", disclosure="[광고]",
                            used_bridges=[used])
    assert not any(i.startswith("S12") for i in issues)


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


def test_ai_review_rewrite_keeps_whether_the_draft_had_a_bridge(setup):
    # 2026-11-18(C): AI 검수 뒤 다시 쓸 때도 같은 배정 — 잇는 문장이 있던 초안은 넣으라고,
    # 까닭만 있던 초안은 넣지 말라고
    _, services, use = setup
    reason_only = ("장거리면 하루에 한 번 연락도 서운하죠ㅠㅠ 최근 운명원 연애 사주가 잘 맞는다는 "
                   "얘기를 들었는데, 저도 연락 문제로 한번 가볼 생각이에요.")
    llm = use([ANALYSIS, draft(BRIDGED), {"ok": False, "problems": ["어색"]}, draft(BRIDGED_2),
               {"ok": True, "problems": []}])
    first = services.drafts.generate(VID, review=False)
    services.drafts.review(first.id)
    assert "**잇는 한 문장**" in users(llm)[2] and "넣지 않는다**" not in users(llm)[2]
    llm = use([draft(reason_only, tone="혼잣말형"), {"ok": False, "problems": ["어색"]},
               draft(reason_only.replace("최근", "요즘"), tone="혼잣말형"),
               {"ok": True, "problems": []}])
    second = services.drafts.generate(VID, review=False)
    assert second.attempts == 1, services.drafts.last_run["attempts"]
    services.drafts.review(second.id)
    assert "이번 초안에는 **잇는 문장을 넣지 않는다**" in users(llm)[1]
