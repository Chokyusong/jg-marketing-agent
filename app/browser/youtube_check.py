"""실제 유튜브 화면 요소 점검(R3) — **읽기만** 한다.

`scripts/check_youtube_page.py`가 쓴다. 영상 페이지를 열어 `youtube_driver.SELECTORS`의 요소
(로그인 표시, 「로그인」 단추, 댓글 영역, 댓글 입력 자리, 글 입력 칸, 「댓글」 게시 단추,
달린 댓글)가 잡히는지 보고 표로 돌려준다.

- 아무것도 입력하거나 누르지 않는다. 댓글은 아래로 내려야 불러오므로 마우스 휠로 내리기만 한다.
- 글 입력 칸과 「댓글」 게시 단추는 「댓글 추가...」를 눌러야 생긴다. 누르지 않으므로
  "눌러야 보임 — 실제 게시 때 확인"으로 표시한다(이미 그려져 있으면 「찾음」).
- 페이지가 그 영상 밖으로 옮겨 가면 거기서 멈추고 그렇게 적는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.browser.youtube_driver import (
    FIND_BOX_TRIES,
    LABELS,
    SCROLL_PAUSE_MS,
    SCROLL_PX,
    SELECTORS,
    SIGN_IN_WAIT_MS,
    YouTubeSelectors,
    may_stay,
)

FOUND = "찾음"
MISSING = "못 찾음"
ABSENT_OK = "없음(정상)"
NEEDS_CLICK = "눌러야 보임 — 실제 게시 때 확인"
NOT_APPLICABLE = "해당 없음"

LOGIN_SIGNED_IN = "로그인됨"
LOGIN_SIGNED_OUT = "로그인 안 됨"
LOGIN_UNKNOWN = "모름(로그인 표시를 못 찾음)"


@dataclass(frozen=True)
class CheckRow:
    key: str  # SELECTORS의 칸 이름
    label: str  # 사람이 읽는 이름
    selector: str
    result: str  # FOUND | MISSING | ABSENT_OK | NEEDS_CLICK | NOT_APPLICABLE
    note: str = ""


@dataclass(frozen=True)
class PageCheck:
    url: str
    final_url: str
    login: str  # LOGIN_*
    rows: tuple[CheckRow, ...]
    left_page: bool = False
    scrolls: int = 0

    def row(self, key: str) -> CheckRow:
        return next(r for r in self.rows if r.key == key)


def _count(page: Any, selector: str) -> int:
    try:
        return int(page.locator(selector).count())
    except Exception:
        return 0


def _visible(page: Any, selector: str) -> bool:
    try:
        return bool(page.locator(selector).first.is_visible())
    except Exception:
        return False


def inspect_page(
    page: Any,
    video_id: str,
    *,
    selectors: YouTubeSelectors = SELECTORS,
    tries: int = FIND_BOX_TRIES,
    pause_ms: int = SCROLL_PAUSE_MS,
    sign_wait_ms: int = SIGN_IN_WAIT_MS,
) -> PageCheck:
    """이미 영상 페이지로 간 `page`에서 요소를 찾아 표를 만든다(누르지 않는다)."""
    sel = selectors
    url = page.url
    try:
        page.wait_for_selector(
            f"{sel.signed_in}, {sel.sign_in}", state="attached", timeout=sign_wait_ms
        )
    except Exception:
        pass
    signed_in = _count(page, sel.signed_in) > 0
    sign_in = _count(page, sel.sign_in) > 0
    login = LOGIN_SIGNED_IN if signed_in else LOGIN_SIGNED_OUT if sign_in else LOGIN_UNKNOWN

    scrolls = 0
    left = False
    for _ in range(tries):
        if not may_stay(page.url, video_id):
            left = True
            break
        if _visible(page, sel.placeholder) or _count(page, sel.comments_off) > 0:
            break
        page.mouse.wheel(0, SCROLL_PX)
        page.wait_for_timeout(pause_ms)
        scrolls += 1

    comments = _count(page, sel.comments) > 0
    placeholder = _visible(page, sel.placeholder)
    placeholder_attached = _count(page, sel.placeholder) > 0
    comments_off = _count(page, sel.comments_off) > 0
    editor = _count(page, sel.editor) > 0
    submit = _count(page, sel.submit) > 0
    written = _count(page, sel.comment_text)

    def row(key: str, result: str, note: str = "") -> CheckRow:
        return CheckRow(key, LABELS[key], getattr(sel, key), result, note)

    rows = [
        row("signed_in", FOUND if signed_in else (MISSING if not sign_in else NOT_APPLICABLE),
            "" if signed_in else "로그인하지 않은 프로필에는 없습니다" if sign_in else ""),
        row("sign_in", FOUND if sign_in else (NOT_APPLICABLE if signed_in else MISSING),
            "로그인한 프로필에는 없습니다" if signed_in else ""),
        row("comments", FOUND if comments else MISSING,
            "" if comments else f"{scrolls}번 내려도 나오지 않았습니다"),
        row("comments_off", FOUND if comments_off else ABSENT_OK,
            "이 영상은 댓글이 막혀 있습니다" if comments_off else ""),
    ]
    if comments_off:
        rows.append(row("placeholder", NOT_APPLICABLE, "댓글이 막힌 영상"))
    elif placeholder:
        rows.append(row("placeholder", FOUND))
    else:
        note = "있지만 화면에 보이지 않습니다" if placeholder_attached else ""
        rows.append(row("placeholder", MISSING, note))
    rows.append(row("editor", FOUND if editor else NEEDS_CLICK,
                    "" if editor else "「댓글 추가...」를 눌러야 생깁니다(누르지 않음)"))
    rows.append(row("submit", FOUND if submit else NEEDS_CLICK,
                    "" if submit else "「댓글 추가...」를 눌러야 생깁니다(누르지 않음)"))
    rows.append(row("comment_text", FOUND if written else MISSING if comments else NOT_APPLICABLE,
                    f"{written}개" if written else ""))
    return PageCheck(url=url, final_url=page.url, login=login, rows=tuple(rows),
                     left_page=left, scrolls=scrolls)


def format_table(check: PageCheck) -> str:
    """사람이 읽는 표(터미널)."""
    lines = [
        f"영상 주소: {check.url}",
        f"로그인: {check.login}",
        f"아래로 내린 횟수: {check.scrolls}",
    ]
    if check.left_page:
        lines.append(f"주의: 페이지가 이 영상 밖으로 옮겨 가 멈췄습니다 → {check.final_url}")
    widths = (34, 46, 30)
    head = ("요소", "요소 이름", "결과")
    lines.append("")
    lines.append(" | ".join(h.ljust(w) for h, w in zip(head, widths, strict=True)) + " | 설명")
    lines.append("-" * 130)
    for r in check.rows:
        cells = (r.label, r.selector, r.result)
        lines.append(" | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))
                     + f" | {r.note}")
    return "\n".join(lines)
