"""크롬 창을 띄울 모니터·위치·크기를 정한다(어느 PC에서나 저절로, 2026-11-17).

설정 「크롬 창을 띄울 화면」(`browser.window_screen`):
- `auto`(기본, 「자동 (권장)」) 또는 빈 값 — 아래 자동 규칙.
- 모니터 ID(`screens.monitor_id`) — 그 모니터. 지금 연결돼 있지 않으면 자동으로 떨어지고
  한 줄로 알린다.
- 빈 값인데 옛 좌표(`browser.window_position`, 예전 판이 저장한 값)가 있으면 옛 방식 그대로(legacy):
  그 좌표가 화면 안이면 그대로, 밖이면 주 모니터 60,60(`screens.check_window_position`).

자동 규칙(`plan_window`, 순수 함수 — 모니터 목록과 프로그램 창이 있는 모니터만 보고 계산):
- 모니터가 둘 이상: 프로그램 창이 있는 모니터가 **아닌** 모니터. 여럿이면 주 모니터가 아닌 것 중
  프로그램 창에 가장 가까운 것. 프로그램 창 위치를 모르면(개발용 브라우저 실행) 주 모니터에
  있다고 본다.
  그 모니터 작업 영역 가운데에 둔다.
- 모니터가 하나(또는 고른 모니터에 프로그램 창도 있음): 그 모니터 **왼쪽**, 작업 영역 폭의 60% 안쪽.
  작업 화면의 ③칸(오른쪽, 진행 상태)이 가려지지 않는다. 크롬의 일(댓글 상자까지 내리고 입력)은
  가운데 세로 띠만 보이면 되고, 가려지는 ①②칸은 게시 중에 쓰지 않는다.
- 크기: 작업 표시줄을 뺀 작업 영역(`MONITORINFO.rcWork`) 안. 1280×900(예전 고정값)을 넘지 않고
  작은 화면에서는 줄인다.

좌표 기준(문서로 확인, 2026-11-17):
- Windows `GetMonitorInfoW`의 `rcMonitor`·`rcWork`는 가상 화면 좌표. 스레드가 Per-Monitor(V2) DPI
  인식일 때 물리 픽셀이고, 아니면 Windows가 값을 96 DPI 기준으로 바꿔 줄 수 있다(virtualization).
  그래서 `screens.read_monitors`는 읽는 동안만 스레드를 PMv2로 바꾼다(SetThreadDpiAwarenessContext).
  출처: learn.microsoft.com MONITORINFO · SetThreadDpiAwarenessContext · GetDpiForMonitor ·
  "High DPI Desktop Application Development on Windows".
- 크롬의 `--window-position`·`--window-size`와 DevTools `Browser.Bounds`(문서에는 "pixels"라고만
  있다)는 크롬의 DIP(배율을 뺀 화면 좌표)다. 크롬은 Windows에서 주 모니터를 뿌리로 두고 맞닿은
  모니터를 이어 붙여 물리 좌표를 DIP로 옮긴다(chromium docs/ui/display/display_conversion.md).
  `chrome_point`는 그 방식을 맞닿은 모니터 한 단계까지 흉내 낸 **어림값**이다. 배율이 모두 100%면
  물리 좌표와 같다. 배율이 섞이면 어긋날 수 있어 창을 연 뒤 실제 위치를 크롬에게 물어 바로잡는다
  (`correct_window`, Playwright로 여는 게시용 크롬만. 사람에게 여는 보통 크롬은 자동화 연결이 없어
  처음 위치·크기만 준다).
- 출처: chromedevtools.github.io/devtools-protocol Browser.getWindowForTarget · setWindowBounds ·
  Bounds(ChromeDevTools/devtools-protocol pdl/domains/Browser.pdl).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.browser.screens import (
    Monitor,
    check_window_position,
    monitor_id,
    primary_monitor,
    where_of,
)

MAX_SIZE = (1280, 900)  # 예전 고정 크기(DIP). 이보다 크게 띄우지 않는다
MIN_SIZE = (640, 480)  # 이보다 작은 화면이면 작업 영역 전부
MARGIN = 8  # 작업 영역 가장자리에서 띄우는 간격(DIP)
SHARE_RATIO = 0.6  # 모니터 하나를 같이 쓸 때 왼쪽에 쓰는 폭
TOLERANCE = 8  # 크롬 창의 보이지 않는 테두리만큼은 밖으로 나가도 된다(DIP)

AUTO = "auto"
NOTE_MISSING = "고른 모니터가 지금 연결돼 있지 않아 자동으로 고른 화면에 띄웁니다"
NOTE_UNKNOWN = "모니터 정보를 읽지 못해 크롬이 정하는 곳에 띄웁니다"


@dataclass(frozen=True)
class WindowTarget:
    """창을 연 뒤 확인할 값(크롬 DIP). `work`는 그 모니터 작업 영역을 크롬 DIP로 옮긴 어림값."""

    bounds: tuple[int, int, int, int]  # left, top, width, height
    work: tuple[int, int, int, int]
    physical_work: tuple[int, int]  # 작업 영역 물리 픽셀 폭·높이(모니터를 알아보는 데 쓴다)
    where: str  # 주 모니터에서 본 방향("" 주 모니터 · 위쪽 · 아래쪽 · 왼쪽 · 오른쪽)
    primary: tuple[int, int, int, int]  # 주 모니터를 크롬 DIP로(왼쪽 위는 보통 0,0)


@dataclass(frozen=True)
class WindowPlan:
    """크롬 창을 띄울 곳. `position`·`size`는 크롬 인자(DIP). 모르면 None(크롬이 정한다)."""

    position: tuple[int, int] | None
    size: tuple[int, int] | None
    monitor: Monitor | None
    label: str  # 「모니터 2(위쪽)」
    mode: str  # auto | chosen | legacy | unknown
    note: str = ""  # 사람에게 알릴 한 줄(떨어짐·옛 좌표가 화면 밖 등). 없으면 ""
    fell_back: bool = False
    adjusted: bool = False  # 옛 좌표가 화면 밖이라 옮겼는지(legacy)
    target: WindowTarget | None = None

    @property
    def where_text(self) -> str:
        """설정 화면 한 줄: 「지금은 모니터 2(위쪽)에 뜹니다」."""
        return f"지금은 {self.label}에 뜹니다" if self.label else "지금은 크롬이 정하는 곳에 뜹니다"


# ---------------------------------------------------------------- 모니터 이름과 고르기


def ordered(monitors: Sequence[Monitor]) -> list[Monitor]:
    """설정 화면과 같은 순서(주 모니터가 먼저, 그다음 위→아래, 왼쪽→오른쪽)."""
    good = [m for m in monitors if m.valid]
    main = primary_monitor(good)
    return sorted(good, key=lambda m: (m != main, m.top, m.left))


def label_of(m: Monitor, monitors: Sequence[Monitor]) -> str:
    """「모니터 1(주 모니터)」 · 「모니터 2(위쪽)」."""
    order = ordered(monitors)
    main = primary_monitor(order)
    n = next((i for i, x in enumerate(order, start=1) if x == m), 0)
    where = "주 모니터" if m == main else (where_of(m, main) or "다른 모니터")
    return f"모니터 {n}({where})" if n else where


def _center(m: Monitor) -> tuple[float, float]:
    return (m.left + m.right) / 2, (m.top + m.bottom) / 2


def auto_monitor(
    monitors: Sequence[Monitor], app_monitor: Monitor | None = None
) -> tuple[Monitor, bool]:
    """자동 규칙으로 고른 모니터와, 프로그램 창과 같은 모니터를 같이 쓰는지(왼쪽에 둔다)."""
    good = [m for m in monitors if m.valid]
    main = primary_monitor(good)
    assert main is not None, "모니터 목록이 비어 있다"
    app = next((m for m in good if app_monitor and monitor_id(m) == monitor_id(app_monitor)), main)
    others = [m for m in good if monitor_id(m) != monitor_id(app)]
    if not others:
        return app, True
    pool = [m for m in others if m != main] or others
    ax, ay = _center(app)
    pick = min(pool, key=lambda m: (math.dist(_center(m), (ax, ay)), m.top, m.left))
    return pick, False


# ---------------------------------------------------------------- 크롬 DIP로 옮기기(어림)


TOUCH = 4  # 모니터 사이가 이만큼 떨어져 있어도 맞닿은 것으로 본다(물리 픽셀)


def _touching(m: Monitor, p: Monitor) -> str:
    if abs(m.left - p.right) <= TOUCH:
        return "right"
    if abs(m.right - p.left) <= TOUCH:
        return "left"
    if abs(m.bottom - p.top) <= TOUCH:
        return "above"
    if abs(m.top - p.bottom) <= TOUCH:
        return "below"
    return ""


def dip_origin(m: Monitor, monitors: Sequence[Monitor]) -> tuple[float, float]:
    """모니터 왼쪽 위를 크롬 DIP로.

    주 모니터를 뿌리로 맞닿은 모니터 한 단계까지, 나머지는 배율로 나눈다(어림값)."""
    p = primary_monitor(monitors) or m
    sp, s = p.scale or 1.0, m.scale or 1.0
    if m == p:
        return p.left / sp, p.top / sp
    side = _touching(m, p)
    if side == "right":
        return p.right / sp, m.top / sp
    if side == "left":
        return p.left / sp - (m.right - m.left) / s, m.top / sp
    if side == "above":
        return m.left / sp, p.top / sp - (m.bottom - m.top) / s
    if side == "below":
        return m.left / sp, p.bottom / sp
    return m.left / s, m.top / s


def chrome_point(x: float, y: float, m: Monitor, monitors: Sequence[Monitor]) -> tuple[int, int]:
    """모니터 `m` 안의 물리 좌표 → 크롬 DIP 좌표(어림값)."""
    ox, oy = dip_origin(m, monitors)
    s = m.scale or 1.0
    return round(ox + (x - m.left) / s), round(oy + (y - m.top) / s)


def _dip_work(m: Monitor, monitors: Sequence[Monitor]) -> tuple[int, int, int, int]:
    wl, wt, wr, wb = m.work_rect
    left, top = chrome_point(wl, wt, m, monitors)
    s = m.scale or 1.0
    return left, top, int((wr - wl) / s), int((wb - wt) / s)


# ---------------------------------------------------------------- 정하기


def _size_for(work_w: int, work_h: int, *, share: bool) -> tuple[int, int]:
    room_w, room_h = max(1, work_w - 2 * MARGIN), max(1, work_h - 2 * MARGIN)
    width = min(MAX_SIZE[0], int(work_w * SHARE_RATIO) - MARGIN if share else room_w)
    if width < MIN_SIZE[0]:
        width = min(room_w, MIN_SIZE[0]) if share else room_w
    height = min(MAX_SIZE[1], room_h)
    return max(1, width), max(1, height)


def place_on(
    m: Monitor, monitors: Sequence[Monitor], *, share: bool
) -> tuple[tuple[int, int], tuple[int, int], WindowTarget]:
    """모니터 `m` 작업 영역 안의 위치·크기(크롬 DIP). `share`면 왼쪽, 아니면 가운데."""
    left, top, work_w, work_h = _dip_work(m, monitors)
    width, height = _size_for(work_w, work_h, share=share)
    if share:
        x, y = left + MARGIN, top + MARGIN
    else:
        x, y = left + (work_w - width) // 2, top + (work_h - height) // 2
    x = min(max(x, left), left + work_w - width)
    y = min(max(y, top), top + work_h - height)
    main = primary_monitor(monitors) or m
    ml, mt = dip_origin(main, monitors)
    sp = main.scale or 1.0
    primary_rect = (round(ml), round(mt), int((main.right - main.left) / sp),
                    int((main.bottom - main.top) / sp))
    wl, wt, wr, wb = m.work_rect
    target = WindowTarget(
        bounds=(x, y, width, height),
        work=(left, top, work_w, work_h),
        physical_work=(wr - wl, wb - wt),
        where="" if m == main else where_of(m, main),
        primary=primary_rect,
    )
    return (x, y), (width, height), target


def plan_window(
    monitors: Sequence[Monitor],
    *,
    screen: str | None = AUTO,
    legacy: Any = None,
    app_monitor: Monitor | None = None,
) -> WindowPlan:
    """크롬 창을 띄울 곳을 정한다(순수 함수). 작업을 시작할 때마다 지금 모니터로 다시 부른다."""
    good = [m for m in monitors if m.valid]
    choice = (screen or "").strip()
    if not good:
        point = None if choice else _point(legacy)
        return WindowPlan(point, None, None, "", "unknown", note=NOTE_UNKNOWN)
    note, fell_back = "", False
    if choice and choice != AUTO:
        m = next((x for x in good if monitor_id(x) == choice), None)
        if m is not None:
            share = app_monitor is not None and monitor_id(app_monitor) == monitor_id(m)
            pos, size, target = place_on(m, good, share=share)
            return WindowPlan(pos, size, m, label_of(m, good), "chosen", target=target)
        note, fell_back = NOTE_MISSING, True
    elif not choice and _point(legacy) is not None:
        return _legacy(_point(legacy), good)
    m, share = auto_monitor(good, app_monitor)
    pos, size, target = place_on(m, good, share=share)
    return WindowPlan(pos, size, m, label_of(m, good), "auto", note=note, fell_back=fell_back,
                      target=target)


def _point(value: Any) -> tuple[int, int] | None:
    try:
        x, y = value
        if isinstance(x, bool) or isinstance(y, bool):
            return None
        return int(x), int(y)
    except (TypeError, ValueError):
        return None


def _legacy(point: tuple[int, int], good: list[Monitor]) -> WindowPlan:
    """옛 좌표: 예전과 같은 확인(화면 밖이면 주 모니터 60,60).

    크기는 그 모니터 작업 영역에 맞춘다."""
    check = check_window_position(point, good)
    pos = check.position or point
    m = next((x for x in good if x.contains(*pos)), None) or primary_monitor(good)
    size = None
    if m is not None:
        left, top, work_w, work_h = _dip_work(m, good)
        room_w = max(1, left + work_w - pos[0] - MARGIN)
        room_h = max(1, top + work_h - pos[1] - MARGIN)
        size = (min(MAX_SIZE[0], room_w), min(MAX_SIZE[1], room_h))
    label = label_of(m, good) if m is not None else ""
    return WindowPlan(pos, size, m, label, "legacy", note=check.note if check.adjusted else "",
                      adjusted=check.adjusted)


# ---------------------------------------------------------------- 연 뒤에 바로잡기


@dataclass(frozen=True)
class Landed:
    """창을 연 뒤 크롬에게 물은 값(모두 크롬 DIP).

    페이지의 `screenX`·`outerWidth`·`screen.avail*`."""

    x: int
    y: int
    width: int
    height: int
    avail: tuple[int, int, int, int]  # 창이 있는 화면의 작업 영역 left, top, width, height
    dpr: float  # devicePixelRatio(그 화면 배율)


LANDED_SCRIPT = """() => ({
  x: window.screenX, y: window.screenY, width: window.outerWidth, height: window.outerHeight,
  availLeft: screen.availLeft, availTop: screen.availTop,
  availWidth: screen.availWidth, availHeight: screen.availHeight, dpr: window.devicePixelRatio
})"""


def landed_from(raw: dict[str, Any]) -> Landed | None:
    try:
        return Landed(
            int(raw["x"]), int(raw["y"]), int(raw["width"]), int(raw["height"]),
            (int(raw["availLeft"]), int(raw["availTop"]), int(raw["availWidth"]),
             int(raw["availHeight"])),
            float(raw.get("dpr") or 1.0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _where_dip(avail: tuple[int, int, int, int], primary: tuple[int, int, int, int]) -> str:
    al, at, aw, ah = avail
    pl, pt, pw, ph = primary
    if al < pl + pw and al + aw > pl and at < pt + ph and at + ah > pt:
        return ""  # 주 모니터와 겹친다 = 주 모니터
    dx = (al + aw / 2) - (pl + pw / 2)
    dy = (at + ah / 2) - (pt + ph / 2)
    if abs(dy) >= abs(dx):
        return "위쪽" if dy < 0 else "아래쪽"
    return "왼쪽" if dx < 0 else "오른쪽"


def on_target_screen(landed: Landed, target: WindowTarget) -> bool:
    """창이 정한 모니터에 떴는지: 그 화면의 물리 크기와 주 모니터에서 본 방향이 같은지."""
    _, _, aw, ah = landed.avail
    pw, ph = target.physical_work
    same_size = abs(aw * landed.dpr - pw) <= 3 and abs(ah * landed.dpr - ph) <= 3
    return same_size and _where_dip(landed.avail, target.primary) == target.where


def inside(landed: Landed) -> bool:
    al, at, aw, ah = landed.avail
    t = TOLERANCE
    return (landed.x >= al - t and landed.y >= at - t
            and landed.x + landed.width <= al + aw + t
            and landed.y + landed.height <= at + ah + t)


def fit_into(landed: Landed) -> tuple[int, int, int, int]:
    """창이 있는 화면의 작업 영역 안으로 들이는 bounds(크롬 DIP)."""
    al, at, aw, ah = landed.avail
    width, height = min(landed.width, aw), min(landed.height, ah)
    x = min(max(landed.x, al), al + aw - width)
    y = min(max(landed.y, at), at + ah - height)
    return x, y, width, height


def correct_window(
    landed: Landed, target: WindowTarget, *, tried_move: bool
) -> tuple[tuple[int, int, int, int] | None, str]:
    """연 뒤 확인: 바로잡을 bounds(없으면 None)와 까닭.

    - 정한 모니터에 있고 작업 영역 안 → None, "ok"
    - 다른 모니터 → (한 번만) 정한 bounds로 옮긴다 "move".
      옮겨도 안 되면 지금 화면 안으로 "fit_other"
    - 정한 모니터지만 화면 밖·작업 표시줄에 걸침 → 작업 영역 안으로 "fit"
    """
    if not on_target_screen(landed, target):
        if not tried_move:
            return target.bounds, "move"
        return (None, "other") if inside(landed) else (fit_into(landed), "fit_other")
    if inside(landed):
        return None, "ok"
    return fit_into(landed), "fit"
