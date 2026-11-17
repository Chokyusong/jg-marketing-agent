"""R1 프로그램형 화면 e2e: 과제 PDF 흐름(① 영상 불러오기 → ② 영상 선택 → ③ 댓글 달기)을 끝까지.

- 영상을 고르면 단추를 누르지 않아도 초안이 나온다.
- 다른 영상으로 바꾸면 하던 결과가 섞이지 않는다(앞 영상의 분석이 늦게 와도 버린다).
- 이미 초안을 만든 영상은 모델을 다시 부르지 않는다(가짜 LLM 부른 횟수).
- [댓글 달기] 한 번이 초안 승인 API를 부르고 연습 모드 게시를 시작한다. 게시 직전에는 금색 [게시].
- 「영상 링크로 불러오기」로 불러온 영상은 바로 골라지고 초안이 나온다.
- 기록 · 프로필 · 설정 화면에 갔다 와도 작업 화면의 상태(고른 영상, 초안, 게시 결과)가 그대로다.

유튜브는 지어낸 응답, AI는 가짜 LLM. 창 없는 크롬(headless). 실제 유튜브는 열지 않는다.
"""

from __future__ import annotations

import threading

import pytest
from r1_support import (
    JOB_STATE,
    PICK,
    draft_for,
    headless_page,
    r1_server,
    topic_for,
    video_id,
    wait_draft,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def live(tmp_path, make_config, fixture_json):
    # 예전 흐름(연습 모드 · [게시]를 기다림)을 본다. R3 기본 흐름은 test_r3_post_flow.py
    with r1_server(tmp_path, make_config, fixture_json, default_target="sandbox",
                   confirm_before_post=True) as app:
        yield app


def _load(page, base):
    page.goto(base + "/")
    page.click("#search-btn")
    page.wait_for_selector(f'.vid[data-id="{PICK}"]')


def test_full_flow_select_auto_draft_one_click_post_and_screens_keep_state(live):
    base, llm = live["base"], live["llm"]
    approved: list[str] = []
    with headless_page(base) as (page, errors):
        def on_request(r):
            if r.method == "POST" and r.url.endswith("/approve"):
                approved.append(r.url)

        page.on("request", on_request)
        _load(page, base)
        # 목록이 뜨면 금색이 목록으로
        assert page.get_attribute("#search-btn", "class").count("is-next") == 0
        assert "목록에서 영상을 하나 고르세요" in page.text_content("#next-hint")
        # 올린 날짜는 날짜로(11.15), 몇 시간 전은 곁들임
        assert "11.15" in page.text_content(f'.vid[data-id="{PICK}"] .vid-day')

        # ② 고르기만 하면 자동으로 고민 한 줄과 초안
        page.click(f'.vid[data-id="{PICK}"]')
        wait_draft(page, 2)
        assert page.text_content("#an-topic") == topic_for(2)
        assert "영상 2번" in page.text_content("#an-concern")
        assert llm.count("analysis", 2) == 1 and llm.count("draft", 2) == 1
        assert "모두 통과" in page.text_content("#draft-checks")
        assert page.locator(".checks-fail li").count() == 0  # 통과면 한 줄로 접힌다
        # 2026-11-18 AI 검수 한 번: 「모두 통과」 옆 한 줄, 「다듬는 중」 단계를 거쳤다
        assert page.text_content("#checks-review") == "AI 검수 통과"
        assert "is-done" in page.get_attribute('#run-steps li[data-phase="review"]', "class")
        # 2026-11-18 자료가 얇은 영상: 자막이 없으면 ②에 알리고, ① 목록은 읽은 영상에만 배지
        assert "초안이 밋밋할 수 있어요" in page.text_content("#ctx-transcript")
        assert page.text_content(f'.vid[data-id="{PICK}"] .tbadge') == "자막 없음"
        assert page.locator(".vid .tbadge").count() == 1  # 안 읽은 영상에는 없다(미리 읽지 않음)

        # ③ [댓글 달기] 한 번 → 승인 API → 연습 모드 게시 시작 → 게시 직전 금색 [게시]
        assert page.is_checked("#practice-mode")
        assert page.text_content("#job-primary") == "댓글 달기"
        assert "is-next" in page.get_attribute("#job-primary", "class")
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
        assert any("/api/drafts/" in u and u.endswith("/approve") for u in approved), approved
        # 서버의 게시 승인은 아직(사람이 [게시])
        assert not any("/api/jobs/" in u for u in approved)
        assert page.text_content("#job-primary") == "게시"
        assert "is-next" in page.get_attribute("#job-primary", "class")
        assert page.text_content("#draft-tag") == "승인됨"
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("posted"), timeout=45000)
        assert page.text_content("#exec-title").startswith("게시 완료")
        assert page.is_visible("#job-view") and page.text_content("#job-view") == "댓글 보기"
        page.wait_for_function("document.querySelectorAll('#records-body tr td.st').length >= 1")
        assert "성공" in page.text_content("#records-body")
        page.wait_for_selector(f'.vid[data-id="{PICK}"] .commented')
        assert page.text_content(f'.vid[data-id="{PICK}"] .commented').startswith("댓글 달았음")
        draft_text = page.input_value("#draft-text")

        # 기록 화면: 오늘 숫자, 표, 거르기
        page.click("#nav-records")
        assert page.is_visible("#screen-records") and not page.is_visible("#screen-work")
        assert page.text_content("#screen-title") == "기록"
        # 2026-11-17(PDF 대조): 처음 거르기는 「게시」, 숫자는 실제 게시 기준, 연습은 「연습 n」
        assert page.is_checked('input[name="records-filter"][value="post"]')
        page.wait_for_function(
            "document.querySelectorAll('#records-all-body tr td.st').length >= 1")
        rows = page.locator("#records-all-body tr")
        assert rows.count() == 1 and "게시 완료" in rows.first.text_content()
        assert rows.first.locator(".kind").text_content() == "연습"
        assert "is-practice-row" in (rows.first.get_attribute("class") or "")
        assert "실제 게시 0건 · 연습 1건" in page.text_content("#records-all-meta")
        assert page.text_content("#stat-posted") == "0"  # 연습 게시는 실제 숫자에 넣지 않는다
        assert "실제 게시 기준" in page.text_content("#today-note")
        assert "연습 1" in page.text_content("#today-note")
        assert "연습 1" in page.text_content("#today-count")
        page.check('input[name="records-filter"][value="failure"]', force=True)
        assert "게시에 실패한 기록이 없습니다" in page.text_content("#records-all-body")
        page.check('input[name="records-filter"][value="all"]', force=True)
        page.wait_for_function(
            "document.querySelectorAll('#records-all-body tr td.st').length >= 3")

        # 프로필 화면(R2): 카드 세 장, 카드마다 [로그인하기] · [로그인 확인] · [유튜브 열기]
        page.click("#nav-profiles")
        page.wait_for_selector("#profiles-body .card")
        assert page.locator("#profiles-body .card").count() == 3
        assert page.locator("#profiles-body .card button").count() == 9
        assert page.locator("#profiles-body .card button:disabled").count() == 0
        assert "유튜브1" in page.text_content("#profiles-body")

        # 설정 화면(R2): 다섯 묶음, [저장]은 바꾼 칸이 생기면 켜진다
        page.click("#nav-settings")
        page.wait_for_selector("#settings-body .set-group")
        heads = page.locator("#settings-body .set-group h3").all_text_contents()
        assert heads == ["유튜브 연결", "AI 모델", "댓글 규칙", "게시", "영상 찾기",
                         "뜨기 직전 영상"]  # R4: 뜨기 직전 영상 조건
        assert page.is_disabled("#settings-save")
        assert page.is_enabled("#warmup-btn")

        # 아래 줄 상태를 누르면 해당 화면으로
        page.click("#today-item")
        assert page.is_visible("#screen-records")

        # 작업 화면으로 돌아오면 그대로
        page.click("#nav-work")
        assert page.is_visible("#screen-work")
        assert page.get_attribute(f'.vid[data-id="{PICK}"]', "aria-pressed") == "true"
        assert page.input_value("#draft-text") == draft_text
        assert page.text_content("#exec-title").startswith("게시 완료")
        assert llm.count() == 2  # 화면을 오가도 모델을 다시 부르지 않는다
    assert not errors, errors
    for driver in live["drivers"]:
        for url in driver.visited:
            assert url.startswith(f"{base}/sandbox/"), url


def test_switching_video_discards_late_result(live):
    base, llm = live["base"], live["llm"]
    gate = threading.Event()
    llm.gate[3] = gate  # 3번 영상의 분석은 풀어 줄 때까지 붙잡는다
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.click(f'.vid[data-id="{video_id(3)}"]')
        page.wait_for_function("() => document.querySelector('#run-steps li.is-current')")
        page.click(f'.vid[data-id="{video_id(4)}"]')
        wait_draft(page, 4)
        gate.set()  # 이제 3번의 분석이 늦게 온다
        page.wait_for_timeout(1500)
        assert page.text_content("#an-topic") == topic_for(4)
        assert page.input_value("#draft-text") == draft_for(4)
        assert llm.count("draft", 3) == 0  # 버린 영상의 초안은 만들지 않는다
        # 다시 3번을 고르면 저장된 분석으로 3번 초안만 만든다(분석은 다시 부르지 않는다)
        page.click(f'.vid[data-id="{video_id(3)}"]')
        wait_draft(page, 3)
        assert page.text_content("#an-topic") == topic_for(3)
        assert llm.count("analysis", 3) == 1
    assert not errors, errors


def test_stored_draft_is_shown_without_calling_model(live):
    base, llm = live["base"], live["llm"]
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.click(f'.vid[data-id="{video_id(5)}"]')
        wait_draft(page, 5)
        page.click(f'.vid[data-id="{video_id(6)}"]')
        wait_draft(page, 6)
        before = llm.count()
        page.click(f'.vid[data-id="{video_id(5)}"]')
        wait_draft(page, 5)
        assert "앞서 만든 초안" in page.text_content("#run-note")
        assert page.text_content("#an-topic") == topic_for(5)
        # 새로 고친 뒤에 골라도 같다
        _load(page, base)
        page.click(f'.vid[data-id="{video_id(6)}"]')
        wait_draft(page, 6)
        assert llm.count() == before
    assert not errors, errors


def test_link_input_selects_video_and_makes_draft(live):
    base = live["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.fill("#video-url", f"https://www.youtube.com/watch?v={video_id(9)}")
        page.click("#resolve-btn")
        page.wait_for_selector(f'.vid[data-id="{video_id(9)}"][aria-pressed="true"]')
        wait_draft(page, 9)
        assert "링크로 불러온 영상" in page.text_content("#result-meta")
        # 검색어 칸에 주소를 넣고 [영상 불러오기]를 눌러도 같다
        page.fill("#q", f"https://youtu.be/{video_id(10)}")
        page.click("#search-btn")
        page.wait_for_selector(f'.vid[data-id="{video_id(10)}"][aria-pressed="true"]')
        wait_draft(page, 10)
        assert page.locator(".vid").count() == 2  # 링크 영상은 목록 맨 위에 더한다
    assert not errors, errors


def test_post_button_blocked_with_reason_when_rules_fail(live):
    base = live["base"]
    with headless_page(base) as (page, errors):
        _load(page, base)
        page.click(f'.vid[data-id="{video_id(7)}"]')
        wait_draft(page, 7)
        page.fill("#draft-text", "[광고] 짧아요")
        page.wait_for_function(
            "document.querySelectorAll('.checks-fail li').length >= 1", timeout=15000)
        assert page.is_disabled("#job-primary")
        assert "규칙 검사에 걸린 항목" in page.text_content("#job-why")
        # 사람이 고친 글이 통과하면 [댓글 달기]가 고친 글을 먼저 저장하고 승인한다
        edited = draft_for(7).replace("마음에 남네요", "오래 마음에 남네요")
        patched: list[str] = []
        def on_request(r):
            if "/api/drafts/" in r.url and r.method == "PATCH":
                patched.append(r.method)

        page.on("request", on_request)
        page.fill("#draft-text", edited)
        page.wait_for_function("!document.getElementById('job-primary').disabled", timeout=15000)
        page.click("#job-primary")
        page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
        assert patched == ["PATCH"]
        assert page.input_value("#draft-text") == edited
        page.click("#job-cancel")
        page.wait_for_function(
            "document.getElementById('job-box').dataset.state === 'failed'", timeout=20000)
    assert not errors, errors
