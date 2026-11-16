"""한 화면 배치 e2e(2026-11-17): 프로그램 창을 최대화하면 페이지 스크롤 없이 다 보인다.

1080 모니터에서 최대화한 프로그램 창의 실제 화면은 1920×1009다(창 제목 줄·작업 표시줄을 뺀 높이).
그 크기와 프로그램 창 기본 크기의 안쪽(1600×960)에서

- 페이지 세로·가로 스크롤이 없다(`scrollHeight <= innerHeight`).
- 01칸 제목 「영상 탐색」이 칸 맨 위에 온전히 보인다(흐름 띠 아래로 잘리지 않는다).
- 스크롤은 01칸의 영상 목록 한 곳뿐이다(02·03칸은 넘치지 않는다).
- 작업 기록 띠가 화면 안에 있다.
- 가장 작은 글자가 11.5px 이상이다.

상태 두 가지로 잰다: (a) 영상 12개 + 하나 선택 + 초안이 규칙 검사 2건에 걸림,
(b) 테스트 페이지 작업이 승인 대기 중.

- 유튜브는 지어낸 응답(httpx.MockTransport, 쇼츠 2개 포함 14개), AI는 가짜 LLM.
  인터넷·키·Ollama 없이 돈다. 실제 유튜브용 크롬은 띄우지 않는다.
- 창을 띄우지 않는다(headless). 주 모니터에 창이 뜨지 않는다.
- `JG_FIT_REPORT=폴더`를 주면 크기별 측정값(JSON)과 1920×1009 화면 그림을 그 폴더에 남긴다
  (저장소 밖 임시 폴더를 준다).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.screens import Monitor
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.llm.base import LLMHealth
from app.main import create_app

pytestmark = pytest.mark.e2e

YT = "/youtube/v3/"
QUOTE = "하루에 한 번 연락으로 싸운 적 있어요"
PICK = "FITVIDEO002"
ANALYSIS = {
    "topic": "장거리 연애 연락 문제와 서운함을 말하는 방법",
    "concern": "연락 빈도 차이로 자주 다투고 서운함을 말하지 못하는 장거리 커플",
    "tone": "진지한 사연 읽기",
    "viewer_needs": "연락 다툼을 줄이고 서운함을 전하는 말",
    "evidence": [{"quote": QUOTE, "source": "comment"}],
}
DRAFT = {
    "body": f"'{QUOTE}'라는 댓글이 마음에 남네요. "
    "운명원에서 연애 사주 상담을 받아 보셔도 좋겠어요.",
    "used_quote": QUOTE,
    "tone_label": "공감형",
}
# 규칙 검사 두 건(V1 한 줄 아님, V2 링크)에 걸리는 글
BAD_DRAFT = (f"[광고] '{QUOTE}'라는 말에 공감해요." + chr(10)
             + "운명원 상담도 한번 보세요 https://example.com/a")

TITLES = [
    "순애남들은 이런 여자들을 좋아합니다 #남자심리 #연애심리 #썸 #인팁특징 #20대 #30대 #연애",
    "장거리 연애 1년차, 연락 문제로 자주 싸워요 #장거리연애 #연애고민 #커플 #연애상담 #사연",
    "11월 16일 고민상담 (mbti, 인생, 연애, whatever)",
    "애인이 \"서운한 거 있어\" 할 때 싸움 안 나는 한마디",
    "좋은 남자를 만나고 싶다면 나부터 돌아볼 것 #남자심리 #연애심리 #썸 #MBTI특징 #20대 #30대",
    "왜 매번 이상한 남자만 만나는 걸까?? #남자심리 #연애심리 #썸 #인팁특징 #INTP남자 #20대",
    "AI한테 연애 물어보면 망하는 이유 (+ 잘 쓰는 법) #연애상담 #AI #재회상담 #연애 #연애세포",
    "#연애 #고민 #상담",
    "헤어진 연인에게 다시 연락해도 될까? 재회 상담 사연 읽기",
    "연애 초반에 꼭 확인해야 할 세 가지 #연애초반 #연애팁 #썸 #20대연애",
    "결혼 전에 꼭 나눠야 하는 대화, 돈과 가족 이야기",
    "썸 탈 때 연락 빈도, 얼마가 적당할까? #썸 #연락 #연애심리 #20대 #30대 #연애",
    "쇼츠 하나 #shorts",
    "쇼츠 둘 #shorts #연애",
]


def _videos() -> list[dict]:
    items = []
    for i, title in enumerate(TITLES, start=1):
        short = title.startswith("쇼츠")
        items.append({
            "kind": "youtube#video",
            "id": f"FITVIDEO{i:03d}",
            "snippet": {
                "publishedAt": f"2026-11-{17 - i % 6:02d}T0{i % 9}:00:00Z",
                "channelId": f"UCfitchannel{i:012d}",
                "title": title,
                "description": "연애 고민 사연을 읽고 이야기합니다.",
                "thumbnails": {},
                "channelTitle": f"연애상담 채널 {i}",
            },
            "contentDetails": {"duration": "PT45S" if short else f"PT{3 + i}M{i:02d}S"},
            "statistics": {"viewCount": str(1200 * i + 37), "likeCount": "10", "commentCount": "5"},
        })
    return items


def _youtube(fixture_json):
    videos = _videos()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"{YT}search":
            return httpx.Response(200, json={
                "kind": "youtube#searchListResponse",
                "pageInfo": {"totalResults": len(videos), "resultsPerPage": len(videos)},
                "items": [{"kind": "youtube#searchResult",
                           "id": {"kind": "youtube#video", "videoId": v["id"]}} for v in videos],
            })
        if path == f"{YT}videos":
            wanted = set(request.url.params.get("id", "").split(","))
            return httpx.Response(200, json={
                "kind": "youtube#videoListResponse",
                "items": [v for v in videos if v["id"] in wanted],
            })
        if path == f"{YT}commentThreads":
            return httpx.Response(200, json=fixture_json("youtube/comment_threads.json"))
        return httpx.Response(404, json={"error": {"message": "not in fixture"}})

    return httpx.MockTransport(handler)


class ScriptedLLM:
    """분석 요청에는 분석, 그 밖에는 초안을 돌려주는 가짜 LLM."""

    provider = "ollama"
    model = "fake-model"
    local = True

    def generate_json(self, *args, **kwargs):
        return dict(ANALYSIS) if "evidence" in json.dumps(kwargs.get("schema", {})) else dict(DRAFT)

    def health(self) -> LLMHealth:
        return LLMHealth("ollama", "fake-model", True, True, True)

    def warmup(self):
        raise AssertionError("warmup은 부르지 않는다")

    def close(self) -> None:
        pass


def _no_real_chrome(args):
    raise AssertionError(f"실제 유튜브용 크롬을 띄우려 했다: {args!r}")


@pytest.fixture
def fit_app(tmp_path: Path, make_config, fixture_json) -> Iterator[dict]:
    config = make_config({
        "limits": {"daily_max_comments": 10},
        "browser": {"headless": True, "typing_delay_ms": [2, 5],
                    "screenshot_dir": str(tmp_path / "shots")},
    })
    settings = load_settings(
        config, env_path=None, db_path=tmp_path / "fit.sqlite3",
        environ={"YOUTUBE_API_KEY": "AIza" + "x" * 35,  # 가짜 키(실행할 때 조립)
                 "JG_PROFILES_DIR": str(tmp_path / "profiles")},
    )
    drivers: list = []

    def factory(browser_settings):
        driver = default_driver_factory(browser_settings)
        drivers.append(driver)
        return driver

    hooks = BrowserHooks(driver_factory=factory, launcher=_no_real_chrome,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True)])
    app = create_app(settings, transport=_youtube(fixture_json), browser_hooks=hooks)
    services = app.state.services.get()
    services.llm = ScriptedLLM()
    server = ServerThread(app, open_listen_socket())
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
    try:
        yield {"base": base, "drivers": drivers}
    finally:
        services.jobs.shutdown(timeout=15)
        server.stop()


# 페이지 하나에서 잰다. 넓은 화면의 세 칸·영상 목록·작업 기록 띠, 글자 크기, 넘침
MEASURE = """() => {
  const de = document.documentElement;
  const vh = window.innerHeight, vw = window.innerWidth;
  const rect = (el) => el.getBoundingClientRect();
  const visible = (el) => { const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const cols = {};
  for (const id of ['col-discover', 'col-analyze', 'col-execute']) {
    const col = document.getElementById(id);
    const box = col.querySelector('.col-body') || col;
    const h2 = col.querySelector('.colhead h2');
    const c = rect(col), h = rect(h2);
    const hit = document.elementFromPoint(Math.min(vw - 1, h.left + 4), h.top + h.height / 2);
    cols[id] = {
      top: Math.round(c.top), bottom: Math.round(c.bottom),
      overflow: Math.max(0, box.scrollHeight - box.clientHeight),
      colOverflow: Math.max(0, col.scrollHeight - col.clientHeight),
      titleTop: Math.round(h.top), titleBottom: Math.round(h.bottom),
      titleShown: h.top >= Math.max(0, c.top) - 0.5 && h.bottom <= Math.min(vh, c.bottom) + 0.5
        && Boolean(hit && h2.contains(hit)),
    };
  }
  const list = document.getElementById('video-list');
  const act = document.getElementById('activity');
  const a = rect(act);
  const scrollers = [];
  for (const el of document.querySelectorAll('.workspace, .workspace *')) {
    const s = getComputedStyle(el).overflowY;
    if ((s === 'auto' || s === 'scroll') && el.scrollHeight > el.clientHeight + 1 && visible(el)) {
      scrollers.push(el.id || el.className);
    }
  }
  let min = 99, minAt = '';
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el) || el.closest('dialog:not([open])') || el.closest('.sr-only')) continue;
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < min) { min = fs; minAt = (el.id ? '#' + el.id : el.className || el.tagName); }
  }
  const pageSize = (sel) => { const n = document.querySelector(sel);
    return n ? parseFloat(getComputedStyle(n).fontSize) : null; };
  const head = Math.round(rect(document.querySelector('.progress')).bottom);
  return {
    viewport: [vw, vh], scrollHeight: de.scrollHeight, scrollWidth: de.scrollWidth,
    pageScroll: de.scrollHeight > vh, hScroll: de.scrollWidth > vw,
    head, cols,
    list: { overflow: Math.max(0, list.scrollHeight - list.clientHeight),
            rows: list.querySelectorAll('.vid').length },
    activity: { top: Math.round(a.top), bottom: Math.round(a.bottom), inView: a.bottom <= vh + 0.5,
                rows: document.querySelectorAll('#records-body tr').length },
    scrollers, minFont: min, minFontAt: minAt,
    fonts: { body: pageSize('body'), listTitle: pageSize('.vid .video-title'),
             meta: pageSize('.vid .video-meta'), dd: pageSize('.report .analysis dd') },
  };
}"""

WIDE = [(1920, 1009), (1903, 1009), (1600, 960), (1366, 720)]
# 1084×681: 프로그램 창 최소 크기(1100×720, app/desktop.py)의 안쪽. 1121px 미만이라 세로로 쌓는다
NARROW = [(1084, 681), (1000, 900), (390, 844)]
DRAFT_TAG = "document.getElementById('draft-tag').textContent === '{}'"
JOB_STATE = "document.getElementById('job-box').dataset.state === '{}'"


def _measure_all(page) -> dict:
    out = {}
    for w, h in WIDE + NARROW:
        page.set_viewport_size({"width": w, "height": h})
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        out[f"{w}x{h}"] = page.evaluate(MEASURE)
    page.set_viewport_size({"width": 1920, "height": 1009})
    page.wait_for_timeout(100)
    return out


def _check(sizes: dict, state: str) -> None:
    for w, h in WIDE:
        m = sizes[f"{w}x{h}"]
        where = f"{state} {w}x{h}"
        assert not m["pageScroll"], f"{where}: 페이지 세로 스크롤 {m['scrollHeight']} > {h}"
        assert not m["hScroll"], f"{where}: 가로 넘침 {m['scrollWidth']} > {w}"
        assert m["cols"]["col-discover"]["titleShown"], f"{where}: 01칸 제목이 잘림 {m['cols']}"
        for col in m["cols"].values():
            assert col["colOverflow"] == 0, f"{where}: 칸 전체가 넘침(이중 스크롤) {m['cols']}"
        assert m["activity"]["inView"], f"{where}: 작업 기록 띠가 화면 밖 {m['activity']}"
        assert m["minFont"] >= 11.5, f"{where}: 글자 {m['minFont']}px ({m['minFontAt']})"
        if h >= 960:  # 최대화한 창·기본 창: 스크롤은 영상 목록 한 곳뿐, 02·03칸은 다 보인다
            assert set(m["scrollers"]) <= {"video-list"}, f"{where}: {m['scrollers']}"
            for cid in ("col-analyze", "col-execute"):
                assert m["cols"][cid]["overflow"] == 0, f"{where}: {cid} 넘침 {m['cols'][cid]}"
    for w, h in NARROW:
        m = sizes[f"{w}x{h}"]
        assert not m["hScroll"], f"{state} {w}x{h}: 가로 넘침 {m['scrollWidth']} > {w}"
        assert m["minFont"] >= 11.5, f"{state} {w}x{h}: 글자 {m['minFont']}px ({m['minFontAt']})"


def test_maximized_window_fits_one_screen_without_page_scroll(fit_app, tmp_path):
    from playwright.sync_api import sync_playwright

    base = fit_app["base"]
    report_dir = os.environ.get("JG_FIT_REPORT")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # 창 없이
        page = browser.new_page(viewport={"width": 1920, "height": 1009})
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                   else route.abort())  # 바깥 주소(썸네일)는 부르지 않는다
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(base + "/")
            # 「쇼츠 제외」는 config.yaml 기본값(켬)으로 시작한다
            assert page.is_checked("#exclude-shorts")
            first = _measure_all(page)  # 처음 화면(목록 없음)
            _check(first, "처음")

            # (a) 영상 12개 + 하나 선택 + 초안이 규칙 검사 2건에 걸림
            page.click("#search-btn")
            page.wait_for_selector(f'.vid[data-id="{PICK}"]')
            assert page.locator(".vid").count() == 12
            assert "쇼츠 2개 제외" in page.text_content("#result-meta")
            page.click(f'.vid[data-id="{PICK}"]')
            page.wait_for_function("!document.getElementById('run-btn').disabled")
            page.click("#run-btn")
            page.wait_for_function(DRAFT_TAG.format("CHECKED"), timeout=30000)
            page.fill("#draft-text", BAD_DRAFT)
            page.wait_for_function("document.querySelectorAll('.checks-fail li').length === 2",
                                   timeout=15000)
            failing = _measure_all(page)
            _check(failing, "검사 실패")
            if report_dir:
                Path(report_dir).mkdir(parents=True, exist_ok=True)
                for w, h in ((1920, 1009), (1600, 960), (1366, 720)):
                    page.set_viewport_size({"width": w, "height": h})
                    page.wait_for_timeout(100)
                    page.screenshot(path=str(Path(report_dir) / f"fit_{w}x{h}_failing.png"))
                page.set_viewport_size({"width": 1920, "height": 1009})
            # 자막 붙여넣기를 펼쳐도 페이지가 아니라 02칸 안에서만 넘친다
            page.click("#transcript-paste > summary")
            opened = page.evaluate(MEASURE)
            assert not opened["pageScroll"], opened
            assert opened["cols"]["col-analyze"]["colOverflow"] == 0, opened["cols"]
            page.click("#transcript-paste > summary")

            # 해시태그: 제목 본문과 뒤쪽 #태그를 나눠 그리고, 원문은 title 속성에 그대로
            row = page.locator(f'.vid[data-id="{PICK}"]')
            assert row.get_attribute("title") == TITLES[1]
            assert page.text_content(f'.vid[data-id="{PICK}"] .video-title') == TITLES[1]
            tags = page.text_content(f'.vid[data-id="{PICK}"] .video-title .title-tags') or ""
            assert tags.strip().startswith("#장거리연애")
            only_tags = page.locator('.vid[data-id="FITVIDEO008"] .video-title .title-tags')
            assert only_tags.count() == 0  # 제목이 해시태그뿐이면 그대로

            # (b) 테스트 페이지 작업이 승인 대기 중
            page.fill("#draft-text", "")
            page.click("#another-btn")
            page.wait_for_function(DRAFT_TAG.format("CHECKED"), timeout=30000)
            page.click("#approve-btn")
            page.wait_for_function(DRAFT_TAG.format("APPROVED"))
            page.check('input[name="mode"][value="sandbox"]', force=True)
            page.click("#job-primary")
            page.wait_for_function(JOB_STATE.format("awaiting_approval"), timeout=45000)
            waiting = _measure_all(page)
            _check(waiting, "승인 대기")

            if report_dir:
                out = Path(report_dir)
                out.mkdir(parents=True, exist_ok=True)
                page.set_viewport_size({"width": 1920, "height": 1009})
                page.screenshot(path=str(out / "fit_1920x1009_waiting.png"))
                (out / "fit_report.json").write_text(json.dumps(
                    {"first": first, "failing": failing, "waiting": waiting},
                    ensure_ascii=False, indent=1), encoding="utf-8")
        finally:
            browser.close()
    assert not errors, errors
    for driver in fit_app["drivers"]:
        for url in driver.visited:
            assert url.startswith(f"{base}/sandbox/"), url
