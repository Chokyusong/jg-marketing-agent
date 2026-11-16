"""내 채널 영상(`own_video_ids`)에서만 홍보 표기를 켜고 끌 수 있다 — 가짜 YouTube, 가짜 LLM.

- 표기를 끈 초안: 내 채널 영상이면 표기 없이 저장되고 V4를 통과한다(본문이 곧 전체 40~120자).
- 내 채널 영상이 아니면 표기를 끌 수 없다(`disclosure_required`, 초안을 만들지 않는다).
- 내 채널 영상이라도 표기를 켠 초안은 그대로 [광고]로 시작한다.
- 사람이 고친 글: 내 채널 영상은 표기를 지워도 V4 통과, 그 밖의 영상은 그대로 실패.
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, add_youtube, draft

from app.errors import AppError, ErrorKind

OWN = VID  # 이 시험에서는 이 영상을 내 채널 영상으로 등록한다
NOT_OWN = "AAAAAAAAAA1"


@pytest.fixture
def client(mock_http, fixture_json, fake_key, make_client):
    return make_client(
        add_youtube(mock_http(), fixture_json), key=fake_key, overrides={"own_video_ids": [OWN]}
    )


@pytest.fixture
def services(client, fake_llm):
    services = client.app.state.services.get()

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        services.llm = llm
        return llm

    services.use = use
    return services


def v4(validation):
    return next(c for c in validation.checks if c.code == "V4")


def test_own_video_draft_without_disclosure(services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(OWN, disclose=False)
    assert not d.body.startswith("[광고]")
    assert d.body == GOOD_BODY
    assert d.passed, d.validation.failure_lines()
    assert v4(d.validation).passed and "표기 끔" in v4(d.validation).message


def test_own_video_draft_with_disclosure_keeps_the_label(services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(OWN)
    assert d.body == f"[광고] {GOOD_BODY}"
    assert d.passed and v4(d.validation).message == "맨 앞이 [광고]"


def test_other_video_cannot_turn_disclosure_off(services):
    llm = services.use([ANALYSIS, draft(GOOD_BODY)])
    with pytest.raises(AppError) as exc:
        services.drafts.generate(NOT_OWN, disclose=False)
    assert exc.value.kind == ErrorKind.DISCLOSURE_REQUIRED
    assert llm.calls == []  # 모델을 부르지 않는다
    assert services.drafts.list(NOT_OWN) == []


def test_unlabelled_text_passes_v4_only_on_own_video(services):
    services.use([ANALYSIS])
    services.drafts.analyze(OWN)
    assert v4(services.drafts.checks.check(OWN, GOOD_BODY)).passed
    services.drafts.checks.own_video_ids = frozenset()
    assert not v4(services.drafts.checks.check(OWN, GOOD_BODY)).passed


def test_label_in_the_middle_still_fails_on_own_video(services):
    services.use([ANALYSIS])
    services.drafts.analyze(OWN)
    text = f"{GOOD_BODY} [광고]"
    assert not v4(services.drafts.checks.check(OWN, text)).passed


# ---------------------------------------------------------------- API·설정 화면


def test_context_says_whether_the_video_is_own(client, services):
    assert client.post(f"/api/videos/{OWN}/context").json()["own_video"] is True
    assert client.post(f"/api/videos/{NOT_OWN}/context").json()["own_video"] is False


def test_create_draft_api_with_disclose_false(client, services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{OWN}")
    res = client.post("/api/drafts", json={"video_id": OWN, "disclose": False})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["body"] == GOOD_BODY and data["disclosed"] is False and data["passed"] is True
    # 기본은 표기를 붙인다(예전 요청 그대로)
    services.use([draft(GOOD_BODY)])
    res = client.post("/api/drafts", json={"video_id": OWN})
    assert res.json()["disclosed"] is True and res.json()["body"].startswith("[광고] ")


def test_create_draft_api_refuses_disclose_false_on_other_video(client, services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    res = client.post("/api/drafts", json={"video_id": NOT_OWN, "disclose": False})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["kind"] == "disclosure_required"
    assert err["message"] == "이 영상은 홍보 표기를 끌 수 없습니다."
    assert "own_video_ids" in err["action"]


def test_settings_shows_only_the_count_of_own_videos(client):
    data = client.get("/api/settings").json()
    assert data["comment"]["own_video_count"] == 1
    assert OWN not in str(data)  # 영상 ID 자체는 보이지 않는다
