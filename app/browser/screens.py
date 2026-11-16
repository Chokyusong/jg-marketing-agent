"""창 위치가 실제 모니터 안인지 확인한다(9단계).

`browser.window_position` 기본값 `60,-1060`은 대표 PC의 위쪽 2번 모니터 좌표다. 모니터가 하나인
PC(심사자 PC)에서는 그 좌표가 화면 밖이라 크롬 창이 보이지 않는다. 그래서 창을 띄우기 전에
좌표가 어느 모니터 안에 들어가는지 보고, 밖이면 주 모니터의 안전한 위치(왼쪽 위에서 60,60)로 바꾼다.

- `check_window_position()`은 순수 함수다(모니터 목록을 받아 계산만 한다). 테스트는 이 함수만 본다.
- `read_monitors()`는 Windows API(EnumDisplayMonitors · GetMonitorInfoW)로 모니터 영역을 읽는다.
  모니터를 하나씩 읽지 못하면 가상 화면 전체 범위(GetSystemMetrics SM_*VIRTUALSCREEN)로 대신한다.
  Windows가 아니거나 읽지 못하면 빈 목록 → 확인하지 않고 설정값 그대로 쓴다.
- 창의 왼쪽 위 점만 보지 않고, 제목 표시줄을 잡을 수 있는 작은 영역(왼쪽 위에서 가로 120px·
  세로 40px 안쪽 점)이 모니터 안에 있어야 "화면 안"으로 본다.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("app.browser.screens")

SAFE_OFFSET = (60, 60)  # 주 모니터 왼쪽 위에서 이만큼 떨어진 곳
GRAB_POINT = (120, 40)  # 창 왼쪽 위에서 이 점(제목 표시줄 안)이 모니터 안이어야 한다


@dataclass(frozen=True)
class Monitor:
    """모니터 한 대의 영역(가상 화면 좌표, 오른쪽·아래는 포함하지 않음)."""

    left: int
    top: int
    right: int
    bottom: int
    primary: bool = False

    @property
    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class PositionCheck:
    """확인 결과. `adjusted`가 참이면 설정값 대신 `position`을 쓴다(`note`에 이유)."""

    requested: tuple[int, int] | None
    position: tuple[int, int] | None
    adjusted: bool
    checked: bool  # 모니터 목록을 읽어 실제로 확인했는지
    note: str


def _as_point(value: Any) -> tuple[int, int] | None:
    try:
        x, y = value
        if isinstance(x, bool) or isinstance(y, bool):
            return None
        return int(x), int(y)
    except (TypeError, ValueError):
        return None


def _text(point: tuple[int, int] | None) -> str:
    return f"{point[0]},{point[1]}" if point else "없음"


def on_screen(point: tuple[int, int], monitors: Sequence[Monitor]) -> bool:
    """창 왼쪽 위가 `point`일 때 제목 표시줄을 잡을 수 있는 점이 어느 모니터 안에 있는지."""
    gx, gy = point[0] + GRAB_POINT[0], point[1] + GRAB_POINT[1]
    return any(m.valid and m.contains(point[0], point[1]) and m.contains(gx, gy) for m in monitors)


def primary_monitor(monitors: Sequence[Monitor]) -> Monitor | None:
    """주 모니터: 표시가 있으면 그것, 없으면 (0,0)을 품은 것, 그것도 없으면 첫 번째."""
    good = [m for m in monitors if m.valid]
    for m in good:
        if m.primary:
            return m
    for m in good:
        if m.contains(0, 0):
            return m
    return good[0] if good else None


def check_window_position(
    position: Any,
    monitors: Sequence[Monitor],
    *,
    fallback_center: bool = False,
) -> PositionCheck:
    """`position`이 실제 모니터 안이면 그대로, 밖이면 주 모니터의 안전한 위치로 바꾼다.

    - 모니터 목록이 비어 있으면(읽지 못함) 확인하지 않고 값을 그대로 돌려준다.
    - 값이 잘못됐으면(숫자 두 개가 아님) 안전한 위치로 바꾼다.
    - `fallback_center`가 참이면 바꿀 위치 대신 None(창 라이브러리가 가운데에 띄움)을 준다.
    """
    requested = _as_point(position)
    good = [m for m in monitors if m.valid]
    if requested is not None and not good:
        note = "모니터 정보를 읽지 못해 설정값 그대로"
        return PositionCheck(requested, requested, False, False, note)
    if requested is not None and on_screen(requested, good):
        return PositionCheck(requested, requested, False, True, "화면 안")
    main = primary_monitor(good)
    if fallback_center or main is None:
        safe = None
        where = "가운데"
    else:
        safe = (main.left + SAFE_OFFSET[0], main.top + SAFE_OFFSET[1])
        where = f"주 모니터({_text(safe)})"
    if requested is None:
        note = f"창 위치 값이 잘못돼({position!r}) {where}에 띄웁니다"
    else:
        note = f"창 위치({_text(requested)})가 화면 밖이라 {where}에 띄웁니다"
    return PositionCheck(requested, safe, True, bool(good), note)


# ---------------------------------------------------------------- Windows API


def read_monitors() -> list[Monitor]:
    """지금 연결된 모니터 영역들. 읽지 못하면 빈 목록(확인하지 않는다)."""
    if sys.platform != "win32":
        return []
    try:
        monitors = _enum_monitors()
        if monitors:
            return monitors
        return _virtual_screen()
    except Exception:  # pragma: no cover - Windows API 실패는 드물다
        log.exception("모니터 정보를 읽지 못했습니다")
        return []


def _enum_monitors() -> list[Monitor]:  # pragma: no cover - 실제 모니터에 따라 다르다
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    found: list[Monitor] = []
    proc_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def callback(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append(Monitor(r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    return found


def _virtual_screen() -> list[Monitor]:  # pragma: no cover
    import ctypes

    metric = ctypes.windll.user32.GetSystemMetrics
    x, y, w, h = metric(76), metric(77), metric(78), metric(79)  # SM_X/Y/CX/CYVIRTUALSCREEN
    if w <= 0 or h <= 0:
        return []
    return [Monitor(x, y, x + w, y + h, primary=False)]
