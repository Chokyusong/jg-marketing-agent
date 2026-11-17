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
- 2026-11-17(창 위치 자동): 모니터마다 작업 영역(`rcWork`, 작업 표시줄을 뺀 곳)과 배율
  (`scale`, GetDpiForMonitor MDT_EFFECTIVE_DPI / 96)도 읽는다. 읽는 동안만 스레드를 Per-Monitor V2
  DPI 인식으로 바꿔 물리 픽셀을 받는다(아니면 Windows가 값을 바꿔 줄 수 있다).
  자동 규칙은 `app/browser/placement.py`.
  `app_window_monitor()`는 이 프로세스의 프로그램 창(제목 「JG Marketing Agent」)이 있는 모니터.
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
    # 작업 영역(작업 표시줄을 뺀 곳, left·top·right·bottom). 모르면 None → 모니터 전체
    work: tuple[int, int, int, int] | None = None
    scale: float = 1.0  # 화면 배율(125% → 1.25)

    @property
    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    @property
    def work_rect(self) -> tuple[int, int, int, int]:
        w = self.work
        if w is None or not (w[2] > w[0] and w[3] > w[1]):
            return self.left, self.top, self.right, self.bottom
        return w

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


# ---------------------------------------------------------------- R2: 설정 화면의 모니터 고르기


@dataclass(frozen=True)
class ScreenChoice:
    """설정 화면에서 고르는 모니터 하나.

    `position`은 그 모니터 왼쪽 위에서 60,60 떨어진 안전한 곳.
    """

    id: str
    label: str
    left: int
    top: int
    width: int
    height: int
    primary: bool
    position: tuple[int, int]
    current: bool  # 지금 설정한 창 위치가 이 모니터 안인지


def monitor_id(m: Monitor) -> str:
    return f"{m.left}_{m.top}_{m.right - m.left}_{m.bottom - m.top}"


def safe_position(m: Monitor) -> tuple[int, int]:
    return m.left + SAFE_OFFSET[0], m.top + SAFE_OFFSET[1]


def where_of(m: Monitor, main: Monitor | None) -> str:
    """주 모니터에서 본 방향(위쪽·아래쪽·왼쪽·오른쪽)."""
    if main is None or m == main:
        return ""
    cx, cy = (m.left + m.right) / 2, (m.top + m.bottom) / 2
    mx, my = (main.left + main.right) / 2, (main.top + main.bottom) / 2
    dx, dy = cx - mx, cy - my
    if abs(dy) >= abs(dx):
        return "위쪽" if dy < 0 else "아래쪽"
    return "왼쪽" if dx < 0 else "오른쪽"


def screen_choices(
    monitors: Sequence[Monitor], window_position: Any = None
) -> list[ScreenChoice]:
    """고를 수 있는 모니터 목록(주 모니터가 먼저).

    이름은 「모니터 1 · 주 모니터 · 1920×1080」처럼.
    """
    good = [m for m in monitors if m.valid]
    main = primary_monitor(good)
    ordered = sorted(good, key=lambda m: (m != main, m.top, m.left))
    point = _as_point(window_position)
    out: list[ScreenChoice] = []
    for i, m in enumerate(ordered, start=1):
        w, h = m.right - m.left, m.bottom - m.top
        where = "주 모니터" if m == main else f"{where_of(m, main) or '다른'} 모니터"
        out.append(
            ScreenChoice(
                id=monitor_id(m),
                label=f"모니터 {i} · {where} · {w}×{h}",
                left=m.left,
                top=m.top,
                width=w,
                height=h,
                primary=m == main,
                position=safe_position(m),
                current=bool(point and m.contains(*point)),
            )
        )
    return out


def find_choice(choices: Sequence[ScreenChoice], screen_id: str) -> ScreenChoice | None:
    return next((c for c in choices if c.id == screen_id), None)


# ---------------------------------------------------------------- Windows API


_where = where_of  # 예전 이름


DPI_PMV2 = -4  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
APP_WINDOW_TITLE = "JG Marketing Agent"  # app/desktop.py WINDOW_TITLE과 같다


class _PerMonitorDpi:  # pragma: no cover - 실제 Windows에서만
    """이 블록 안에서만 스레드를 Per-Monitor V2로(물리 픽셀). 끝나면 원래대로 돌린다."""

    def __enter__(self) -> _PerMonitorDpi:
        import ctypes

        self._old = None
        try:
            fn = ctypes.windll.user32.SetThreadDpiAwarenessContext
            fn.restype = ctypes.c_void_p
            fn.argtypes = [ctypes.c_void_p]
            self._fn = fn
            self._old = fn(ctypes.c_void_p(DPI_PMV2))
        except (AttributeError, OSError):  # Windows 10 1607보다 오래된 판
            self._old = None
        return self

    def __exit__(self, *_: object) -> None:
        import ctypes

        if self._old:
            self._fn(ctypes.c_void_p(self._old))


def read_monitors() -> list[Monitor]:
    """지금 연결된 모니터 영역들(물리 픽셀, 작업 영역·배율 포함). 읽지 못하면 빈 목록."""
    if sys.platform != "win32":
        return []
    try:
        with _PerMonitorDpi():
            monitors = _enum_monitors()
            if monitors:
                return monitors
            return _virtual_screen()
    except Exception:  # pragma: no cover - Windows API 실패는 드물다
        log.exception("모니터 정보를 읽지 못했습니다")
        return []


def app_window_monitor(
    monitors: Sequence[Monitor], title: str = APP_WINDOW_TITLE
) -> Monitor | None:
    """이 프로세스의 프로그램 창이 있는 모니터. 창이 없으면(개발용 브라우저 실행) None."""
    if sys.platform != "win32" or not monitors:
        return None
    try:
        with _PerMonitorDpi():
            rect = _app_monitor_rect(title)
    except Exception:  # pragma: no cover
        log.info("프로그램 창이 있는 모니터를 읽지 못했습니다")
        return None
    if rect is None:
        return None
    return next((m for m in monitors if (m.left, m.top, m.right, m.bottom) == rect), None)


def _monitor_info_type():  # pragma: no cover
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    return MONITORINFO


def _app_monitor_rect(title: str) -> tuple[int, int, int, int] | None:  # pragma: no cover
    import ctypes
    import os
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR,
                                     wintypes.LPCWSTR]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    pid = wintypes.DWORD()
    hwnd = user32.FindWindowExW(None, None, None, title)
    while hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            break
        hwnd = user32.FindWindowExW(None, hwnd, None, title)
    if not hwnd:
        return None
    hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    info_type = _monitor_info_type()
    info = info_type()
    info.cbSize = ctypes.sizeof(info_type)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return r.left, r.top, r.right, r.bottom


def _enum_monitors() -> list[Monitor]:  # pragma: no cover - 실제 모니터에 따라 다르다
    import ctypes
    from ctypes import wintypes

    MONITORINFO = _monitor_info_type()
    user32 = ctypes.windll.user32
    try:
        get_dpi = ctypes.windll.shcore.GetDpiForMonitor
    except (AttributeError, OSError):
        get_dpi = None
    found: list[Monitor] = []
    proc_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def callback(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r, w = info.rcMonitor, info.rcWork
            scale = 1.0
            if get_dpi is not None:
                dx, dy = ctypes.c_uint(), ctypes.c_uint()
                if get_dpi(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value:
                    scale = round(dx.value / 96, 3)  # MDT_EFFECTIVE_DPI
            found.append(Monitor(r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1),
                                 (w.left, w.top, w.right, w.bottom), scale))
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
