"""크롬 창 위치 자동(2026-11-17): 어느 PC에서나 저절로 맞추는 규칙(순수 함수, 창을 띄우지 않는다).

규칙은 app/browser/placement.py 머리말. 여기서는 모니터 배치(하나 · 노트북 · 위·왼쪽·오른쪽 ·
음수 좌표 · 셋 · 고른 모니터 없음 · 150% 배율 · 프로그램 창 위치 모름)마다 계산값을 본다.
"""

from __future__ import annotations

import pytest

from app.browser.chrome import assist_args
from app.browser.placement import (
    AUTO,
    MAX_SIZE,
    NOTE_MISSING,
    NOTE_UNKNOWN,
    SHARE_RATIO,
    Landed,
    auto_monitor,
    correct_window,
    label_of,
    landed_from,
    plan_window,
)
from app.browser.sandbox_driver import HEADED_WINDOW_SIZE, PlaywrightSandboxDriver
from app.browser.screens import Monitor, monitor_id
from app.desktop import WINDOW_MIN_SIZE, WINDOW_SIZE, fit_app_window

TASKBAR = 40
MAIN = Monitor(0, 0, 1920, 1080, primary=True, work=(0, 0, 1920, 1080 - TASKBAR))
UPPER = Monitor(0, -1080, 1920, 0)
LEFT = Monitor(-1920, 0, 0, 1080)
RIGHT = Monitor(1920, 0, 3840, 1080)
LAPTOP = Monitor(0, 0, 1366, 768, primary=True, work=(0, 0, 1366, 728))


def inside_work(plan, m: Monitor) -> bool:
    """배율 100%에서는 크롬 DIP = 물리 좌표라 바로 비교할 수 있다."""
    (x, y), (w, h) = plan.position, plan.size
    wl, wt, wr, wb = m.work_rect
    return wl <= x and wt <= y and x + w <= wr and y + h <= wb


# ---------------------------------------------------------------- 모니터 하나


def test_single_full_hd_monitor_goes_left_so_the_progress_column_stays_visible():
    plan = plan_window([MAIN])
    assert plan.mode == "auto" and plan.monitor == MAIN and plan.note == ""
    assert plan.position == (8, 8) and plan.size == (1144, 900)
    assert plan.position[0] + plan.size[0] <= 1920 * SHARE_RATIO  # 오른쪽 40%(③칸)는 비워 둔다
    assert inside_work(plan, MAIN)
    assert plan.where_text == "지금은 모니터 1(주 모니터)에 뜹니다"


def test_small_laptop_shrinks_the_window_into_the_work_area():
    plan = plan_window([LAPTOP])
    assert plan.position == (8, 8) and plan.size == (811, 712)
    assert plan.size[0] < MAX_SIZE[0] and plan.size[1] < MAX_SIZE[1]
    assert plan.position[0] + plan.size[0] <= 1366 * SHARE_RATIO
    assert inside_work(plan, LAPTOP)  # 작업 표시줄(아래 40)에 걸치지 않는다


def test_window_never_grows_past_the_old_fixed_size():
    big = Monitor(0, 0, 3840, 2160, primary=True)
    plan = plan_window([big, Monitor(0, -2160, 3840, 0)])
    assert plan.size == MAX_SIZE


# ------------------------------------------------ 모니터 둘(위·왼쪽·오른쪽, 음수 좌표)


@pytest.mark.parametrize(
    ("other", "position", "label"),
    [
        (UPPER, (320, -990), "모니터 2(위쪽)"),
        (LEFT, (-1600, 90), "모니터 2(왼쪽)"),
        (RIGHT, (2240, 90), "모니터 2(오른쪽)"),
        (Monitor(0, 1080, 1920, 2160), (320, 1170), "모니터 2(아래쪽)"),
    ],
)
def test_two_monitors_use_the_one_without_the_app(other, position, label):
    plan = plan_window([MAIN, other])  # 프로그램 창 위치를 모르면 주 모니터에 있다고 본다
    assert plan.monitor == other and plan.mode == "auto"
    assert plan.position == position and plan.size == (1280, 900)
    assert plan.label == label and plan.where_text == f"지금은 {label}에 뜹니다"
    assert inside_work(plan, other)


def test_app_on_the_second_monitor_sends_chrome_to_the_main_one():
    plan = plan_window([MAIN, UPPER], app_monitor=UPPER)
    assert plan.monitor == MAIN and plan.label == "모니터 1(주 모니터)"
    assert plan.position == (320, 70) and inside_work(plan, MAIN)  # 가운데(함께 쓰지 않음)


def test_upper_left_layout_with_small_gap_like_this_pc():
    """이 PC(2026-11-17 실측): 왼쪽 세로 모니터 · 위쪽 모니터, 사이가 1~2픽셀 떨어져 있다."""
    main = Monitor(0, 0, 1920, 1080, primary=True, work=(0, 0, 1920, 1032))
    upper = Monitor(0, -1082, 1920, -2, work=(0, -1082, 1920, -50))
    portrait = Monitor(-1080, -1081, 0, 839, work=(-1080, -1081, 0, 791))
    plan = plan_window([main, upper, portrait])
    assert plan.monitor == upper and plan.label == "모니터 2(위쪽)"
    # 2픽셀 틈은 맞닿은 것으로 보고 주 모니터 바로 위(-1080)에서 센다(크롬 DIP 어림값)
    assert plan.position == (320, -1014) and plan.size == (1280, 900)


# ---------------------------------------------------------------- 모니터 셋


def test_three_monitors_pick_the_non_primary_one_nearest_the_app():
    monitors = [MAIN, UPPER, RIGHT]
    assert auto_monitor(monitors)[0] == UPPER  # 주 모니터에서 위쪽이 오른쪽보다 가깝다
    assert plan_window(monitors, app_monitor=RIGHT).monitor == UPPER  # 주 모니터가 아닌 것 먼저
    assert plan_window(monitors, app_monitor=UPPER).monitor == RIGHT


def test_three_monitors_labels_follow_settings_order():
    monitors = [RIGHT, MAIN, LEFT]
    assert [label_of(m, monitors) for m in (MAIN, LEFT, RIGHT)] == [
        "모니터 1(주 모니터)", "모니터 2(왼쪽)", "모니터 3(오른쪽)"]


# ---------------------------------------------------------------- 모니터를 고른 경우


def test_chosen_monitor_is_used_and_shares_left_when_the_app_is_there():
    plan = plan_window([MAIN, LEFT], screen=monitor_id(LEFT))
    assert plan.mode == "chosen" and plan.monitor == LEFT and plan.position == (-1600, 90)
    shared = plan_window([MAIN, LEFT], screen=monitor_id(MAIN), app_monitor=MAIN)
    assert shared.monitor == MAIN and shared.position == (8, 8) and shared.size == (1144, 900)


def test_missing_chosen_monitor_falls_back_to_auto_with_a_note():
    plan = plan_window([MAIN], screen=monitor_id(UPPER))  # 위쪽 모니터를 뺀 뒤
    assert plan.mode == "auto" and plan.fell_back is True and plan.note == NOTE_MISSING
    assert plan.monitor == MAIN and plan.position == (8, 8)


def test_auto_ignores_an_old_saved_position():
    plan = plan_window([MAIN, UPPER], screen=AUTO, legacy=(-1860, 60))
    assert plan.mode == "auto" and plan.monitor == UPPER


# ------------------------------------------------ 예전 판이 저장한 좌표(그대로 읽는다)


def test_old_saved_position_keeps_the_old_behavior():
    kept = plan_window([MAIN, UPPER], screen="", legacy=(60, -1060))
    assert kept.mode == "legacy" and kept.position == (60, -1060) and kept.adjusted is False
    assert kept.size == (1280, 900) and kept.label == "모니터 2(위쪽)"
    moved = plan_window([MAIN], screen="", legacy=(60, -1060))
    assert moved.position == (60, 60) and moved.adjusted is True
    assert "화면 밖" in moved.note
    assert moved.size == (1280, 900)


# ---------------------------------------------------------------- 150% 배율 · 모니터를 못 읽음


def test_150_percent_scale_uses_chrome_dip_sizes():
    main = Monitor(0, 0, 2880, 1620, primary=True, work=(0, 0, 2880, 1560), scale=1.5)
    plan = plan_window([main])
    assert plan.position == (8, 8) and plan.size == (1144, 900)  # 1920×1040 DIP 기준
    assert plan.target.physical_work == (2880, 1560)


def test_150_percent_two_monitors():
    main = Monitor(0, 0, 3840, 2160, primary=True, scale=1.5)
    upper = Monitor(0, -2160, 3840, 0, scale=1.5)
    plan = plan_window([main, upper])
    assert plan.monitor == upper
    assert plan.position == (640, -1170) and plan.size == (1280, 900)  # 2560×1440 DIP의 가운데
    assert plan.target.work == (0, -1440, 2560, 1440)
    mixed = plan_window([main, Monitor(0, -1080, 1920, 0)])  # 위쪽만 100%
    assert mixed.position == (320, -990)


def test_unreadable_monitors_let_chrome_decide():
    plan = plan_window([])
    assert plan.position is None and plan.size is None and plan.mode == "unknown"
    assert plan.note == NOTE_UNKNOWN and plan.where_text == "지금은 크롬이 정하는 곳에 뜹니다"
    old = plan_window([], screen="", legacy=(60, -1060))
    assert old.position == (60, -1060)  # 못 읽으면 예전처럼 설정값 그대로


# ---------------------------------------------------------------- 연 뒤 확인·바로잡기


def landed(x, y, w, h, avail, dpr=1.0):
    return Landed(x, y, w, h, avail, dpr)


UPPER_WORK = (0, -1080, 1920, 1080)
MAIN_WORK = (0, 0, 1920, 1040)


def test_correct_window_cases():
    target = plan_window([MAIN, UPPER]).target
    ok = landed(320, -990, 1280, 900, UPPER_WORK)
    assert correct_window(ok, target, tried_move=False) == (None, "ok")
    wrong = landed(320, 70, 1280, 900, MAIN_WORK)
    assert correct_window(wrong, target, tried_move=False) == (target.bounds, "move")
    assert correct_window(wrong, target, tried_move=True) == (None, "other")
    spill = landed(1000, 70, 1280, 900, MAIN_WORK)
    assert correct_window(spill, target, tried_move=True) == ((640, 70, 1280, 900), "fit_other")
    over_edge = landed(320, -500, 1280, 900, UPPER_WORK)  # 정한 모니터지만 아래로 넘침
    assert correct_window(over_edge, target, tried_move=False) == ((320, -900, 1280, 900), "fit")


def test_on_target_uses_physical_size_with_device_pixel_ratio():
    main = Monitor(0, 0, 3840, 2160, primary=True, scale=1.5)
    upper = Monitor(0, -2160, 3840, 0, scale=1.5)
    target = plan_window([main, upper]).target
    there = landed(640, -1170, 1280, 900, (0, -1440, 2560, 1440), dpr=1.5)
    assert correct_window(there, target, tried_move=False) == (None, "ok")


def test_landed_from_page_values():
    raw = {"x": 1, "y": 2, "width": 3, "height": 4, "availLeft": 0, "availTop": -1080,
           "availWidth": 1920, "availHeight": 1040, "dpr": 1.25}
    assert landed_from(raw) == Landed(1, 2, 3, 4, (0, -1080, 1920, 1040), 1.25)
    assert landed_from({"x": 1}) is None


class FakeCdp:
    def __init__(self):
        self.sent = []

    def send(self, method, params=None):
        self.sent.append((method, params))
        return {"windowId": 7} if method == "Browser.getWindowForTarget" else {}


class FakeCtx:
    def __init__(self, cdp):
        self.cdp = cdp

    def new_cdp_session(self, page):
        return self.cdp


class FakePage:
    def __init__(self, answers):
        self.answers = list(answers)

    def evaluate(self, script):
        return self.answers.pop(0)

    def wait_for_timeout(self, ms):
        pass


def page_values(x, y, w, h, avail, dpr=1.0):
    al, at, aw, ah = avail
    return {"x": x, "y": y, "width": w, "height": h, "availLeft": al, "availTop": at,
            "availWidth": aw, "availHeight": ah, "dpr": dpr}


def test_driver_moves_a_window_that_landed_on_the_wrong_monitor():
    plan = plan_window([MAIN, UPPER])
    driver = PlaywrightSandboxDriver(headless=False, window_position=plan.position,
                                     window_size=plan.size, window_target=plan.target)
    cdp = FakeCdp()
    driver._ctx = FakeCtx(cdp)
    driver._page = FakePage([page_values(320, 70, 1280, 900, MAIN_WORK),
                             page_values(320, -990, 1280, 900, UPPER_WORK)])
    driver._check_window()
    assert driver.window_check == "ok" and not driver.window_note
    moves = [p for m, p in cdp.sent if m == "Browser.setWindowBounds"]
    assert moves == [{"windowId": 7, "bounds": {"windowState": "normal"}},
                     {"windowId": 7, "bounds": {"left": 320, "top": -990,
                                                "width": 1280, "height": 900}}]


def test_driver_reports_when_the_window_cannot_reach_the_monitor():
    plan = plan_window([MAIN, UPPER])
    driver = PlaywrightSandboxDriver(headless=False, window_position=plan.position,
                                     window_size=plan.size, window_target=plan.target)
    driver._ctx = FakeCtx(FakeCdp())
    stuck = page_values(320, 70, 1280, 900, MAIN_WORK)
    driver._page = FakePage([stuck, stuck])
    driver._check_window()
    assert driver.window_check == "other" and "옮기지 못했습니다" in driver.window_note


# ---------------------------------------------------------------- 크롬 인자


def test_launch_args_carry_planned_position_and_size():
    plan = plan_window([MAIN, UPPER])
    headed = PlaywrightSandboxDriver(headless=False, window_position=plan.position,
                                     window_size=plan.size)
    args = headed.launch_args()
    assert "--window-position=320,-990" in args and "--window-size=1280,900" in args
    unknown = PlaywrightSandboxDriver(headless=False, window_position=None)
    args = unknown.launch_args()
    assert not any(a.startswith("--window-position") for a in args)
    assert HEADED_WINDOW_SIZE in args


def test_plain_chrome_args_carry_position_and_size(tmp_path):
    plan = plan_window([LAPTOP])
    args = assist_args(tmp_path / "chrome.exe", tmp_path / "p", "https://example.invalid/",
                       plan.position, plan.size)
    assert "--window-position=8,8" in args and "--window-size=811,712" in args
    bare = assist_args(tmp_path / "chrome.exe", tmp_path / "p", "https://example.invalid/", None)
    assert not any(a.startswith("--window-") for a in bare)


# ---------------------------------------------------------------- 프로그램 창(app/desktop.py)


def test_app_window_fits_the_primary_work_area():
    assert fit_app_window([MAIN]).width == WINDOW_SIZE[0]
    assert fit_app_window([MAIN]).height == WINDOW_SIZE[1]  # 1000은 작업 영역 1040 안에 들어간다
    short = Monitor(0, 0, 1920, 1080, primary=True, work=(0, 0, 1920, 1000))
    assert fit_app_window([short]).height == 1000 - 16  # 작업 표시줄이 크면 줄인다
    assert fit_app_window([MAIN]).maximized is False
    small = fit_app_window([LAPTOP])
    assert small.maximized is True  # 1366×728은 최소 크기(1100×720)+여백보다 작다
    assert small.width <= 1366 and small.height <= 728
    assert small.min_size == (WINDOW_MIN_SIZE[0], WINDOW_MIN_SIZE[1])
    tiny = fit_app_window([Monitor(0, 0, 1024, 600, primary=True)])
    assert tiny.maximized is True and tiny.min_size == (1024, 600)


def test_app_window_uses_logical_pixels_at_150_percent():
    fit = fit_app_window([Monitor(0, 0, 2880, 1620, primary=True, work=(0, 0, 2880, 1560),
                                  scale=1.5)])
    assert (fit.width, fit.height, fit.maximized) == (1600, 1000, False)  # 1920×1040 논리


def test_app_window_defaults_when_monitors_unknown():
    fit = fit_app_window([])
    assert (fit.width, fit.height, fit.min_size, fit.maximized) == (
        WINDOW_SIZE[0], WINDOW_SIZE[1], WINDOW_MIN_SIZE, False)
