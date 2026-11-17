"""C1 다듬기(대표 지시 2026-11-17 「초안 더 다듬고」) — 가짜 YouTube, 가짜 LLM.

- 규칙 검사를 통과해도 다듬기 검사(110자 넘음 · 바람에 핵심 말 · 붙여 쓴 말 · 같은 영상 앞 초안과
  비슷함)에 걸리면 다시 쓸 차례가 남았을 때 한 번 더 쓰게 한다. 마지막 차례면 통과한 글을 둔다.
- [다른 댓글 만들기]는 앞 초안의 핵심 말·운명원 꺼내는 말을 피하라고 프롬프트에 넣는다.
- 다듬기 단계: 통과한 초안을 한 번 더 보여 고치게 하고 다시 검사한다. 더 나빠지면 원래 글.
"""

import pytest
from test_drafts_api import (
    ANALYSIS,
    GOOD_BODY,
    GOOD_BODY_2,
    KEYS,
    Q_COMMENT,
    VID,
    add_youtube,
    draft,
)

from app.errors import AppError, ErrorKind


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


# 규칙 검사(V1~V14)는 통과하지만 다듬기 검사에 걸리는 글
STUFFED = (  # S2: 운명원 뒤의 바람에 핵심 말('하루에 한 번 연락')을 끼움
    "장거리는 진짜 연락이 전부인 듯...ㅠㅠ 운명원 연애 사주 잘 본다던데 하루에 한 번 연락이면 "
    "되는지 물어보고 싶어요."
)
GLUED = (  # S3: 「이유여쭤보고」
    "기대치 차이라는 말에 뜨끔했어요. 요즘 운명원 얘기 자주 보이던데 자꾸 싸우는 이유여쭤보고 "
    "싶네요."
)
LONG = (  # S1: 표기까지 110자 넘음(120자 한도 안)
    "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요ㅠㅠ 저도 연락 문제로 늘 마음 졸이는 "  # noqa: E501
    "편이라 남 일 같지가 않아요. 운명원 연애 사주 잘 본다던데 이번 인연은 오래 갈지 알면 좋겠어요."
)


def test_samples_pass_the_rules_but_not_the_style_checks(setup):
    _, services, use = setup
    use([ANALYSIS])
    services.drafts.analyze(VID)
    for body, code in ((STUFFED, "S2"), (GLUED, "S3"), (LONG, "S1")):
        text = f"[광고] {body}"
        v = services.checks.check(VID, text, evidence_quote=Q_COMMENT, key_phrases=KEYS,
                                  concern=ANALYSIS["concern"])
        assert v.passed, (body, v.failure_lines())
        issues = services.drafts._style(text, "[광고]", KEYS, [])
        assert [i[:2] for i in issues] == [code], (body, issues)
    assert 110 < len(f"[광고] {LONG}") <= 120


@pytest.mark.parametrize(("body", "code"), [(STUFFED, "S2 바람에 핵심 말"),
                                            (GLUED, "S3 띄어쓰기·말꼴"), (LONG, "S1 길이")])
def test_passed_but_awkward_draft_is_written_again(setup, body, code):
    _, services, use = setup
    llm = use([ANALYSIS, draft(body), draft(GOOD_BODY)])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {GOOD_BODY}" and d.attempts == 2
    assert d.first_passed  # 첫 글이 규칙 검사는 통과했다(모델 비교 숫자는 그대로)
    retry = user_prompts(llm)[2]
    assert "[다시 쓰기] 앞의 본문이 검사에 걸렸다." in retry and f"- {code}: " in retry
    assert f"앞의 본문: {body}" in retry
    run = services.drafts.last_run
    assert [a["issues"][0][:2] for a in run["attempts"][:1]] == [code[:2]]
    assert run["attempts"][1]["issues"] == []


def test_awkward_draft_on_the_last_attempt_is_kept_because_it_passed(setup):
    # 다듬기 검사는 승인을 막지 않는다: 세 번 다 어색하면 규칙을 통과한 글 중 문제가 적은 것
    _, services, use = setup
    llm = use([ANALYSIS, draft(LONG), draft(STUFFED), draft(LONG)])
    d = services.drafts.generate(VID)
    assert d.passed and d.attempts == 3 and len(llm.calls) == 4
    assert d.body == f"[광고] {LONG}"  # 문제 수가 같으면 먼저 쓴 것


def test_rule_failure_is_still_fixed_before_style(setup):
    # 규칙 검사에 걸린 글(V5: 브랜드 없음)보다는 어색해도 통과한 글을 남긴다
    _, services, use = setup
    no_brand = (
        "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 "
        "않네요ㅠㅠ 연애 사주 한번 보고 싶다."
    )
    use([ANALYSIS, draft(no_brand), draft(LONG), draft(no_brand)])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {LONG}"


def test_another_draft_must_differ_from_the_earlier_one(setup):
    _, services, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), draft(GOOD_BODY), draft(GOOD_BODY_2)])
    first = services.drafts.generate(VID)
    second = services.drafts.generate(VID, avoid_quotes=[first.evidence_quote])
    assert second.body == f"[광고] {GOOD_BODY_2}" and second.attempts == 2
    prompt, retry = user_prompts(llm)[2], user_prompts(llm)[3]
    # 앞 초안이 쓴 핵심 말·운명원 꺼내는 말을 피하라고 처음부터 적는다
    assert "같은 영상에 이미 쓴 초안 — 이것과 다른 글로 쓴다" in prompt
    assert f"- [광고] {GOOD_BODY}" in prompt
    assert "앞 초안에 쓴 핵심 말('하루에 한 번 연락') 말고 다른 핵심 말로 시작한다" in prompt
    hearsay = next(x for x in prompt.splitlines() if x.startswith("운명원을 꺼내는 말은"))
    assert "잘 본다던데" not in hearsay  # 앞 초안이 쓴 꺼내는 말은 권하지 않는다
    assert "- S4 앞 초안과 비슷함: 같은 영상의 앞 초안과 100% 같습니다" in retry


def test_same_hearsay_as_the_earlier_draft_is_written_again(setup):
    _, services, use = setup
    same_mark = (
        "기대치 차이라니 뼈 맞았네ㅋㅋ 연애만 하면 속도가 엇갈림. 운명원에서 연애 사주 잘 "
        "본다던데 이번 인연은 어떨지 궁금해지네."
    )
    llm = use([ANALYSIS, draft(GOOD_BODY), draft(same_mark), draft(GOOD_BODY_2)])
    services.drafts.generate(VID)
    second = services.drafts.generate(VID)
    assert second.body == f"[광고] {GOOD_BODY_2}"
    assert "운명원을 앞 초안과 같은 말('잘 본다던데')로 꺼냈습니다" in user_prompts(llm)[3]


# ---------------------------------------------------------------- 다듬기 단계

FIXED = (
    "장거리는 진짜 연락이 전부인 듯...ㅠㅠ 운명원 연애 사주 잘 본다던데 이번 인연은 오래 갈지 "
    "물어보고 싶어요."
)


def polished(body, changed=True):
    return {"body": body, "changed": changed}


def test_polish_fixes_the_awkward_part_and_is_checked_again(setup):
    _, services, use = setup
    services.drafts.polish = True
    # 세 번 다 S2(바람에 핵심 말) → 다듬기가 그 대목만 고친다
    llm = use([ANALYSIS, draft(STUFFED), draft(STUFFED), draft(STUFFED), polished(FIXED)])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {FIXED}" and d.attempts == 3
    call = llm.calls[-1]["kwargs"]
    assert "맞춤법·문장만 손보는 한국어 교정자" in call["system"]
    assert f"[댓글 본문] {STUFFED}" in call["user"]  # 표기 없이 본문만
    assert "[코드가 찾은 문제] 이것도 고친다:\n- S2 바람에 핵심 말" in call["user"]
    assert "[영상 제목] " in call["user"] and ANALYSIS["concern"] in call["user"]
    info = services.drafts.last_run["polish"]
    assert info["accepted"] and info["before"] == f"[광고] {STUFFED}" and info["issues_after"] == []
    assert isinstance(info["seconds"], float)
    rows = services.ledger.recent(limit=5)
    assert any(r.action == "draft" and "다듬음" in (r.reason or "") for r in rows)


def test_polish_that_breaks_a_rule_keeps_the_original(setup):
    _, services, use = setup
    services.drafts.polish = True
    broken = (
        "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 "
        "않네요ㅠㅠ 연애 사주 한번 보고 싶다."
    )
    use([ANALYSIS, draft(GOOD_BODY), polished(broken)])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {GOOD_BODY}"
    info = services.drafts.last_run["polish"]
    assert not info["accepted"] and any(x.startswith("V5") for x in info["failures_after"])


def test_polish_that_adds_style_issues_keeps_the_original(setup):
    _, services, use = setup
    services.drafts.polish = True
    use([ANALYSIS, draft(GOOD_BODY), polished(LONG)])  # 통과하지만 110자를 넘김
    d = services.drafts.generate(VID)
    assert d.body == f"[광고] {GOOD_BODY}" and not services.drafts.last_run["polish"]["accepted"]


def test_polish_with_nothing_to_fix_or_a_model_error_keeps_the_draft(setup):
    _, services, use = setup
    services.drafts.polish = True
    use([ANALYSIS, draft(GOOD_BODY), polished(GOOD_BODY, changed=False)])
    assert services.drafts.generate(VID).body == f"[광고] {GOOD_BODY}"
    use([draft(GOOD_BODY_2), AppError(ErrorKind.LLM_TIMEOUT, message="시간 초과")])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {GOOD_BODY_2}"
    assert services.drafts.last_run["polish"]["error"] == "시간 초과"


def test_failed_draft_is_not_polished(setup):
    _, services, use = setup
    services.drafts.polish = True
    no_brand = (
        "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 "
        "않네요ㅠㅠ 연애 사주 한번 보고 싶다."
    )
    llm = use([ANALYSIS, draft(no_brand), draft(no_brand), draft(no_brand)])
    d = services.drafts.generate(VID)
    assert not d.passed and len(llm.calls) == 4 and services.drafts.last_run["polish"] == {}


def test_polish_off_makes_no_extra_call(setup):
    _, services, use = setup
    services.drafts.polish = False
    llm = use([ANALYSIS, draft(GOOD_BODY)])
    services.drafts.generate(VID)
    assert len(llm.calls) == 2 and services.drafts.last_run["polish"] == {}


COPIED_NUMBER = (  # S5: 영상 속 숫자(「1년차」)를 내 일처럼
    "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요ㅠㅠ 저도 1년차라 자주 싸워요. "
    "운명원 연애 사주 잘 본다던데 이번 인연은 오래 갈지 알면 좋겠어요."
)


def test_number_copied_from_the_video_is_written_again(setup):
    # 영상 자료 글(제목 「장거리 연애 1년차…」)을 다듬기 검사에 넘겨 숫자 복사를 잡는다
    _, services, use = setup
    llm = use([ANALYSIS, draft(COPIED_NUMBER), draft(GOOD_BODY)])
    d = services.drafts.generate(VID)
    assert d.passed and d.body == f"[광고] {GOOD_BODY}" and d.attempts == 2
    first = services.drafts.last_run["attempts"][0]
    assert first["failures"] == [] and [i[:2] for i in first["issues"]] == ["S5"]
    assert "- S5 영상 사연을 내 것으로: '1년'" in user_prompts(llm)[2]
