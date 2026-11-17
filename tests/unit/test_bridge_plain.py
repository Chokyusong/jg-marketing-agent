"""잇는 문장은 쉬운 말로, 넣을지는 코드가(2026-11-18 기획 담당 C).

- 쉬운 낱말(인연·운명·타이밍·때·궁합·맞는 사람·팔자)과 끝꼴(「~인가 봐요」「~있는 듯」「~따로 있나
  싶네요」「~것 같아요」)을 프롬프트에 알리고, 꾸민 말(「결」「박자」「작용」「고비」「~을 타다」)은
  다듬기 검사 S17이 다시 쓰게 한다.
- 잇는 문장은 약 3개 중 2개. 같은 영상 초안끼리는 넣은 것(+까닭)·안 넣은 것(까닭만)을 섞는다
  (`prompts.assign_bridge`). 정하지 않았는데 넣으면 S16.
- S12는 통째로 같은 잇는 문장만(낱말이 겹치는 것은 괜찮다).
"""

from __future__ import annotations

import pytest

from app.analysis import style as S
from app.llm import prompts as P

BRAND = "운명원"
REACTION = "[광고] 하루에 한 번 연락으로 싸웠다니 남 일 같지 않네요. "
LEAD = "요즘 운명원이 연애사주를 잘 본다고 하더라구요. "


def _codes(issues):
    return [i.split(" ", 1)[0] for i in issues]


def _style(text, **kw):
    return S.style_issues(text, brand=BRAND, disclosure="[광고]", need_bridge=True, **kw)


@pytest.mark.parametrize("bridge, word", [
    ("둘이 결이 안 맞는 건가 봐요.", "결이"),
    ("연애도 박자가 맞아야 하나 봐요.", "박자"),
    ("인연도 때가 작용하는 걸까요.", "작용"),
    ("이번이 고비인가 봐요.", "고비"),
    ("연애도 타이밍을 타는 것 같아요.", "을 타"),
    ("다 흐름을 타야 하나 봐요.", "을 타"),
])
def test_s17_fancy_bridge_words(bridge, word):
    text = REACTION + bridge + " " + LEAD + "저도 한번 가보려구요."
    got = _style(text, bridge_wanted=True)
    assert "S17" in _codes(got), got
    assert word in next(i for i in got if i.startswith("S17"))
    # 사람이 고친 글(정한 것이 없음)은 보지 않는다
    assert "S17" not in _codes(_style(text))


@pytest.mark.parametrize("bridge", [
    "결국 맞는 사람이 따로 있나 싶네요.",
    "이것도 다 인연인가 봐요.",
    "연애도 타이밍이 있는 듯.",
    "결국 궁합 문제인 것 같아요.",
    "다 팔자인가 봐요.",
    "결국 운명인가 봐요.",
])
def test_plain_bridges_pass(bridge):
    text = REACTION + bridge + " " + LEAD + "저도 한번 가보려구요."
    assert P.bridge_sentence(text, BRAND) == bridge
    got = _style(text, bridge_wanted=True)
    assert "S17" not in _codes(got) and "S16" not in _codes(got), got


def test_s16_bridge_when_the_draft_should_go_reason_only():
    bridged = REACTION + "이것도 다 인연인가 봐요. " + LEAD + "저도 한번 가보려구요."
    assert "S16" in _codes(_style(bridged, bridge_wanted=False))
    assert "S16" not in _codes(_style(bridged, bridge_wanted=True))
    assert "S16" not in _codes(_style(bridged))  # 사람이 고친 글
    reason_only = REACTION + LEAD + "저도 연락 문제로 한번 가보려구요."
    assert _style(reason_only, bridge_wanted=False) == []
    # 잇는 문장도 까닭도 없으면 S11(이번 초안은 까닭을 넣으라고)
    plain = REACTION + LEAD + "저도 한번 가보려구요."
    got = _style(plain, bridge_wanted=False)
    assert [i[:9] for i in got if i.startswith("S11")] == ["S11 까닭 없음"]


def test_same_video_drafts_mix_and_overall_share_is_about_two_in_three():
    b = REACTION + "이것도 다 인연인가 봐요. " + LEAD + "저도 한번 가보려구요."
    n = REACTION + LEAD + "저도 연락 문제로 한번 가보려구요."
    # 같은 영상 앞 초안이 모두 넣었으면 빼고, 모두 안 넣었으면 넣는다
    assert P.assign_bridge(BRAND, [b, b, n], [b]) is False
    assert P.assign_bridge(BRAND, [n, n, n], [n]) is True
    # 첫 초안: 앞서 보인 초안의 몫이 2/3보다 적으면 넣는다
    assert P.assign_bridge(BRAND, [], []) is True
    assert P.assign_bridge(BRAND, [b, n, n], []) is True
    assert P.assign_bridge(BRAND, [b, b, n], []) is False
    # 영상마다 첫 초안만 만든다고 치면 약 3개 중 2개
    shown: list[str] = []
    for _ in range(30):
        shown.insert(0, b if P.assign_bridge(BRAND, shown, []) else n)
    share = sum(bool(P.bridge_sentence(t, BRAND)) for t in shown) / len(shown)
    assert 0.6 <= share <= 0.72, share
    # 영상마다 두 개면 영상 안에서 하나씩 섞인다
    shown, pairs = [], []
    for _ in range(14):
        first = P.assign_bridge(BRAND, shown, [])
        shown.insert(0, b if first else n)
        second = P.assign_bridge(BRAND, shown, [shown[0]])
        shown.insert(0, b if second else n)
        pairs.append((first, second))
    assert all(f != s for f, s in pairs), pairs


def test_prompt_lists_plain_words_and_says_when_to_leave_the_bridge_out():
    system = P.draft_system(brand=BRAND, disclosure="[광고]", facts=())
    for w in P.BRIDGE_WORDS:
        assert w in system
    assert "'~인가 봐요', '~있는 듯', '~따로 있나 싶네요', '~것 같아요' 같은 꼴로 끝낸다" in system
    assert "'결'·'박자'·'작용'·'고비'·'~을 타다' 같은 꾸민 말은 쓰지 않는다" in system
    assert "낱말은 겹쳐도 되지만 통째로 같은 문장은 쓰지 않는다" in system
    base = dict(analysis={"concern": "c"}, quote="q", source="comment", min_body=35,
                max_body=115)
    without = P.draft_user(**base, bridge=False, reason=True)
    assert "이번 초안에는 **잇는 문장을 넣지 않는다**" in without
    assert "**잇는 한 문장**" not in without
    with_bridge = P.draft_user(**base, bridge=True, used_bridges=["다 인연인가 봐요."])
    assert "이미 쓴 잇는 문장: '다 인연인가 봐요.' — 통째로 같은 문장만 피한다" in with_bridge
    assert "넣지 않는다**" not in with_bridge
    assert "잇는 문장" not in P.draft_user(**base)  # 정하지 않으면 말하지 않는다
