"""모델 본문 정리(app/analysis/drafter.clean_body) — 자모 표기 뒤 마침표(2026-11-18 기획 담당).

기획 담당이 뽑은 초안 18개 중 3개: 「현실적이네ㅋㅋ.」「답답하다 ㅠㅠ.」「어렵다 ㅠㅠ.」.
사람은 ㅋㅋ 뒤에 마침표를 찍지 않는다. 모델 글을 받는 자리에서만 지우고, 사람이 고친 글은
그대로 둔다.
"""

import pytest

from app.analysis.drafter import clean_body


@pytest.mark.parametrize("raw, want", [
    ("현실적이네ㅋㅋ. 요즘 운명원이 연애사주를 잘 본다고 하던데, 저도 한번 가 보려고요.",
     "현실적이네ㅋㅋ 요즘 운명원이 연애사주를 잘 본다고 하던데, 저도 한번 가 보려고요."),
    ("답답하다 ㅠㅠ. 요즘", "답답하다 ㅠㅠ 요즘"),
    ("어렵다 ㅠㅠ.", "어렵다 ㅠㅠ"),
    ("좋다ㅎㅎ. 그리고 ㅜㅜ. 끝", "좋다ㅎㅎ 그리고 ㅜㅜ 끝"),
    ("[광고] 웃기다ㅋㅋ. 요즘", "웃기다ㅋㅋ 요즘"),  # 모델이 붙인 표기도 뗀다
])
def test_period_right_after_jamo_is_dropped(raw, want):
    assert clean_body(raw, "[광고]") == want


@pytest.mark.parametrize("raw", [
    "답답하다 ㅠㅠ... 요즘 운명원이 연애사주를 잘 본다고 하던데.",  # 말줄임은 그대로
    "웃기다ㅋㅋ.. 요즘",
    "그 마음 알 것 같다. 요즘 운명원",  # 자모 뒤가 아닌 마침표
    "ㅋㅋ 진짜 웃기네요.",
])
def test_ellipsis_and_ordinary_periods_stay(raw):
    assert clean_body(raw, "[광고]") == raw
