"""한 화면 배치 e2e(R1 프로그램형 화면, UI_SPEC 4판 §9).

1080 모니터에서 최대화한 프로그램 창의 실제 화면은 1920×1009다(창 제목 줄·작업 표시줄을 뺀 높이).
1920×1009, 1903×1009(세로 스크롤 막대 폭만큼 좁은 창), 1600×960(기본 창), 1366×720,
1000×900(좁은 창 — 세 칸을 탭으로)에서

- 페이지 세로·가로 스크롤이 없다.
- 칸 머리(① 영상 불러오기 · ② 영상 선택 · ③ 댓글 달기)가 잘리지 않는다.
- 칸 전체가 넘치지 않는다(넘치면 칸 몸통 안에서만 스크롤한다).
- 1920×1009와 1600×960에서는 스크롤하는 곳이 ①의 영상 목록 한 곳뿐이다(②·③은 다 보인다).
- 가장 작은 글자 12px 이상, 단추·입력 칸 높이 36px 이상.
- 금색 채움 단추는 한 번에 하나뿐이다.

상태 두 가지로 잰다: (a) 영상 12개 + 하나 선택(자동 초안) + 고친 글이 규칙 검사 2건에 걸림,
(b) 연습 모드 게시가 진행 중(게시 직전 대기).

- 유튜브는 지어낸 응답, AI는 가짜 LLM. 인터넷·키·Ollama 없이 돈다.
  실제 유튜브용 크롬은 띄우지 않는다.
- 창을 띄우지 않는다(headless). 주 모니터에 창이 뜨지 않는다.
- `JG_FIT_REPORT=폴더`를 주면 크기별 측정값(JSON)과 화면 그림을 그 폴더에 남긴다
  (저장소 밖 임시 폴더를 준다).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from r1_support import (
    BAD_DRAFT,
    JOB_STATE,
    PICK,
    TITLES,
    headless_page,
    measure,
    r1_server,
    wait_draft,
)
from r1_support import MEASURE as MEASURE_FN

pytestmark = pytest.mark.e2e

WIDE = [(1920, 1009), (1903, 1009), (1600, 960), (1366, 720)]
NARROW = [(1000, 900)]
FULL = {(1920, 1009), (1600, 960)}  # 스크롤은 영상 목록 한 곳뿐이어야 하는 크기


@pytest.fixture
def fit_app(tmp_path, make_config, fixture_json):
    # 연습 모드 · [게시] 대기 화면까지 잰다(R3 기본 흐름의 화면 재기는 test_r3_post_flow.py)
    with r1_server(tmp_path, make_config, fixture_json, default_target="sandbox",
                   confirm_before_post=True) as app:
        yield app


def _measure_all(page, report: dict | None = None, name: str = "") -> dict:
    out = {}
    for w, h in WIDE + NARROW:
        out[f"{w}x{h}"] = m = measure(page, w, h)
        if (w, h) in NARROW:  # 좁은 창은 탭 세 개를 하나씩
            m["tabs_each"] = {}
            for n in (1, 2, 3):
                page.click(f'.col-tab[data-col="{n}"]')
                page.wait_for_timeout(80)
                m["tabs_each"][n] = page.evaluate(f"({MEASURE_FN})()")
            page.click('.col-tab[data-col="2"]')
        if report is not None and (w, h) in {(1920, 1009), (1600, 960)}:
            page.screenshot(path=str(Path(report["dir"]) / f"r1_{w}x{h}_{name}.png"))
    page.set_viewport_size({"width": 1920, "height": 1009})
    page.wait_for_timeout(100)
    return out


def _check_one(m: dict, where: str, full: bool) -> None:
    assert not m["pageScroll"], f"{where}: 페이지 세로 스크롤 {m['scrollHeight']}"
    assert not m["hScroll"], f"{where}: 가로 넘침 {m['scrollWidth']}"
    assert m["minFont"] >= 12, f"{where}: 글자 {m['minFont']}px ({m['minFontAt']})"
    assert m["buttons"]["min"] >= 36, f"{where}: 단추·입력 칸 높이 {m['buttons']}"
    assert len(m["gold"]) <= 1, f"{where}: 금색 단추가 여럿 {m['gold']}"
    for cid, col in m["cols"].items():
        if col is None:
            continue
        assert col["headShown"], f"{where}: {cid} 칸 머리가 잘림 {col}"
        assert col["colOverflow"] == 0, f"{where}: {cid} 칸 전체가 넘침 {col}"
    if full:
        extra = set(m["scrollers"]) - {"video-list"}
        assert not extra, f"{where}: 영상 목록 밖 스크롤 {m['scrollers']}"
        for cid in ("col-analyze", "col-execute"):
            assert m["cols"][cid]["overflow"] == 0, f"{where}: {cid} 넘침 {m['cols'][cid]}"


def _check(sizes: dict, state: str) -> None:
    for w, h in WIDE:
        m = sizes[f"{w}x{h}"]
        _check_one(m, f"{state} {w}x{h}", (w, h) in FULL)
        assert not m["tabs"], f"{state} {w}x{h}: 넓은 창인데 칸 탭이 보임"
        assert all(m["cols"].values()), f"{state} {w}x{h}: 세 칸이 다 보이지 않음"
    for w, h in NARROW:
        m = sizes[f"{w}x{h}"]
        assert m["tabs"], f"{state} {w}x{h}: 좁은 창인데 칸 탭이 없음"
        assert m["rail"] <= 60, f"{state} {w}x{h}: 왼쪽 줄이 아이콘만이 아님 {m['rail']}"
        for n, each in m["tabs_each"].items():
            shown = [cid for cid, col in each["cols"].items() if col]
            assert len(shown) == 1, f"{state} {w}x{h} 탭 {n}: 칸 {shown}"
            _check_one(each, f"{state} {w}x{h} 탭 {n}", False)


def test_program_screen_fits_without_page_scroll(fit_app):
    base = fit_app["base"]
    report_dir = os.environ.get("JG_FIT_REPORT")
    report = {"dir": report_dir} if report_dir else None
    if report_dir:
        Path(report_dir).mkdir(parents=True, exist_ok=True)
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        assert page.is_checked("#exclude-shorts")  # 「쇼츠 빼기」는 기본값(켬)으로 시작
        first = _measure_all(page)  # 처음 화면(목록 없음)
        _check(first, "처음")
        assert first["1920x1009"]["gold"] == ["search-btn"]

        # (a) 영상 12개 + 하나 선택(누르지 않아도 초안) + 고친 글이 규칙 검사 2건에 걸림
        page.click("#search-btn")
        page.wait_for_selector(f'.vid[data-id="{PICK}"]')
        assert page.locator(".vid").count() == 12
        assert "쇼츠 2개 뺌" in page.text_content("#result-meta")
        page.click(f'.vid[data-id="{PICK}"]')
        wait_draft(page, 2)
        page.fill("#draft-text", BAD_DRAFT)
        page.wait_for_function(
            "document.querySelectorAll('.checks-fail li').length === 2", timeout=15000)
        failing = _measure_all(page, report, "failing")
        _check(failing, "검사 실패")
        # 「자막 직접 넣기」를 펼쳐도 페이지가 아니라 ② 칸 안에서만 넘친다
        page.click("#transcript-paste > summary")
        opened = page.evaluate(MEASURE_FN)
        assert not opened["pageScroll"], opened
        assert opened["cols"]["col-analyze"]["colOverflow"] == 0, opened["cols"]
        page.click("#transcript-paste > summary")

        # 해시태그: 제목 본문과 뒤쪽 #태그를 나눠 그리고, 원문은 title 속성에 그대로
        row = page.locator(f'.vid[data-id="{PICK}"]')
        assert row.get_attribute("title") == TITLES[1]
        assert page.text_content(f'.vid[data-id="{PICK}"] .video-title') == TITLES[1]
        tags = page.text_content(f'.vid[data-id="{PICK}"] .video-title .title-tags') or ""
        assert tags.strip().startswith("#장거리연애")
        assert page.locator('.vid[data-id="FITVIDEO008"] .video-title .title-tags').count() == 0

        # (b) 연습 모드 게시가 진행 중(서버가 게시 직전에 기다림)
        page.click("#another-btn")
        page.wait_for_function(
            "document.getElementById('draft-tag').textContent === '검사 통과'", timeout=30000)
        assert page.is_checked("#practice-mode")
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
        waiting = _measure_all(page, report, "posting")
        _check(waiting, "게시 중")
        assert waiting["1920x1009"]["gold"] == ["job-primary"]

        if report_dir:
            (Path(report_dir) / "r1_fit_report.json").write_text(json.dumps(
                {"first": first, "failing": failing, "waiting": waiting},
                ensure_ascii=False, indent=1), encoding="utf-8")
        page.click("#job-primary")  # [게시]
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
    assert not errors, errors
    for driver in fit_app["drivers"]:
        for url in driver.visited:
            assert url.startswith(f"{base}/sandbox/"), url
