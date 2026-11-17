"""AI 검수 「문제가 아닌 것」 흐름(2026-11-18 기획 담당 B) — 진짜 `review.ask`, 가짜 AI.

잇는 혼잣말(「결국 궁합의 문제도 있나 봐요」)과 「저도 + 영상 고민에서 온 까닭」, 운명원 대목
조각이 든 초안을 검수에 보내면, 검수 AI가 받는 글에 「문제가 아닌 것」 목록이 들어 있고 참으로
답하면 다시 쓰지 않는다(AI를 더 부르지 않는다). 분명한 문제로 거짓이면 지금처럼 한 번 다시 쓴다.
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, add_youtube, draft

from app.analysis import review as R

pytestmark = pytest.mark.real_review

BRIDGED = ("하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요. 결국 궁합의 문제도 있나 "
           "봐요. 요즘 운명원 연애 사주 잘 본다고 하던데 저도 연락 문제로 언제 한번 가 보려고요.")


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


def _review_calls(llm):
    return [c["kwargs"] for c in llm.calls if c["kwargs"].get("schema") == R.REVIEW_SCHEMA]


def test_bridge_and_reason_pass_review_without_a_rewrite(setup):
    _, services, use = setup
    llm = use([ANALYSIS, draft(BRIDGED), {"ok": True, "problems": []}])
    d = services.drafts.generate(VID, review=False)
    assert d.passed, d.validation.failure_lines()
    reviewed = services.drafts.review(d.id)
    assert reviewed.review_status == R.PASSED and reviewed.body == d.body
    (call,) = _review_calls(llm)
    assert "[문제가 아닌 것 — 이것 때문에 false로 답하지 않는다]" in call["system"]
    assert "(가) 잇는 혼잣말" in call["system"]
    assert "(나) '저도' + 영상 고민에서 온" in call["system"]
    assert "결국 궁합의 문제도 있나 봐요" in call["user"]  # 검수할 글
    assert len(llm.calls) == 3  # 분석 · 초안 · 검수 한 번(다시 쓰지 않았다)


def test_a_clear_problem_is_still_written_again_once(setup):
    _, services, use = setup
    llm = use([ANALYSIS, draft(BRIDGED),
               {"ok": False, "problems": ["'갖고 싸웠다는' 뒤 조사가 꼬였다"]},
               draft(GOOD_BODY), {"ok": True, "problems": []}])
    d = services.drafts.generate(VID, review=False)
    reviewed = services.drafts.review(d.id)
    assert reviewed.review_status == R.REWRITTEN
    assert reviewed.body == f"[광고] {GOOD_BODY}"
    assert len(_review_calls(llm)) == 2
