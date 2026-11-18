"""댓글 생성·검수 흐름(2026-11-18 대표 최종 지시서, docs/COMMENT_REFACTOR.md 6절) — 가짜 YouTube·AI.

- 코드가 말 높임·들은 경로를 뽑아 시스템 글에 하나씩만 넣는다. AI는 mood·body·wish·used_quote.
- `tone_label` = "말 높임 / 들은 경로 / 기분", `wish`와 AI가 본 근거는 `review_json`에 함께.
- 규칙 검사에 걸리면 걸린 사유와 앞 본문으로 **같은 말 높임·들은 경로**로 다시 쓴다
  (다시 쓰기 2번까지).
- [다른 댓글 만들기]: 직전 초안과 다른 조합, 이미 짚은 구절과 앞 댓글의 wish를 요청 글에.
- [짚을 내용]: 자막 → 제목·설명 → 인기 댓글. 근거가 댓글일 때만 시스템 글에 댓글 줄.
- AI 검수: 세 가지 판정 + 갈래. 거짓이면 같은 말 높임·들은 경로로 한 번 다시 쓴다.
"""

import random

import pytest
from test_drafts_api import (
    ANALYSIS,
    GOOD_BODY,
    GOOD_BODY_2,
    MANY_FAILS,
    Q_COMMENT,
    TRANSCRIPT,
    VID,
    add_youtube,
)

from app.analysis import drafter as D
from app.analysis.analyzer import Evidence
from app.llm import prompts as P

WISH = "이 사람이랑 계속 가도 될지"


def answer(body, *, mood="답답", wish=WISH, quote=Q_COMMENT):
    return {"mood": mood, "body": body, "wish": wish, "used_quote": quote}


def ok(kind="잘 맞는 사람"):
    return {"ok": True, "problems": [], "wish_kind": kind}


def bad(problem="알고 싶은 것이 고민과 다름"):
    return {"ok": False, "problems": [problem], "wish_kind": "기타"}


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm):
    client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key)
    services = client.app.state.services.get()
    services.drafts.rng = random.Random(7)

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        services.llm = llm
        return llm

    return client, services, use


def create(client, **kw):
    res = client.post("/api/drafts", json={"video_id": VID, **kw})
    assert res.status_code == 200, res.text
    return res.json()


def picked(system: str) -> tuple[str, str]:
    voice = next(v for v in P.VOICES if f"[말]\n- {v}로 쓴다." in system)  # 2026-11-18 새 틀
    heard = next(h for h in P.HEARD_FROM if f"- 너는 {h} 「" in system)  # 9회차
    return voice, heard


def test_first_draft_stores_voice_heard_mood_wish_and_kind(setup):
    client, services, use = setup
    llm = use([ANALYSIS, answer(GOOD_BODY), ok("궁합")])
    data = create(client)
    system = llm.calls[1]["kwargs"]["system"]
    voice, heard = picked(system)
    assert data["tone_label"] == f"{voice} / {heard} / 답답"
    assert data["evidence_quote"] == Q_COMMENT and data["evidence_source"] == "comment"
    assert data["review"]["status"] == "passed" and data["passed"] and data["attempts"] == 1
    stored = services.drafts.get(data["id"])
    assert stored.wish == WISH and stored.review["wish_kind"] == "궁합"
    assert stored.review["basis"] == {"quote": Q_COMMENT, "source": "comment"}
    # 스키마와 온도는 댓글 것, 후보 목록은 프롬프트에 하나씩만
    assert llm.calls[1]["kwargs"]["schema"] == P.DRAFT_SCHEMA
    assert sum(v in system for v in P.VOICES) == 1
    assert sum(h in system for h in P.HEARD_FROM) == 1


def test_comment_basis_adds_the_comment_line(setup):
    """VID의 근거는 모두 인기 댓글이다(자막이 없음) → 댓글 줄이 들어간다."""
    client, _, use = setup
    llm = use([ANALYSIS, answer(GOOD_BODY)])
    create(client)
    system, user = llm.calls[1]["kwargs"]["system"], llm.calls[1]["kwargs"]["user"]
    assert P.COMMENT_LINE in system
    assert f"[짚을 내용]\n- (댓글) {Q_COMMENT}" in user
    assert ANALYSIS["concern"] in user
    for word in ("[광고]", "예시", "이미 쓴"):
        assert word not in system + user, word


def test_transcript_basis_comes_first_and_has_no_comment_line(setup):
    client, _, use = setup
    assert client.put(f"/api/videos/{VID}/transcript", json={"text": TRANSCRIPT}).status_code == 200
    quote = "주말마다 기차를 타고 내려가는 게 점점 지쳐요"
    analysis = dict(ANALYSIS, evidence=[*ANALYSIS["evidence"],
                                        {"quote": quote, "source": "transcript"}])
    body = ("주말마다 기차 타고 내려가는 게 지친다는 말 너무 알 것 같아요. 운명원이 연애 사주 잘 "
            "본다던데 저도 이 사람이랑 계속 갈지 보러 가려고요.")
    llm = use([analysis, answer(body, quote=quote)])
    data = create(client)
    system, user = llm.calls[1]["kwargs"]["system"], llm.calls[1]["kwargs"]["user"]
    assert f"- (자막) {quote}" in user and "- 자막 앞부분: " in user
    assert P.COMMENT_LINE not in system
    assert data["evidence_source"] == "transcript"


def test_rule_failure_rewrites_with_the_same_voice_and_reasons(setup):
    client, _, use = setup
    llm = use([ANALYSIS, answer(MANY_FAILS), answer(GOOD_BODY)])
    data = create(client)
    assert data["passed"] and data["attempts"] == 2 and data["first_passed"] is False
    first, second = llm.calls[1]["kwargs"], llm.calls[2]["kwargs"]
    assert first["system"] == second["system"]  # 같은 말 높임·들은 경로
    assert f"- 앞의 본문: {MANY_FAILS}" in second["user"]
    assert "- 걸린 까닭: V2" in second["user"]


def test_three_failures_keep_the_least_bad(setup):
    client, _, use = setup
    one_fail = GOOD_BODY.replace("운명원 ", "")  # V5만 걸린다
    llm = use([ANALYSIS, answer(MANY_FAILS), answer(one_fail), answer(MANY_FAILS)])
    data = create(client)
    assert llm.remaining == 0 and data["attempts"] == 3 and not data["passed"]
    assert data["body"].endswith(one_fail)
    assert [c["code"] for c in data["validation"]["checks"] if not c["passed"]] == ["V5"]
    assert data["review"]["status"] == ""  # 걸린 초안은 검수하지 않는다


def test_another_comment_changes_the_combo_and_names_quote_and_wish(setup):
    client, services, use = setup
    other_quote = "서로 기대치 차이 같아요"
    llm = use([ANALYSIS, answer(GOOD_BODY), ok(),
               answer(GOOD_BODY_2, wish="연락 문제가 반복되는 이유", quote=other_quote), ok()])
    first = create(client)
    second = create(client, another=True)
    assert first["tone_label"].split(" / ")[:2] != second["tone_label"].split(" / ")[:2]
    user = llm.calls[2]["kwargs"]["user"]
    assert f"- 이미 짚은 구절: {Q_COMMENT} — 이 장면은 피한다" in user
    assert f"- 앞 댓글이 알고 싶어 한 것: {WISH}" in user
    assert GOOD_BODY not in user  # 앞 댓글 본문은 보여 주지 않는다
    assert f"- (댓글) {other_quote}" in user  # 짚지 않은 근거부터
    assert second["evidence_quote"] == other_quote


def test_review_false_rewrites_once_with_the_same_voice(setup):
    client, services, use = setup
    rewrite = GOOD_BODY.replace("언제 한번 가 보려고요", "이 사람이랑 계속 갈지 보러 가려고요")
    llm = use([ANALYSIS, answer(GOOD_BODY), bad(),
               answer(rewrite, mood="씁쓸", wish="계속 갈지"), ok("잘 맞는 사람")])
    data = create(client)
    assert data["review"]["status"] == "rewritten" and data["body"].endswith(rewrite)
    assert data["attempts"] == 2
    assert llm.calls[1]["kwargs"]["system"] == llm.calls[2]["kwargs"]["system"]
    retry = llm.calls[2]["kwargs"]["user"]
    assert "- 걸린 까닭: AI 검수: 알고 싶은 것이 고민과 다름" in retry
    assert f"- 앞의 본문: {GOOD_BODY}" in retry
    stored = services.drafts.get(data["id"])
    assert stored.tone_label.endswith(" / 씁쓸") and stored.wish == "계속 갈지"
    assert stored.review["wish_kind"] == "잘 맞는 사람" and stored.review["first"]
    # 검수 AI는 쓰는 AI와 같은 [짚을 내용]을 본다
    review_user = llm.review_calls[0]["kwargs"]["user"]
    assert f"[짚을 내용]\n- (댓글) {Q_COMMENT}" in review_user


def test_review_rewrite_that_breaks_the_rules_keeps_the_first(setup):
    client, _, use = setup
    llm = use([ANALYSIS, answer(GOOD_BODY), bad(), answer(MANY_FAILS)])
    data = create(client)
    assert data["review"]["status"] == "flagged" and data["body"].endswith(GOOD_BODY)
    assert data["review"]["problems"] == ["알고 싶은 것이 고민과 다름"]
    assert data["passed"] and llm.remaining == 0


def test_review_error_leaves_the_draft(setup):
    """모양이 틀린 검수 답(ok가 참/거짓이 아님)은 「검수 못 함」 — 초안은 그대로."""
    client, services, use = setup
    llm = use([ANALYSIS, answer(GOOD_BODY), {"ok": "몰라"}])
    data = create(client)
    assert data["review"]["status"] == "error" and data["review"]["label"] == "AI 검수 못 함"
    assert data["body"].endswith(GOOD_BODY) and data["passed"]
    assert services.drafts.get(data["id"]).wish == WISH  # wish는 그대로
    assert llm.remaining == 0


def test_ai_review_off(setup):
    client, services, use = setup
    services.drafts.ai_review = False
    llm = use([ANALYSIS, answer(GOOD_BODY)])
    data = create(client)
    assert data["review"]["status"] == "off" and llm.review_calls == []


# ---------------------------------------------------------------- 코드가 고르는 것(단위)


def test_pick_voice_avoids_the_last_combo():
    rng = random.Random(1)
    last = D.Voice(P.VOICES[0], P.HEARD_FROM[0])
    assert all(D.pick_voice(rng, avoid=last) != last for _ in range(50))
    seen = {D.pick_voice(rng) for _ in range(200)}
    assert len(seen) == len(P.VOICES) * len(P.HEARD_FROM)


def test_voice_label_round_trip_and_old_labels():
    v = D.Voice("존댓말", "요즘 자주 들어서")
    assert v.label("설렘") == "존댓말 / 요즘 자주 들어서 / 설렘"
    assert D.voice_of(v.label("설렘")) == v and D.mood_of(v.label("설렘")) == "설렘"
    assert D.voice_of("공감형") is None and D.mood_of("공감형") == ""


def test_pick_evidence_order_transcript_then_title_description_then_comment():
    ev = [Evidence("댓글 구절입니다", "comment"), Evidence("설명 구절입니다", "description"),
          Evidence("제목 구절입니다", "title")]
    assert D.pick_evidence(ev).source == "title"
    assert D.pick_evidence(ev, ["제목 구절입니다"]).source == "description"
    assert D.pick_evidence([*ev, Evidence("자막 구절입니다", "transcript")]).source == "transcript"
    assert D.pick_evidence([ev[0]]).source == "comment"
    # 무리 안이 다 짚은 구절이면 그 무리의 첫 것(댓글로 내려가지 않는다)
    assert D.pick_evidence(ev[1:], ["제목 구절입니다", "설명 구절입니다"]).source == "title"


# ------------------------------------------------ 2026-11-18 운명원 말하기를 영상마다 다르게


def test_pick_voice_alternates_with_other_videos():
    """다른 영상 직전 초안과 말 높임은 번갈아, 들은 경로는 최근 두 개와 다르게(2026-11-18)."""
    rng = random.Random(3)
    recent = [D.Voice(P.VOICES[0], P.HEARD_FROM[0]), D.Voice(P.VOICES[1], P.HEARD_FROM[1])]
    for _ in range(50):
        v = D.pick_voice(rng, recent=recent)
        assert v.voice != P.VOICES[0] and v.heard == P.HEARD_FROM[2]
    # 같은 영상 직전 조합까지 피해야 해서 남는 게 없으면 조건을 푼다
    only = D.Voice(P.VOICES[1], P.HEARD_FROM[2])
    assert all(D.pick_voice(rng, avoid=only, recent=recent) != only for _ in range(30))


def test_user_text_carries_recent_comments_on_other_videos():
    user = P.draft_user(title="t", concern="c", material=["- (자막) q"],
                        recent_bodies=["요즘 운명원이 연애 사주 잘 본다던데 가봐야지", ""])
    assert ("[다른 영상에 최근 단 댓글]\n- 요즘 운명원이 연애 사주 잘 본다던데 가봐야지\n"
            "- 이 댓글들과 처지(네 연애가 어떤지)·궁금증·운명원 얘기·끝말이 겹치지 않게, "
            "다른 걸로 쓴다.") in user
    # 9회차: 요청 글 끝 쪽(답하라는 말 바로 위)에 둔다
    assert user.index("[다른 영상에 최근 단 댓글]") > user.index("[짚을 내용]")
    assert "[다른 영상에 최근 단 댓글]" not in P.draft_user(
        title="t", concern="c", material=["- (자막) q"])


def test_pick_saying_avoids_what_other_videos_just_used():
    """들은 말의 요지(핫하다 / 잘 본다 / 유명하다 / 연애 사주 하면 운명원)는 다른 영상 최근 두
    댓글과 다르게."""
    rng = random.Random(5)
    recent = ["운명원이 연애 사주로 유명하단 얘길 들어서 가봐야지",
              "운명원 연애 사주 잘 본다던데 가봐야겠어요"]
    assert [D.saying_of(b, "운명원") for b in recent] == [2, 1]
    assert D.saying_of("연애 사주 하면 운명원이라고들 하던데", "운명원") == 3
    assert D.saying_of("연애 사주는 운명원이라던데", "운명원") == 3  # 12회차 소넷
    assert D.saying_of("요새 운명원이 연애 사주 잘 보는 걸로 핫하던데", "운명원") == 0
    assert D.saying_of("그냥 가봐야지", "운명원") is None
    for _ in range(30):
        assert D.pick_saying(rng, "운명원", recent) in {
            "운명원이 연애 사주 잘 보는 걸로 핫하다", "연애 사주 하면 운명원이다"}
    every = recent + ["연애 사주 하면 운명원이라던데"]
    assert D.pick_saying(rng, "운명원", every[1:] + every[:1]) in {
        s.format(brand="운명원") for s, _ in P.SAYINGS}


def test_system_carries_the_picked_saying():
    text = P.draft_system(brand="운명원", facts=["운명원은 연애 사주를 잘 봐주는 곳으로 유명하다"],
                          voice="존댓말", heard="요즘 자주 들어서", from_comment=False,
                          said="연애 사주 하면 운명원이다")
    assert ("- 너는 요즘 자주 들어서 「연애 사주 하면 운명원이다」는 걸 알게 됐고, "
            "아직 가 본 적은 없다.") in text
    assert ("- 요즘 자주 들어서 알게 된 그 얘기(「연애 사주 하면 운명원이다」). "
            "그 뜻 그대로") in text
    assert "누가 말해 줬는지(친구·지인)는 쓰지 않는다." in text
    # 9회차: 소개 문장(잘 봐주는 곳으로 유명하다)이 요지를 덮었다 → 들은 말이 있으면 넣지 않는다
    assert "[운명원]\n- 연애 사주를 보는 곳이다.\n" in text
    assert "잘 봐주는 곳으로 유명하다" not in text
    others = [s.format(brand="운명원") for s, _ in P.SAYINGS if not s.startswith("연애 사주 하면")]
    assert not any(o in text for o in others)


def test_user_text_lists_situations_used_on_other_videos():
    """12회차: 본문 셋만 보여 주면 처지가 겹쳤다(11개 중 「흐지부지」 4) → 이미 쓴 처지를 짧게."""
    user = P.draft_user(title="t", concern="c", material=["- (자막) q"],
                        recent_bodies=["요즘 운명원이 연애 사주 잘 본다던데 가봐야지"],
                        recent_situations=["썸만 타다 흐지부지됨", "", "늘 기다리는 쪽"])
    assert "- 다른 영상 댓글에 이미 쓴 처지: 썸만 타다 흐지부지됨 / 늘 기다리는 쪽\n" in user
    assert "이미 쓴 처지와 같은 낱말(예: 흐지부지)도 쓰지 않는다." in user
    assert "이미 쓴 처지" not in P.draft_user(
        title="t", concern="c", material=["- (자막) q"], recent_bodies=["가봐야지"])


def test_situation_of_reads_the_saved_situation():
    assert D.situation_of('{"situation": "늘 기다리는 쪽", "wish": "w"}') == "늘 기다리는 쪽"
    assert D.situation_of('{"wish": "w"}') == ""
    assert D.situation_of(None) == "" and D.situation_of("깨진") == ""
    assert "situation" in P.DRAFT_SCHEMA["properties"]
    assert "situation" not in P.DRAFT_SCHEMA["required"]  # 없으면 빈 글로(가짜 답·옛 답)
