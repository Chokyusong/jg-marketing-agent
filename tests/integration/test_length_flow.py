"""길이 셈이 초안 만들기에 이어지는가(2026-11-18 기획 담당).

- 요청 글에 ①·② 글자 수 숫자와 맨 끝 [끝 꼴] 한 줄.
- 다듬기 검사 S1 문턱은 112자(규칙 검사 V1은 120자 그대로).
- 세 번 다 길이(V1)만 넘치면 잇는 문장을 덜어 본다(모델을 다시 부르지 않는다).

가짜 YouTube, 가짜 LLM.
"""

import pytest
from test_drafts_api import ANALYSIS, VID, add_youtube, draft

from app.analysis import style

REACTION = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글 보니 남 일 같지 않네요ㅠㅠ "
    "저도 연락 문제로 서운해지는 편이라.."
)
BRIDGE = "결국 맞는 사람은 따로 있나 싶네요."
BRAND_PART = "요즘 운명원이 연애사주를 그렇게 잘 본다고 하더라구요. 저도 언제 한번 가보려구요."
TOO_LONG = f"{REACTION} 자꾸만 {BRIDGE} {BRAND_PART}"  # 표기까지 130자대
JUST_FITS = f"{REACTION} {BRAND_PART}"  # 표기까지 111자(예전 S1 110자에는 걸린다)


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, length_plan_on):
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


def test_prompt_gives_numbers_and_ends_with_the_ending_form(setup):
    _, services, use = setup
    llm = use([ANALYSIS, draft(JUST_FITS)])
    services.drafts.generate(VID, review=False)
    first = users(llm)[1]
    assert "**이번 초안 글자 수(코드가 셈함, 표기 포함 " in first
    assert "자 안의 **온전한 한 문장**" in first
    assert first.splitlines()[-1].startswith("[끝 꼴] 저도 ")


def test_s1_waits_until_112_characters(setup):
    _, services, use = setup
    assert len("[광고] " + JUST_FITS) == 111 > style.SOFT_MAX_TOTAL
    llm = use([ANALYSIS, draft(JUST_FITS)])
    d = services.drafts.generate(VID, review=False)
    assert d.passed and d.attempts == 1 and len(llm.calls) == 2
    assert not [i for i in services.drafts.last_run["attempts"][0]["issues"]
                if i.startswith("S1")]


def test_only_too_long_three_times_drops_the_bridge(setup):
    _, services, use = setup
    long_text = "[광고] " + TOO_LONG
    assert len(long_text) > 120
    use([ANALYSIS, draft(TOO_LONG), draft(TOO_LONG), draft(TOO_LONG)])
    d = services.drafts.generate(VID, review=False)
    assert d.passed and d.attempts == 3
    assert BRIDGE not in d.body and len(d.body) <= 120
    assert d.body == "[광고] " + JUST_FITS  # 잇는 문장 한 문장(「자꾸만 결국 …」)째 덜었다
    assert services.drafts.last_run["trimmed"]["before"] == long_text


def test_other_failures_are_not_trimmed_away(setup):
    _, services, use = setup
    no_brand = (f"{REACTION} {BRIDGE} 연애사주 한번 보고 싶네요 진짜 요즘 너무 궁금해서 "
                "미치겠어요ㅠㅠ")
    use([ANALYSIS, draft(no_brand), draft(no_brand), draft(no_brand)])
    d = services.drafts.generate(VID, review=False)
    assert not d.passed and "trimmed" not in services.drafts.last_run
