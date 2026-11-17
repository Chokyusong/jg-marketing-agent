"""조각 배정이 초안 만들기·다시 쓰기·AI 검수 뒤 다시 쓰기에 이어지는가(2026-11-18 기획 담당 A).

- 첫 프롬프트에 「이번 초안의 운명원 대목: 때=… / 평판=… / 들은 꼴=… / 끝말=…」.
- 모델이 다른 조각을 쓰면 S15로 다시 쓰고, 다시 쓰는 프롬프트에도 **같은 조각**.
- AI 검수에 걸려 다시 쓸 때도 그 초안의 조각 그대로.

가짜 YouTube, 가짜 LLM(정해 준 조각 줄을 읽어 그대로 쓰는 차례가 있다).
"""

import re

import pytest
from test_drafts_api import ANALYSIS, GOOD_BODY, VID, add_youtube, draft

HEAD = "이번 초안의 운명원 대목:"
# 영상 반응은 차례마다 다르게(같은 영상 초안끼리 S4 「앞 초안과 비슷함」에 걸리지 않게)
REACTIONS = (
    "하루에 한 번 연락 갖고 싸웠다는 댓글에 공감해요. ",
    "기대치 차이라는 말에 뜨끔했어요. ",
    "장거리는 하루에 한 번 연락도 서운할 듯ㅠㅠ ",
)


def follow(user: str, n: int = 0) -> dict:
    """프롬프트의 조각 줄을 읽어 그대로 쓴 초안."""
    line = next(x for x in user.splitlines() if x.startswith(HEAD))
    joined = re.search(r"이어 쓰면: '([^']+)'", line).group(1)
    return draft(REACTIONS[n % len(REACTIONS)] + joined + ".")


def piece_line(user: str) -> str:
    line = next(x for x in user.splitlines() if x.startswith(HEAD))
    return line.split(" — ", 1)[0]


@pytest.fixture
def setup(mock_http, fixture_json, fake_key, make_client, fake_llm, piece_check_on):
    client = make_client(add_youtube(mock_http(), fixture_json), key=fake_key)
    services = client.app.state.services.get()

    def use(responses):
        llm = fake_llm(responses)
        llm.model = "fake-model"
        plain = llm.generate_json

        followed = []

        def generate_json(*args, **kwargs):
            item = plain(*args, **kwargs)
            if item != "follow":
                return item
            followed.append(1)
            return follow(kwargs["user"], len(followed) - 1)

        llm.generate_json = generate_json
        services.llm = llm
        return llm

    return client, services, use


def users(llm):
    return [c["kwargs"]["user"] for c in llm.calls]


def test_other_pieces_are_written_again_with_the_same_assignment(setup):
    _, services, use = setup
    llm = use([ANALYSIS, draft(GOOD_BODY), "follow"])
    d = services.drafts.generate(VID)
    first, retry = users(llm)[1], users(llm)[2]
    assert piece_line(first).startswith(HEAD + " 때='")
    assert piece_line(first) == piece_line(retry)  # 다시 쓸 때도 같은 배정
    assert "- S15 정해 준 조각과 다름: " in retry
    assert d.passed and d.attempts == 2
    run = services.drafts.last_run
    assert [i[:3] for i in run["attempts"][0]["issues"]].count("S15") == 1
    assert not [i for i in run["attempts"][1]["issues"] if i.startswith("S15")]


def test_following_the_pieces_passes_first_time(setup):
    _, services, use = setup
    use([ANALYSIS, "follow"])
    d = services.drafts.generate(VID)
    assert d.passed and d.attempts == 1 and d.first_passed
    assert not [i for i in services.drafts.last_run["attempts"][0]["issues"]
                if i.startswith("S15")]


def test_next_draft_gets_other_pieces_and_never_the_same_lead(setup):
    _, services, use = setup
    use([ANALYSIS, "follow", "follow", "follow"])
    bodies = [services.drafts.generate(VID).body for _ in range(3)]
    from app.llm import prompts as P

    leads = [P.fold(P.lead_part(b, "운명원")) for b in bodies]
    assert len(set(leads)) == 3, bodies


def test_ai_review_rewrite_keeps_the_same_pieces(setup):
    _, services, use = setup
    llm = use([ANALYSIS, "follow", {"ok": False, "problems": ["이어짐이 갑작스러움"]}, "follow",
               {"ok": True, "problems": []}])
    d = services.drafts.generate(VID)
    reviewed = services.drafts.review(d.id)
    first, rewrite = users(llm)[1], users(llm)[2]
    assert "이어짐이 갑작스러움" in rewrite
    assert piece_line(first) == piece_line(rewrite)
    assert reviewed.review_status == "rewritten"
