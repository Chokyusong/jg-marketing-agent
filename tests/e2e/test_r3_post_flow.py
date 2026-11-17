"""R3 e2e: 실제 게시가 기본 · [댓글 달기] 한 번으로 끝까지 · 광고 표기 켬/끔 · 연습 모드 한 번.

과제 PDF 흐름 그대로: ① 영상 불러오기 → ② 영상 고르기(초안이 자동으로) → ③ [댓글 달기] 한 번
→ 프로필 여는 중 → 입력 중 → 게시 완료 · [댓글 보기] → 기록.

- 실제 유튜브에 가지 않는다. 실제 게시 실행기는 가짜 YouTube 페이지만 연다(`r1_support`의
  `fake_youtube_driver`, 그 밖의 요청은 막는다). AI는 가짜 LLM, 유튜브 목록은 지어낸 응답.
- 창을 띄우지 않는다(headless). 1920×1009 · 1600×960에서 페이지가 스크롤되지 않는지도 잰다.
"""

from __future__ import annotations

import pytest
from r1_support import (
    DRAFT_TAG,
    JOB_STATE,
    PICK,
    WATCH,
    draft_for,
    headless_page,
    measure,
    r1_server,
    video_id,
    wait_draft,
)

pytestmark = pytest.mark.e2e

# ③ 작업 상자의 상태가 바뀔 때마다 모은다(게시 대기를 거치지 않았는지 본다)
WATCH_STATES = """() => {
  window.jgStates = [];
  const box = document.getElementById('job-box');
  new MutationObserver(() => {
    const s = box.dataset.state;
    if (window.jgStates[window.jgStates.length - 1] !== s) window.jgStates.push(s);
  }).observe(box, { attributes: true, attributeFilter: ['data-state'] });
}"""


@pytest.fixture
def live(tmp_path, make_config, fixture_json):
    with r1_server(tmp_path, make_config, fixture_json) as app:  # 설정 기본값 그대로
        yield app


def _load(page, base):
    page.goto(base + "/")
    page.click("#search-btn")
    page.wait_for_selector(f'.vid[data-id="{PICK}"]')


def _no_scroll(page) -> None:
    for w, h in ((1920, 1009), (1600, 960)):
        m = measure(page, w, h)
        assert not m["pageScroll"] and not m["hScroll"], (w, h, m["scrollHeight"])
    page.set_viewport_size({"width": 1920, "height": 1009})


def test_real_post_by_default_label_off_on_another_video_then_practice_once(live):
    base, youtube = live["base"], live["youtube"]
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.evaluate(WATCH_STATES)

        # ② 고르면 초안이 자동으로(광고 표기 붙음 = 설정 기본값)
        page.click(f'.vid[data-id="{PICK}"]')
        wait_draft(page, 2)
        assert page.is_checked("#disclose")

        # ③ 연습 모드는 꺼져 있다 = 실제 게시. [댓글 달기] 한 번으로 게시 완료까지
        assert not page.is_checked("#practice-mode")
        assert "실제 유튜브" in page.text_content("#practice-text")
        assert page.text_content("#job-primary") == "댓글 달기"
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
        states = page.evaluate("window.jgStates")
        assert "awaiting_approval" not in states, states
        assert "launching" in states and "typing" in states, states
        assert page.text_content("#exec-title") == "게시 완료 · 내 댓글 확인됨"
        assert page.text_content("#draft-tag") == "승인됨"
        assert page.is_visible("#job-view") and page.text_content("#job-view") == "댓글 보기"
        assert page.get_attribute("#job-view", "href") == WATCH + PICK  # 그 영상의 유튜브 주소
        page.wait_for_function("document.querySelectorAll('#records-body tr td.st').length >= 1")
        assert "성공" in page.text_content("#records-body")
        assert youtube["videos"] == [PICK]
        _no_scroll(page)

        # 다른 영상: 광고 표기를 끄고 다시 [댓글 달기] 한 번.
        # 가짜 LLM의 초안은 앞서 단 글과 93% 비슷해 V11(이전 글과 다름)에 걸린다 → 사람이 고쳐 쓴다
        other = video_id(4)
        page.evaluate("window.jgStates = []")
        page.click(f'.vid[data-id="{other}"]')
        page.wait_for_function(
            "(t) => document.getElementById('draft-text').value === t", arg=draft_for(4),
            timeout=30000)
        page.wait_for_function("!document.getElementById('disclose').disabled")
        page.uncheck("#disclose", force=True)
        page.wait_for_function(
            "() => !document.getElementById('draft-text').value.startsWith('[광고]')")
        bare = ("'하루에 한 번 연락'으로 싸웠다는 말에 오래 고개가 끄덕여지네요. "
                "요즘 운명원 얘기 많이 보이던데 연애 사주 한번 보고 싶어요.")
        page.fill("#draft-text", bare)  # 표기 끔 저장을 기다리지 않고 바로 고쳐 써도 글이 남는다
        page.wait_for_function(
            "(t) => document.getElementById('draft-text').value === t"
            " && document.getElementById('draft-tag').textContent === '검사 통과'", arg=bare,
            timeout=15000)
        assert not page.is_checked("#disclose")
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
        assert page.get_attribute("#job-view", "href") == WATCH + other
        assert "광고 표기 없음" in page.text_content("#exec-desc")
        page.wait_for_function(
            "[...document.querySelectorAll('#records-body [title]')]"
            ".some((n) => n.title.includes('광고 표기 없음'))", timeout=10000)
        assert youtube["videos"] == [PICK, other]

        # 연습 모드 한 번: 이 앱의 연습 페이지에 단다(유튜브는 열지 않는다)
        page.check("#practice-mode", force=True)
        page.click(f'.vid[data-id="{video_id(5)}"]')
        page.wait_for_function(
            "(t) => document.getElementById('draft-text').value === t", arg=draft_for(5),
            timeout=30000)
        assert page.is_checked("#disclose")  # 새 영상은 다시 설정 기본값(켬)
        practice = ("[광고] 영상 속 '하루에 한 번 연락'으로 싸웠다는 고백을 들으니 "
                    "서로 연락 기대치가 다를 때가 많다는 생각이 드네요. "
                    "주변에서 운명원 얘기 종종 하던데 연애 사주가 궁금해져요.")
        page.fill("#draft-text", practice)
        page.wait_for_function(DRAFT_TAG.format("검사 통과"), timeout=15000)
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
        assert page.get_attribute("#job-view", "href").startswith(f"{base}/sandbox/watch")
        assert youtube["videos"] == [PICK, other]
        _no_scroll(page)
    assert not errors, errors
    assert youtube["seen"] and all(u.startswith(WATCH) for u in youtube["seen"])


def test_failure_shows_reason_screenshot_and_retry(live):
    base, youtube = live["base"], live["youtube"]
    youtube["mode"] = "signed_out"  # 로그인 안 된 프로필
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.click(f'.vid[data-id="{PICK}"]')
        wait_draft(page, 2)
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("failed"), timeout=45000)
        assert page.is_visible("#job-error")
        reason = page.text_content("#job-error")
        assert "로그인" in reason and "[로그인하기]" in reason
        assert page.is_visible("#job-shot")  # [화면 캡처 보기]
        assert page.text_content("#job-primary") == "다시 시도"
        _no_scroll(page)
        # 로그인한 뒤(여기서는 가짜 페이지를 로그인 상태로) 다른 프로필로 다시 시도
        youtube["mode"] = "signed_in"
        page.select_option("#profile", "유튜브2")
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
    assert not errors, errors


@pytest.fixture
def confirm_live(tmp_path, make_config, fixture_json):
    with r1_server(tmp_path, make_config, fixture_json, confirm_before_post=True) as app:
        yield app


def test_confirm_before_post_stops_until_post_button(confirm_live):
    base, youtube = confirm_live["base"], confirm_live["youtube"]
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.click(f'.vid[data-id="{PICK}"]')
        wait_draft(page, 2)
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
        assert page.text_content("#job-primary") == "게시"
        assert youtube["videos"] == [PICK]
        _no_scroll(page)
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
        assert page.get_attribute("#job-view", "href") == WATCH + PICK
    assert not errors, errors


def test_auto_assignment_shows_profile_and_unchecked_profile_hint(live):
    """2026-11-17(PDF 대조): ③ 「자동 배정 · 이번에는 유튜브1」, 로그인 확인 안 한 프로필을 고르면
    [댓글 달기] 아래에 이유와 [프로필 화면에서 로그인]."""
    from app import db

    base = live["base"]
    services = live["app"].state.services.get()
    now = services.jobs.clock().isoformat()
    with db.session(services.settings.db_path) as conn:
        for name in ("유튜브1", "유튜브2"):
            conn.execute(
                "INSERT OR REPLACE INTO profile_logins(profile, state, channel, checked_at, note) "
                "VALUES (?, 'signed_in', '', ?, '')", (name, now))
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.wait_for_function(
            "document.querySelector('#profile option[value=\"\"]').textContent"
            " === '자동 배정 · 이번에는 유튜브1'", timeout=15000)
        assert page.is_hidden("#job-login")
        page.select_option("#profile", "유튜브3")
        page.wait_for_selector("#job-login", state="visible")
        assert page.text_content("#job-login-text") == "유튜브3은 아직 로그인을 확인하지 않았습니다"
        assert page.text_content("#job-login-btn") == "프로필 화면에서 로그인"
        _no_scroll(page)
        page.click("#job-login-btn")
        page.wait_for_selector("#screen-profiles", state="visible")
        # 연습 모드는 로그인이 필요 없다
        page.click("#nav-work")
        page.check("#practice-mode", force=True)
        page.wait_for_selector("#job-login", state="hidden")
    assert not errors, errors
