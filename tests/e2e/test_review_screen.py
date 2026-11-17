"""AI 검수·자료 상태 화면 손질 e2e(2026-11-18, 기획 담당이 스크린샷을 보고 고르게 한 네 가지).

1. ②칸 자료 줄(자막이 없을 때)과 AI 검수 안내는 두 줄까지 줄바꿈 — 「초안이 밋밋할 수 있어요」와
   검수가 든 문제까지 보인다. 1920×1009·1600×960에서 페이지 스크롤 없음은 그대로.
2. 문구: 영상에 자막이 없으면 「자막이 없어 …」, 자료 부족은 「자료 부족: 자막이 없고 …」.
3. 「다듬는 중」 동안 규칙 검사를 통과한 초안이 글 상자에 보인다(잠긴 채).
   [댓글 달기]는 검수가 끝난 뒤.
4. 1366×768: ①칸 배지가 잘리지 않고, 규칙 검사·AI 검수 줄이 ②칸 안에서 보인다.

유튜브는 지어낸 응답, AI는 가짜 LLM, AI 검수 답도 가짜(이 시험이 직접 정한다).
창 없는 크롬(headless).
"""

from __future__ import annotations

import threading

import pytest
from r1_support import (
    PICK,
    draft_for,
    headless_page,
    measure,
    r1_server,
    video_id,
)

from app.analysis import review
from app.transcript import auto

pytestmark = pytest.mark.e2e

FLAG = "'마음에 남네요' 다음에 운명원 얘기가 바로 나와 이어짐이 갑작스러움"
SLOW = 5   # 이 영상의 검수는 풀어 줄 때까지 붙잡는다
WARN = 3   # 이 영상의 검수는 「어색할 수 있어요」
REVIEW_SHOWN = ("() => { const r = document.getElementById('checks-review');"
                " return r && r.textContent; }")

# 글이 다 보이는가(줄바꿈 뒤에도 잘리지 않았는가): 글 높이가 상자 높이 안
FITS = ("(sel) => { const e = document.querySelector(sel);"
        " return e.scrollHeight <= e.clientHeight + 1; }")


class _Snip:
    def __init__(self, text: str, start: float) -> None:
        self.text, self.start = text, start


class _Track:
    language_code = "ko"
    is_generated = False

    def fetch(self):
        return [_Snip("오늘은 하루에 한 번 연락하는 커플 사연을 읽어 볼게요", 1.0),
                _Snip("연락 빈도가 달라서 서운함이 쌓였다고 하시네요", 6.0)]


@pytest.fixture
def live(tmp_path, make_config, fixture_json, monkeypatch):
    gate = threading.Event()
    real_parse = review.parse

    def fake_ask(llm, *, system, user):
        if f"영상 {SLOW}번" in user:
            gate.wait(timeout=30)
        if f"영상 {WARN}번" in user:
            return real_parse({"ok": False, "problems": [FLAG]})
        return real_parse({"ok": True, "problems": []})

    monkeypatch.setattr(review, "ask", fake_ask)
    # 1번 영상에만 지어낸 한국어 자막(「자막 있음」). 나머지는 자막이 없는 영상
    monkeypatch.setattr(auto, "default_lister", lambda timeout=10.0: (
        lambda vid: [_Track()] if vid == video_id(1) else []))
    with r1_server(tmp_path, make_config, fixture_json) as app:
        app["gate"] = gate
        try:
            yield app
        finally:
            gate.set()


def _pick(page, n: int, *, review_done: bool = True) -> None:
    page.click(f'.vid[data-id="{video_id(n)}"]')
    if review_done:
        page.wait_for_function(REVIEW_SHOWN, timeout=30000)


def _no_page_scroll(page) -> None:
    for w, h in ((1920, 1009), (1600, 960)):
        m = measure(page, w, h)
        assert not m["pageScroll"] and not m["hScroll"], (w, h, m)
        assert m["cols"]["col-analyze"]["overflow"] == 0, (w, h, m["cols"])
    page.set_viewport_size({"width": 1920, "height": 1009})


def test_draft_shows_while_review_runs_and_posting_waits(live):
    base = live["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.click("#search-btn")
        page.wait_for_selector(f'.vid[data-id="{video_id(SLOW)}"]')
        _pick(page, SLOW, review_done=False)
        page.wait_for_selector('#run-steps li[data-phase="review"].is-current', timeout=30000)
        # 규칙 검사를 통과한 초안이 글 상자에 보인다(읽을 수 있게).
        # 고칠 수는 없고 [댓글 달기]도 아직
        page.wait_for_function(
            "([t]) => document.getElementById('draft-text').value === t", arg=[draft_for(SLOW)])
        assert page.is_disabled("#draft-text")
        assert page.is_disabled("#job-primary") and page.is_disabled("#another-btn")
        assert "모두 통과" in page.text_content("#draft-checks")
        assert page.locator("#checks-review").count() == 0  # 검수 결과는 아직
        assert "is-reviewing" in page.get_attribute("#draft-edit", "class")
        assert float(page.evaluate(
            "getComputedStyle(document.getElementById('draft-edit')).opacity")) > 0.8

        live["gate"].set()
        page.wait_for_function(REVIEW_SHOWN, timeout=30000)
        assert page.text_content("#checks-review") == "AI 검수 통과"
        page.wait_for_function("!document.getElementById('job-primary').disabled")
        assert page.is_enabled("#draft-text")
        assert "is-reviewing" not in page.get_attribute("#draft-edit", "class")
        assert errors == []


def test_flagged_review_and_thin_material_lines_are_not_cut(live):
    base = live["base"]
    live["gate"].set()
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.click("#search-btn")
        page.wait_for_selector(f'.vid[data-id="{video_id(WARN)}"]')

        # 자료 부족(이 시험 영상: 자막 없음 + 짧은 설명 + 댓글 2개): 새 문구가 끝까지 보인다
        _pick(page, WARN)
        line = page.text_content("#ctx-transcript")
        assert line == ("자료 부족: 자막이 없고 설명·댓글도 거의 없어 제목만 읽었습니다. "
                        "초안이 밋밋할 수 있어요")
        assert "is-long" in page.get_attribute("#context-box", "class")
        assert page.evaluate(FITS, "#ctx-transcript")
        assert page.get_attribute("#ctx-transcript", "title") == line
        # 늘어난 높이는 접힌 「자막 직접 넣기」를 「인기 댓글」 줄 오른쪽에 붙여 되찾는다
        rows = page.evaluate("""() => {
          const c = document.getElementById('ctx-comments').getBoundingClientRect();
          const s = document.querySelector('#transcript-paste > summary').getBoundingClientRect();
          return { same: Math.abs((c.top + c.bottom) / 2 - (s.top + s.bottom) / 2) < 4,
                   right: s.left > c.left };
        }""")
        assert rows == {"same": True, "right": True}, rows
        page.click("#transcript-paste > summary")  # 펼치면 한 줄을 통째로(예전처럼)
        assert page.is_visible("#transcript-text")
        page.click("#transcript-paste > summary")

        # AI 검수 「어색할 수 있어요」: 문제 한 줄까지 다 보인다(다음 줄을 통째로, 두 줄까지)
        warn = page.text_content("#checks-review")
        assert warn == f"AI 검수: 어색할 수 있어요 — 읽고 고쳐 주세요 · {FLAG}"
        assert "is-warn" in page.get_attribute("#checks-review", "class")
        assert page.evaluate(FITS, "#checks-review")
        for w, h in ((1920, 1009), (1600, 960)):
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(100)
            assert page.evaluate(FITS, "#checks-review"), (w, h)
            assert page.evaluate(FITS, "#ctx-transcript"), (w, h)
        _no_page_scroll(page)
        assert page.text_content(f'.vid[data-id="{video_id(WARN)}"] .tbadge') == "자료 부족"
        assert errors == []


def test_narrow_1366_keeps_badges_whole_and_review_line_in_view(live):
    base = live["base"]
    live["gate"].set()
    with headless_page(base, size=(1366, 768)) as (page, errors):
        page.goto(base + "/")
        page.click("#search-btn")
        page.wait_for_selector(f'.vid[data-id="{PICK}"]')
        _pick(page, 2)
        _pick(page, 4)
        _pick(page, 1)
        page.wait_for_timeout(200)
        # ①칸 배지는 잘리지 않는다(날짜 줄 글이 대신 말줄임)
        badges = page.evaluate("""() => [...document.querySelectorAll('.vid .tbadge')].map((b) => {
          const meta = b.closest('.video-meta').getBoundingClientRect();
          const r = b.getBoundingClientRect();
          return { text: b.textContent, inside: r.right <= meta.right + 0.5,
                   whole: b.scrollWidth <= b.clientWidth + 1 };
        })""")
        assert len(badges) == 3, badges
        assert [b["text"] for b in badges] == ["자막 있음", "자료 부족", "자료 부족"], badges
        assert all(b["inside"] and b["whole"] for b in badges), badges
        # 규칙 검사·AI 검수 줄은 ②칸 안에서 스크롤 없이 보인다(글 상자 바로 아래로 올라온다)
        seen = page.evaluate("""() => {
          const body = document.querySelector('#col-analyze .col-body').getBoundingClientRect();
          const r = document.getElementById('checks-review').getBoundingClientRect();
          return { top: r.top, bottom: r.bottom, boxBottom: body.bottom };
        }""")
        assert seen["bottom"] <= seen["boxBottom"] + 0.5, seen
        assert not measure(page, 1366, 768)["pageScroll"]
        assert errors == []
