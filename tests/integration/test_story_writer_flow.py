"""이야기처럼 쓰기가 초안 만들기·다시 쓰기·맥락 일치 검증·설정·API에 이어지는가(2026-11-18).

- 설정 `comment.writer` 기본은 story. 설정 화면에서 pieces로 바꾸면 바로 조각 맞추기로 쓴다.
- 이야기 방식: 요청 글에 기승전결과 영상 자료만 준다(조각·잇는 문장·까닭·글쓴이 배정 없음).
  처지는 시스템 글의 예만 보고 AI가 정한다. 분석·초안·DB에 새 칸이 없다.
- 길이(V1)로 세 번 다 걸리면 여운 → 전 차례로 한 번씩 더 쓰게 한다.
- 맥락 일치 검증: 네 판단 중 하나라도 걸리면 그 까닭으로 한 번 다시 쓰고, 다시 쓴 글도 규칙 검사와
  검증을 거친다. 그래도 걸리면 「맥락 확인 필요」와 벗어난 문장을 화면에 보인다(게시는 막지 않음).
  검증 호출이 실패하면 「맥락 검증 못 함 — 직접 읽어 주세요」. 네 판단과 벗어난 문장은 초안마다
  `review_json`에 남는다.

가짜 YouTube, 가짜 LLM.
"""

from __future__ import annotations

import pytest
from test_drafts_api import ANALYSIS, VID, add_youtube, draft

from app.analysis import review as rv
from app.analysis.validator import ASSIGNMENT_SAMPLE
from app.errors import AppError, ErrorKind
from app.llm import story_prompts as SP

GOOD = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글에 마음이 쓰이네요. 저도 자주 부딪히는 편이라 결국 "
    "맞는 사람이 따로 있나 싶어요. 운명원이 연애사주 잘 본다길래 지금 사람이랑 오래 갈지 보러 "
    "가려구요"
)
GOOD2 = (
    "기대치 차이라는 말이 꼭 제 얘기 같아요ㅠ 저도 서운해도 꾹 참는 편이라 다 때가 있나 봐요. "
    "운명원 연애사주가 그렇게 잘 맞는다던데 지금 사람이랑 맞는지 한번 보러 가 볼까 해요"
)
TOO_LONG = GOOD + (" 진짜 다들 각자 정해진 인연이 따로 있는 것 같아서 마음이 조금 놓이기도 "
                   "하고요 정말")
CLEAN = {"same_topic": True, "comment_topic": "연락 문제", "one_voice": True, "drift": "",
         "natural_ad": True, "ok": True, "problems": []}
DRIFT = {**CLEAN, "one_voice": False, "drift": "저도 자주 부딪히는 편이라"}


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, story_writer):
    def build(overrides=None):
        client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key,
                             overrides=overrides)
        services = client.app.state.services.get()

        def use(responses):
            llm = fake_llm(responses)
            llm.model = "fake-model"
            services.llm = llm
            return llm

        return client, services, use

    return build


def users(llm):
    return [c["kwargs"]["user"] for c in llm.calls]


def test_story_is_the_default_and_assigns_no_writer(setup):
    client, services, use = setup()
    assert services.drafts.writer == "story" and services.drafts.is_story
    llm = use([ANALYSIS, draft(GOOD)])
    d = services.drafts.generate(VID)
    assert d.passed, d.validation.failure_lines()
    user = users(llm)[1]
    assert "[글쓴이]" not in user
    assert "이번 초안의 운명원 대목" not in user and "잇는 한 문장" not in user
    system = llm.calls[1]["kwargs"]["system"]
    assert "기승전결" in system and ASSIGNMENT_SAMPLE in system
    assert user.startswith("[영상 자료]")  # 자막·제목·설명·인기 댓글을 직접 읽는다
    assert "writer" not in services.drafts.last_run
    assert not hasattr(services.drafts.stored_analysis(VID), "topic_group")
    # 맥락 일치 검증으로 묻는다(네 판단의 스키마·영상 주제)
    review = llm.review_calls[0]["kwargs"]
    assert "same_topic" in review["system"] and review["schema"] is rv.STORY_REVIEW_SCHEMA
    assert "[영상 주제]" in review["user"]
    # API·화면: 통과 줄은 「맥락 검증 통과 · 영상 주제와 일치」, 글쓴이 칸은 없다
    got = client.get("/api/drafts", params={"video_id": VID})
    assert got.status_code == 200, got.text
    item = got.json()["items"][0]
    assert "writer" not in item
    assert item["review"]["label"] == "맥락 검증 통과 · 영상 주제와 일치"
    assert item["review"]["story"] is True


def test_context_checks_are_recorded_per_draft(setup):
    _, services, use = setup()
    use([ANALYSIS, draft(GOOD), CLEAN])
    d = services.drafts.generate(VID)
    assert d.review_status == rv.PASSED
    assert d.review["story"] is True and d.review["checks"]["comment_topic"] == "연락 문제"
    assert d.review["drift"] == ""
    assert set(d.review["checks"]) >= {"same_topic", "one_voice", "drift", "natural_ad"}


def test_brand_in_first_sentence_is_written_again(setup):
    _, services, use = setup()
    bad = ("운명원이 연애사주 잘 본다던데 하루에 한 번 연락 갖고 싸웠다는 댓글 보니 저도 지금 "
           "사람이랑 맞는지 보러 가려구요")
    llm = use([ANALYSIS, draft(bad), draft(GOOD)])
    d = services.drafts.generate(VID, review=False)
    assert d.passed and d.attempts == 2
    assert "첫 문장" in users(llm)[2] and "걸린 항목을 고쳐" in users(llm)[2]


def test_three_long_drafts_drop_the_coda_then_the_turn(setup):
    _, services, use = setup()
    llm = use([ANALYSIS, draft(TOO_LONG), draft(TOO_LONG), draft(TOO_LONG),
               draft(TOO_LONG), draft(GOOD)])
    d = services.drafts.generate(VID, review=False)
    asked = users(llm)[1:]
    assert len(asked) == 5 and d.passed and d.attempts == 5
    assert SP.DROP_LINES[1] not in asked[2] and SP.DROP_LINES[1] in asked[3]
    assert SP.DROP_LINES[2] in asked[4]
    drops = [a.get("drop", 0) for a in services.drafts.last_run["attempts"]]
    assert drops == [0, 0, 0, 1, 2]


def test_long_then_other_failure_does_not_add_more_tries(setup):
    _, services, use = setup()
    llm = use([ANALYSIS, draft(TOO_LONG), draft(GOOD), draft(GOOD)])
    services.drafts.generate(VID, review=False)
    assert len(llm.calls) <= 3 + 1  # 분석 + 최대 세 번(길이가 모두는 아님)


def test_context_drift_rewrites_once_then_passes(setup):
    _, services, use = setup()
    llm = use([ANALYSIS, draft(GOOD), DRIFT, draft(GOOD2), CLEAN])
    d = services.drafts.generate(VID)
    assert d.review_status == rv.REWRITTEN and d.body.endswith(GOOD2)
    retry = users(llm)[-1]
    assert "맥락 검증: 벗어난 문장: 「저도 자주 부딪히는 편이라」" in retry
    assert "맥락 검증: 한 사람의 목소리가 아님" in retry
    assert d.review["first_checks"]["one_voice"] is False and d.review["checks"]["one_voice"]
    # 다시 쓴 글도 맥락 일치 검증을 한 번 더 받았다
    assert len(llm.review_calls) == 2


def test_still_drifting_shows_the_sentence_and_does_not_block(setup):
    client, services, use = setup()
    still = {**CLEAN, "same_topic": False, "comment_topic": "결혼운",
             "drift": "결혼운도 보러 가 볼까 해요"}
    use([ANALYSIS, draft(GOOD), DRIFT, draft(GOOD2), still])
    d = services.drafts.generate(VID)
    assert d.review_status == rv.FLAGGED and d.passed  # 게시는 막지 않는다(규칙 검사 통과)
    assert d.review["drift"] == "결혼운도 보러 가 볼까 해요"
    item = client.get("/api/drafts", params={"video_id": VID}).json()["items"][0]
    review = item["review"]
    assert review["label"] == "맥락 확인 필요"
    assert review["problems"][0] == "벗어난 문장: 「결혼운도 보러 가 볼까 해요」"
    assert review["drift"] == "결혼운도 보러 가 볼까 해요"


def test_failed_context_check_says_read_it_yourself(setup):
    client, services, use = setup()
    use([ANALYSIS, draft(GOOD), {"ok": True, "raise": AppError(ErrorKind.LLM_TIMEOUT)}])
    d = services.drafts.generate(VID)
    assert d.review_status == rv.ERROR and d.passed
    item = client.get("/api/drafts", params={"video_id": VID}).json()["items"][0]
    assert item["review"]["label"] == "맥락 검증 못 함 — 직접 읽어 주세요"


def test_writer_setting_switches_to_pieces_right_away(setup):
    client, services, use = setup()
    edit = client.get("/api/settings").json()["edit"]
    assert edit["values"]["comment.writer"] == "story"
    assert [c["label"] for c in edit["writers"]] == ["이야기처럼(권장)", "조각 맞추기(예전)"]
    res = client.put("/api/settings", json={"values": {"comment.writer": "pieces"}})
    assert res.status_code == 200, res.text
    services = client.app.state.services.get()
    assert services.drafts.writer == "pieces" and not services.drafts.is_story
    bad = client.put("/api/settings", json={"values": {"comment.writer": "free"}})
    assert bad.status_code in (400, 422)


def test_pieces_mode_keeps_the_old_prompt_and_review(setup):
    client, services, use = setup({"comment": {"writer": "pieces"}})
    assert services.drafts.writer == "pieces"
    old = ("하루에 한 번 연락 갖고 싸웠다는 댓글에 공감해요. 요즘 운명원 연애 사주 잘 본다고 "
           "하던데 저도 언제 한번 가 보려고요.")
    llm = use([ANALYSIS, draft(old)])
    d = services.drafts.generate(VID)
    assert "기:" not in llm.calls[1]["kwargs"]["system"]
    assert llm.review_calls[0]["kwargs"]["schema"] is rv.REVIEW_SCHEMA
    assert "story" not in d.review
    item = client.get("/api/drafts", params={"video_id": VID}).json()["items"][0]
    assert item["review"]["label"] == "AI 검수 통과" and "story" not in item["review"]


def test_validate_api_uses_story_v14(setup):
    client, services, use = setup()
    no_time = "[광고] " + GOOD  # 때 말(요즘·요새)이 없다
    res = client.post("/api/validate", json={"video_id": VID, "text": no_time, "disclose": True})
    assert res.status_code == 200, res.text
    v14 = next(c for c in res.json()["checks"] if c["code"] == "V14")
    assert v14["passed"] is True
