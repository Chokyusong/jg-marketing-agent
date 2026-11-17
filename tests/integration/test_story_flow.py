"""⑤의 꼴 배정이 초안 만들기·다시 쓰기에 이어지는가(2026-11-18 기획 담당 D-1).

- 처음 초안의 요청 글에 「이번 끝말은 **'저도 + [사주로 알고 싶은 것] + …」와 그 끝말(보러 가다 쪽).
- 알고 싶은 것을 빼고 쓰면 S18로 다시 쓰고, 다시 쓰는 요청에도 **같은 조각·같은 꼴**.
- 같은 영상 다음 초안은 상태 까닭이나 까닭 없음(셋 중 둘만 알고 싶은 것).

가짜 YouTube, 가짜 LLM(정해 준 조각 줄을 읽어 그대로 쓰는 차례가 있다).
"""

import re

import pytest
from test_drafts_api import ANALYSIS, VID, add_youtube, draft

from app.llm import prompts as P

HEAD = "이번 초안의 운명원 대목:"
WISH_LINE = "이번 끝말은 **'저도 + [사주로 알고 싶은 것] + "
REACTIONS = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글에 공감해요. ",
    "장거리는 하루에 한 번 연락도 서운할 듯ㅠㅠ ",
    "기대치 차이라는 말이 내 얘기 같아서 찔리네. ",
)


def joined(user: str) -> str:
    line = next(x for x in user.splitlines() if x.startswith(HEAD))
    return re.search(r"이어 쓰면: '([^']+)'", line).group(1)


def piece_line(user: str) -> str:
    line = next(x for x in user.splitlines() if x.startswith(HEAD))
    return line.split(" — ", 1)[0]


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, piece_check_on,
          story_check_on):
    client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key)
    services = client.app.state.services.get()

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        plain = llm.generate_json
        n = [0]

        def generate_json(*args, **kwargs):
            item = plain(*args, **kwargs)
            if item not in ("follow", "follow_wish"):
                return item
            tail = joined(kwargs["user"])
            if item == "follow_wish":
                tail = tail.replace("저도 ", "저도 이 사람이랑 잘 맞는지 ", 1)
            n[0] += 1
            return draft(REACTIONS[(n[0] - 1) % len(REACTIONS)] + tail + ".")

        llm.generate_json = generate_json
        services.llm = llm
        return llm

    return client, services, use


def users(llm):
    return [c["kwargs"]["user"] for c in llm.calls]


def test_first_draft_asks_for_a_wish_and_writes_again_without_one(setup):
    _, services, use = setup
    llm = use([ANALYSIS, "follow", "follow_wish"])
    d = services.drafts.generate(VID, review=False)
    first, retry = users(llm)[1], users(llm)[2]
    assert WISH_LINE in first
    assert piece_line(first) == piece_line(retry) and WISH_LINE in retry  # 같은 배정
    assert any(a in piece_line(first) for a in P.WISH_ACTIONS)
    assert "- S18 알고 싶은 것 없음: " in retry
    assert d.passed and d.attempts == 2
    assert P.reason_kind(d.body, "운명원") == P.REASON_WISH
    assert P.intent_reason(d.body, "운명원") == "이 사람이랑 잘 맞는지"


def test_next_draft_of_the_same_video_is_not_a_wish_again(setup):
    _, services, use = setup
    llm = use([ANALYSIS, "follow_wish", "follow", "follow"])
    first = services.drafts.generate(VID, review=False)
    assert first.passed and first.attempts == 1
    services.drafts.generate(VID, review=False)
    second = users(llm)[2]
    assert WISH_LINE not in second
    assert ("짧은 **상태 까닭**(12자 안)을 넣는다" in second
            or "이번 끝말은 까닭 없이 본보기 꼴" in second), second
    assert "이미 쓴 까닭·알고 싶은 것: '이 사람이랑 잘 맞는지'" in second
