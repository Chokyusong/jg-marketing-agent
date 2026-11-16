"""광고 표기 켬/끔(R3) — 모든 영상에서. 가짜 YouTube, 가짜 LLM.

- 처음 상태는 설정 `comment.disclose_default`(기본 켬).
- 끈 초안은 표기 없이 저장되고 V4를 「표기 끔」으로 통과한다. 켠 초안은 `[광고] `로 시작해야 한다.
  글자 수는 어느 쪽이든 전체 글로 센다.
- 켬/끔을 바꾸면 그 영상의 초안을 다시 맞춘다: 저장된 글에 표기만 붙이거나 떼고 다시 검사한다.
  **모델을 부르지 않는다.** 길어져 넘치면 검사에 걸린 채로 보인다.
- 작업 기록에 그 댓글이 표기를 붙였는지 남는다.
- 옛 「내 채널 영상(own_video_ids)」 구분은 없다(설정 키가 남아 있어도 조용히 무시).
"""

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, add_youtube, draft

OTHER = "AAAAAAAAAA1"  # 아무 영상(예전에는 표기를 끌 수 없던 「내 채널이 아닌 영상」)


@pytest.fixture
def overrides() -> dict:
    return {}


@pytest.fixture
def client(mock_http, fixture_json, fake_key, make_client, overrides):
    return make_client(add_youtube(mock_http(), fixture_json), key=fake_key, overrides=overrides)


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


def v1(validation):
    return next(c for c in validation.checks if c.code == "V1")


# ---------------------------------------------------------------- 서비스


@pytest.mark.parametrize("video", [VID, OTHER])
def test_any_video_can_draft_without_the_label(services, video):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(video, disclose=False)
    assert d.disclosed is False
    assert d.body == GOOD_BODY and not d.body.startswith("[광고]")
    assert d.passed, d.validation.failure_lines()
    assert v4(d.validation).passed and v4(d.validation).message == "표기 끔"


def test_label_on_keeps_the_label_and_counts_full_text(services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(VID)
    assert d.disclosed is True and d.body == f"[광고] {GOOD_BODY}"
    assert d.passed and v4(d.validation).message == "맨 앞이 [광고]"
    assert d.validation.char_count == len(f"[광고] {GOOD_BODY}")


def test_unlabelled_text_passes_v4_only_when_label_is_off(services):
    services.use([ANALYSIS])
    services.drafts.analyze(VID)
    checks = services.drafts.checks
    assert v4(checks.check(VID, GOOD_BODY, disclose=False)).passed
    assert not v4(checks.check(VID, GOOD_BODY, disclose=True)).passed
    assert not v4(checks.check(VID, GOOD_BODY)).passed  # 기본은 표기를 본다
    assert not v4(checks.check(VID, f"{GOOD_BODY} [광고]", disclose=True)).passed  # 가운데는 안 됨


def test_toggle_strips_and_adds_the_label_without_calling_the_model(services):
    llm = services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(OTHER)
    calls = len(llm.calls)
    off = services.drafts.set_disclosure(d.id, False)
    assert off.id == d.id and off.disclosed is False and off.body == GOOD_BODY
    assert off.passed and v4(off.validation).message == "표기 끔"
    on = services.drafts.set_disclosure(d.id, True)
    assert on.disclosed is True and on.body == f"[광고] {GOOD_BODY}" and on.passed
    assert len(llm.calls) == calls  # 모델을 다시 부르지 않는다
    assert on.evidence_quote == d.evidence_quote  # 근거 구절은 그대로


def test_toggle_on_that_overflows_shows_as_failing(services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(VID, disclose=False)
    long_text = (GOOD_BODY + " 마음이 편해지길 바랄게요" * 10)[:118]
    edited = services.drafts.update_text(d.id, long_text)
    assert edited.disclosed is False and len(edited.body) == 118
    on = services.drafts.set_disclosure(d.id, True)
    assert on.body.startswith("[광고] ") and len(on.body) > 120
    assert not on.passed and not v1(on.validation).passed  # 글자 수 넘침(표기 포함)
    assert v4(on.validation).passed


def test_toggle_resets_approval(services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(VID)
    assert services.drafts.approve(d.id).status == "approved"
    off = services.drafts.set_disclosure(d.id, False)
    assert off.status == "draft"  # 글이 바뀌었으니 다시 [댓글 달기]에서 승인한다
    assert services.drafts.approve(d.id).status == "approved"


@pytest.mark.parametrize("overrides", [{"comment": {"disclose_default": False}}])
def test_settings_default_off_applies_to_new_drafts(services):
    services.use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY)])
    d = services.drafts.generate(VID)
    assert d.disclosed is False and d.body == GOOD_BODY and d.passed
    again = services.drafts.generate(VID, disclose=True)  # 화면에서 켜면 그대로 붙는다
    assert again.disclosed is True and again.body.startswith("[광고] ")


# ---------------------------------------------------------------- API


def test_create_draft_api_with_disclose_false_on_any_video(client, services):
    services.use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{OTHER}")
    res = client.post("/api/drafts", json={"video_id": OTHER, "disclose": False})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["body"] == GOOD_BODY and data["disclosed"] is False and data["passed"] is True
    services.use([draft(GOOD_BODY)])
    res = client.post("/api/drafts", json={"video_id": OTHER})  # 비우면 설정 기본값(켬)
    assert res.json()["disclosed"] is True and res.json()["body"].startswith("[광고] ")


def test_disclosure_api_toggles_without_model_and_records(client, services):
    llm = services.use([ANALYSIS, draft(GOOD_BODY)])
    client.post(f"/api/analysis/{VID}")
    made = client.post("/api/drafts", json={"video_id": VID}).json()
    calls = len(llm.calls)
    res = client.post(f"/api/drafts/{made['id']}/disclosure", json={"disclose": False})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == made["id"] and data["disclosed"] is False and data["body"] == GOOD_BODY
    assert data["passed"] is True
    assert len(llm.calls) == calls
    approved = client.post(f"/api/drafts/{made['id']}/approve")
    assert approved.status_code == 200
    rec = next(r for r in client.get("/api/records").json()["items"] if r["action"] == "approve")
    assert rec["disclosed"] is False  # 작업 기록에 표기를 붙였는지 남는다
    missing = client.post("/api/drafts/9999/disclosure", json={"disclose": True})
    assert missing.status_code == 404


def test_validate_api_follows_the_toggle(client, services):
    services.use([ANALYSIS])
    client.post(f"/api/analysis/{VID}")

    def v4_of(body):
        checks = client.post("/api/validate", json=body).json()["checks"]
        return next(c for c in checks if c["code"] == "V4")

    assert v4_of({"video_id": VID, "text": GOOD_BODY, "disclose": False})["passed"] is True
    assert v4_of({"video_id": VID, "text": GOOD_BODY})["passed"] is False


def test_context_and_settings_no_longer_split_own_videos(client, services):
    assert client.post(f"/api/videos/{VID}/context").json()["own_video"] is False  # 호환용, 늘 거짓
    data = client.get("/api/settings").json()
    assert data["comment"]["own_video_count"] == 0
    assert data["edit"]["values"]["comment.disclose_default"] is True


@pytest.mark.parametrize("overrides", [{"own_video_ids": [VID]}])
def test_old_own_video_ids_key_changes_nothing(client, services):
    assert client.get("/api/settings").json()["comment"]["own_video_count"] == 0
    services.use([ANALYSIS, draft(GOOD_BODY)])
    d = services.drafts.generate(OTHER, disclose=False)
    assert d.passed and d.disclosed is False
