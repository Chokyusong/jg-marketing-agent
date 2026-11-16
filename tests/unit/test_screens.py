"""9단계: 크롬 창 위치가 실제 모니터 안인지 확인하는 순수 함수(app/browser/screens.py).

이 PC에서 창을 띄워 보지 않는다. 모니터 목록을 만들어 넣고 계산만 본다.
"""

from __future__ import annotations

import pytest

from app.browser.screens import (
    Monitor,
    check_window_position,
    on_screen,
    primary_monitor,
    read_monitors,
)

MAIN = Monitor(0, 0, 1920, 1080, primary=True)
UPPER = Monitor(0, -1080, 1920, 0)
LEFT = Monitor(-1920, 1, 0, 1081)  # 2026-11-16에 본 배치(왼쪽 {X=-1920,Y=1})
DEFAULT = (60, -1060)  # config.yaml browser.window_position 기본값(위쪽 2번 모니터)


def test_single_monitor_moves_default_to_main_monitor():
    """심사자 PC처럼 모니터가 하나면 60,-1060은 화면 밖 → 주 모니터 60,60."""
    check = check_window_position(DEFAULT, [MAIN])
    assert check.adjusted is True and check.checked is True
    assert check.position == (60, 60)
    assert check.requested == DEFAULT
    assert check.note == "창 위치(60,-1060)가 화면 밖이라 주 모니터(60,60)에 띄웁니다"


def test_upper_monitor_keeps_default():
    check = check_window_position(DEFAULT, [MAIN, UPPER])
    assert check.adjusted is False and check.position == DEFAULT
    assert check.note == "화면 안"


def test_left_monitor_layout():
    # 위쪽 좌표는 화면 밖(왼쪽 모니터에도 주 모니터에도 없다) → 주 모니터로
    assert check_window_position(DEFAULT, [MAIN, LEFT]).position == (60, 60)
    # 왼쪽 모니터 좌표는 그대로
    left = check_window_position((-1860, 60), [MAIN, LEFT])
    assert left.adjusted is False and left.position == (-1860, 60)


def test_main_monitor_point_is_kept_and_edges_need_the_title_bar():
    assert check_window_position((60, 60), [MAIN]).adjusted is False
    # 왼쪽 위 점은 안이지만 제목 표시줄을 잡을 자리가 화면 밖(오른쪽 끝·아래 끝)
    assert check_window_position((1900, 60), [MAIN]).adjusted is True
    assert check_window_position((60, 1070), [MAIN]).adjusted is True
    # 바로 바깥(왼쪽·위)도 밖
    assert check_window_position((-1, 0), [MAIN]).adjusted is True
    assert check_window_position((0, -1), [MAIN]).adjusted is True


@pytest.mark.parametrize("bad", [None, "60,-1060", ("a", "b"), (1,), (1, 2, 3), (True, 5), 42])
def test_bad_values_fall_back_to_main_monitor(bad):
    check = check_window_position(bad, [MAIN, UPPER])
    assert check.adjusted is True
    assert check.position == (60, 60)
    assert check.requested is None
    assert "잘못돼" in check.note


def test_unknown_monitors_keep_the_setting():
    """모니터 정보를 못 읽으면(빈 목록) 확인하지 않고 설정값 그대로."""
    check = check_window_position(DEFAULT, [])
    assert check.adjusted is False and check.checked is False and check.position == DEFAULT
    # 값까지 잘못됐으면 갈 곳이 없어 None(창 라이브러리가 가운데에 띄운다)
    assert check_window_position(None, []).position is None


def test_fallback_center_for_the_program_window():
    check = check_window_position(DEFAULT, [MAIN], fallback_center=True)
    assert check.adjusted is True and check.position is None
    assert "가운데" in check.note


def test_primary_monitor_choice_and_invalid_rects():
    second_main = Monitor(1920, 0, 3840, 1080, primary=True)
    # 주 모니터 표시가 있는 쪽으로(왼쪽 위가 (0,0)이 아니어도)
    check = check_window_position((5000, 5000), [Monitor(0, 0, 1920, 1080), second_main])
    assert check.position == (1980, 60)
    assert primary_monitor([Monitor(0, 0, 1920, 1080), second_main]) == second_main
    # 표시가 없으면 (0,0)을 품은 모니터
    assert primary_monitor([LEFT, Monitor(0, 0, 1920, 1080)]) == Monitor(0, 0, 1920, 1080)
    # 크기가 없는 영역은 무시한다
    broken = Monitor(0, 0, 0, 0)
    assert primary_monitor([broken]) is None
    assert on_screen((60, 60), [broken]) is False
    assert check_window_position((60, 60), [broken]).checked is False


def test_read_monitors_returns_rects():
    monitors = read_monitors()  # Windows가 아니거나 읽지 못하면 빈 목록
    assert isinstance(monitors, list)
    for m in monitors:
        assert isinstance(m, Monitor) and m.valid
