"""R1(프로그램형 화면) e2e 공용 도우미: 지어낸 유튜브, 가짜 LLM, 임시 앱 서버, 화면 재기.

- 유튜브는 지어낸 응답(httpx.MockTransport, 쇼츠 2개 포함 14개). 인터넷·키·Ollama 없이 돈다.
- 가짜 LLM은 부른 횟수를 센다(저장된 초안이 있으면 다시 부르지 않는지 본다).
  영상마다 다른 분석을 돌려준다. `gate`에 영상 번호를 넣으면 그 영상의 분석을
  풀어 줄 때까지 붙잡는다(영상을 바꾸면 결과가 섞이지 않는지 본다).
- 실제 유튜브에 가지 않는다(R3). 실제 게시는 창 없는 크롬이 `https://www.youtube.com/watch?...`를
  요청하면 테스트가 가로채 지어낸 페이지(`tests/fixtures/fake_youtube_watch.html`)를 돌려주고 나머지
  요청은 모두 막는다(`fake_youtube_driver`). 로그인 창용 크롬(`launcher`)은 부르면 실패한다.
  창도 띄우지 않는다(headless).
- 기본은 설정 그대로(실제 게시 · 게시 직전 확인 끔). 옛 시험은 `default_target="sandbox"`,
  `confirm_before_post=True`로 예전 흐름(연습 모드 · [게시]를 기다림)을 돌린다.
- R2: `user_dir`을 주면 그 임시 폴더에 설정을 저장한다(키 암호화는 가짜 `FAKE_PROTECTOR`).
  로그인 창 실행기·로그인 확인기는 가짜로 바꿔 끼울 수 있다(진짜 로그인 창을 열지 않는다).
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from app.browser.hooks import BrowserHooks
from app.browser.jobs import default_driver_factory
from app.browser.screens import Monitor
from app.browser.youtube_driver import PlaywrightYouTubeDriver
from app.config import load_settings
from app.desktop import ServerThread, open_listen_socket, wait_until_ready
from app.llm.base import LLMHealth
from app.main import create_app
from app.user_settings import Protector

FAKE_KEY_PREFIX = b"FAKE1"


def _fake_protect(data: bytes) -> bytes:
    return FAKE_KEY_PREFIX + bytes(b ^ 0x5A for b in data)


def _fake_unprotect(blob: bytes) -> bytes:
    if not blob.startswith(FAKE_KEY_PREFIX):
        raise ValueError("가짜 암호가 아님")
    return bytes(b ^ 0x5A for b in blob[len(FAKE_KEY_PREFIX):])


FAKE_PROTECTOR = Protector(protect=_fake_protect, unprotect=_fake_unprotect)

YT = "/youtube/v3/"
QUOTE = "하루에 한 번 연락으로 싸운 적 있어요"
PICK = "FITVIDEO002"
ENDINGS = ["좋겠어요", "괜찮겠어요", "어떨까 싶어요", "도움이 될 거예요"]
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


def video_id(n: int) -> str:
    return f"FITVIDEO{n:03d}"


def topic_for(n: int) -> str:
    return f"영상 {n}번의 연락 다툼 이야기"


def draft_for(n: int) -> str:
    ending = ENDINGS[n % len(ENDINGS)]
    return (f"[광고] '{QUOTE}'라는 댓글이 마음에 남네요. "
            f"운명원에서 연애 사주 상담을 받아 보셔도 {ending}")


def _videos() -> list[dict]:
    items = []
    for i, title in enumerate(TITLES, start=1):
        short = title.startswith("쇼츠")
        items.append({
            "kind": "youtube#video",
            "id": video_id(i),
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


def youtube_transport(fixture_json) -> httpx.MockTransport:
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
    """분석 요청에는 그 영상의 분석, 초안 요청에는 그 영상의 초안을 돌려주는 가짜 LLM.

    부른 횟수를 센다.
    """

    provider = "ollama"
    model = "fake-model"
    local = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []  # (analysis|draft, 영상 번호)
        self.gate: dict[int, threading.Event] = {}  # 영상 번호 → 풀어 줄 때까지 분석을 붙잡는다
        self._lock = threading.Lock()

    def _video(self, user: str) -> int:
        # 초안 요청에는 분석의 고민(「영상 n번: …」)이 들어 있다
        found = re.search(r"영상 (\d+)번", user)
        if found:
            return int(found.group(1))
        # 분석 요청은 프롬프트에 든 제목으로 알아낸다.
        # 긴 제목부터 맞춘다(짧은 제목이 긴 제목 안에 들 수 있다)
        for i, title in sorted(enumerate(TITLES, start=1), key=lambda p: -len(p[1])):
            if title in user:
                return i
        found = re.search(r"FITVIDEO(\d{3})", user)
        return int(found.group(1)) if found else 0

    def count(self, kind: str | None = None, n: int | None = None) -> int:
        with self._lock:
            return sum(1 for k, v in self.calls
                       if (kind is None or k == kind) and (n is None or v == n))

    def generate_json(self, *args, **kwargs):
        user = str(kwargs.get("user", ""))
        n = self._video(user)
        analysis = "evidence" in json.dumps(kwargs.get("schema", {}))
        with self._lock:
            self.calls.append(("analysis" if analysis else "draft", n))
        if analysis:
            gate = self.gate.get(n)
            if gate is not None:
                gate.wait(timeout=30)
            return {
                "topic": topic_for(n),
                "concern": f"영상 {n}번: 연락 빈도 차이로 자주 다투고 서운함을 말하지 못하는 커플",
                "tone": "진지한 사연 읽기",
                "viewer_needs": "연락 다툼을 줄이고 서운함을 전하는 말",
                "evidence": [{"quote": QUOTE, "source": "comment"}],
            }
        body = draft_for(n).removeprefix("[광고] ")
        return {"body": body, "used_quote": QUOTE, "tone_label": "공감형"}

    def health(self) -> LLMHealth:
        return LLMHealth("ollama", "fake-model", True, True, True)

    def list_models(self):  # R2: 설정 화면의 모델 고르기
        return [{"name": "fake-model:latest", "size": 4_700_000_000},
                {"name": "qwen2.5-coder:7b", "size": 4_400_000_000},
                {"name": "other-model:7b", "size": 4_100_000_000}]

    def warmup(self):
        raise AssertionError("warmup은 부르지 않는다")

    def close(self) -> None:
        pass


def _no_real_chrome(args):
    raise AssertionError(f"실제 유튜브용 크롬을 띄우려 했다: {args!r}")


FAKE_PAGE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_youtube_watch.html"
WATCH = "https://www.youtube.com/watch?v="


def fake_youtube(mode: str, seen: list[str]):
    """크롬 요청을 가로챈다: 영상 페이지는 가짜 페이지, 나머지는 모두 막는다."""
    html = FAKE_PAGE.read_text(encoding="utf-8").replace("__MODE__", mode)

    def prepare(ctx) -> None:
        def handle(route) -> None:
            url = route.request.url
            seen.append(url)
            if url.startswith(WATCH):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()

        ctx.route("**/*", handle)

    return prepare


def fake_youtube_driver(mode: str, seen: list[str], video_id: str, *,
                        headless: bool = True) -> PlaywrightYouTubeDriver:
    driver = PlaywrightYouTubeDriver(
        video_id=video_id, headless=headless, window_position=(60, -1060),
        prepare_context=fake_youtube(mode, seen),
    )
    driver.verify_timeout_ms = 1_500
    return driver


@contextmanager
def r1_server(tmp_path: Path, make_config, fixture_json, *, user_dir: Path | None = None,
              key: bool = True, launcher=None, login_checker=None,
              default_target: str | None = None,
              confirm_before_post: bool | None = None) -> Iterator[dict]:
    browser = {"headless": True, "typing_delay_ms": [2, 5],
               "screenshot_dir": str(tmp_path / "shots")}
    if default_target is not None:
        browser["default_target"] = default_target
    overrides: dict = {"limits": {"daily_max_comments": 10}, "browser": browser}
    if confirm_before_post is not None:
        overrides["posting"] = {"confirm_before_post": confirm_before_post}
    config = make_config(overrides)
    environ = {"JG_PROFILES_DIR": str(tmp_path / "profiles")}
    if key:
        environ["YOUTUBE_API_KEY"] = "AIza" + "x" * 35  # 가짜 키(실행할 때 조립)
    settings = load_settings(
        config, env_path=None, db_path=tmp_path / "r1.sqlite3", environ=environ,
        user_dir=user_dir, protector=FAKE_PROTECTOR if user_dir is not None else None,
    )
    drivers: list = []

    youtube = {"mode": "signed_in", "seen": [], "videos": []}

    def factory(browser_settings):
        driver = default_driver_factory(browser_settings)
        drivers.append(driver)
        return driver

    def youtube_factory(browser_settings, video):  # 가짜 유튜브 페이지만 연다
        assert browser_settings.headless is True
        youtube["videos"].append(video)
        driver = fake_youtube_driver(youtube["mode"], youtube["seen"], video)
        drivers.append(driver)
        return driver

    hooks = BrowserHooks(driver_factory=factory, youtube_driver_factory=youtube_factory,
                         launcher=launcher or _no_real_chrome,
                         login_checker=login_checker,
                         screens=lambda: [Monitor(0, 0, 1920, 1080, primary=True),
                                          Monitor(0, -1080, 1920, 0)])  # 위쪽 모니터
    llm = ScriptedLLM()

    def use_fake_llm(built) -> None:  # 설정을 저장해 서비스를 다시 만들어도 가짜 LLM
        built.llm = llm
        built.llm_error = None

    app = create_app(settings, transport=youtube_transport(fixture_json), browser_hooks=hooks,
                     on_build=use_fake_llm)
    app.state.services.get()  # 먼저 만들어 둔다(가짜 LLM을 끼운다)
    server = ServerThread(app, open_listen_socket())
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    assert wait_until_ready(base, timeout=20, is_alive=server.is_alive)
    try:
        yield {"base": base, "drivers": drivers, "llm": llm, "app": app, "youtube": youtube}
    finally:
        for gate in llm.gate.values():
            gate.set()
        app.state.services.get().jobs.shutdown(timeout=15)
        server.stop()
        # 실제 유튜브 주소로 나간 요청은 모두 가짜 페이지가 받았다(그 밖은 막았다)
        assert all(u.startswith(WATCH) for u in youtube["seen"] if "youtube.com" in u)


@contextmanager
def headless_page(base: str, size=(1920, 1009)):
    """창 없는 설치된 크롬. 바깥 주소(썸네일)는 부르지 않는다. 페이지 오류를 모은다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # 창 없이(주 모니터에 뜨지 않는다)
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base)
                   else route.abort())
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            yield page, errors
        finally:
            browser.close()


DRAFT_TAG = "document.getElementById('draft-tag').textContent === '{}'"
JOB_STATE = "document.getElementById('job-box').dataset.state === '{}'"


def wait_draft(page, n: int, timeout: int = 30000) -> None:
    """②의 글 상자에 n번 영상의 초안이 들어오고 규칙 검사를 통과할 때까지."""
    page.wait_for_function(
        "([text]) => document.getElementById('draft-text').value === text"
        " && document.getElementById('draft-tag').textContent === '검사 통과'",
        arg=[draft_for(n)], timeout=timeout)


# 화면 재기: 페이지 스크롤, 가로 넘침, 칸 머리 잘림, 칸 넘침, 스크롤하는 상자, 가장 작은 글자
MEASURE = """() => {
  const de = document.documentElement;
  const vh = window.innerHeight, vw = window.innerWidth;
  const rect = (el) => el.getBoundingClientRect();
  const visible = (el) => { const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length > 0; };
  const cols = {};
  for (const id of ['col-discover', 'col-analyze', 'col-execute']) {
    const col = document.getElementById(id);
    if (!visible(col)) { cols[id] = null; continue; }
    const box = col.querySelector('.col-body');
    const h2 = col.querySelector('.colhead h2');
    const c = rect(col), h = rect(h2);
    const hit = document.elementFromPoint(Math.min(vw - 1, h.left + 4), h.top + h.height / 2);
    cols[id] = {
      top: Math.round(c.top), bottom: Math.round(c.bottom), width: Math.round(c.width),
      overflow: Math.max(0, box.scrollHeight - box.clientHeight),
      colOverflow: Math.max(0, col.scrollHeight - col.clientHeight),
      headShown: h.top >= Math.max(0, c.top) - 0.5 && h.bottom <= Math.min(vh, c.bottom) + 0.5
        && h.right <= Math.min(vw, c.right) + 0.5 && h2.scrollWidth <= h2.clientWidth + 1
        && Boolean(hit && h2.contains(hit)),
    };
  }
  const list = document.getElementById('video-list');
  const scrollers = [];
  for (const el of document.querySelectorAll('.app, .app *')) {
    const s = getComputedStyle(el);
    const scrolls = (s.overflowY === 'auto' || s.overflowY === 'scroll')
      && el.scrollHeight > el.clientHeight + 1;
    if (scrolls && visible(el)) scrollers.push(el.id || el.className);
  }
  let min = 99, minAt = '';
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el) || el.closest('.sr-only')) continue;
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < min) { min = fs; minAt = (el.id ? '#' + el.id : el.className || el.tagName); }
  }
  const tall = (sel) => { let low = 999, at = '';
    for (const el of document.querySelectorAll(sel)) { if (!visible(el)) continue;
      const h = rect(el).height; if (h < low) { low = h; at = el.id || el.className; } }
    return { min: Math.round(low * 10) / 10, at }; };
  const bar = (sel) => {
    const n = document.querySelector(sel); return n ? Math.round(rect(n).height) : null; };
  const history = document.getElementById('activity');
  const hs = history && visible(history) ? rect(history) : null;
  return {
    viewport: [vw, vh], scrollHeight: de.scrollHeight, scrollWidth: de.scrollWidth,
    pageScroll: de.scrollHeight > vh || document.body.scrollHeight > vh,
    hScroll: de.scrollWidth > vw || document.body.scrollWidth > vw,
    topbar: bar('.topbar'), statusbar: bar('.statusbar'),
    rail: Math.round(rect(document.querySelector('.rail')).width),
    cols,
    list: { overflow: Math.max(0, list.scrollHeight - list.clientHeight),
            rows: list.querySelectorAll('.vid').length,
            height: Math.round(rect(list).height) },
    history: hs ? { bottom: Math.round(hs.bottom), inView: hs.bottom <= vh + 0.5,
                    rows: document.querySelectorAll('#records-body tr').length } : null,
    scrollers, minFont: min, minFontAt: minAt,
    buttons: tall('.btn:not(.btn-text), .field, select'),
    gold: [...document.querySelectorAll('.btn.is-next')].filter(visible).map((n) => n.id),
    tabs: visible(document.querySelector('.col-tabs')),
  };
}"""


def measure(page, w: int, h: int) -> dict:
    page.set_viewport_size({"width": w, "height": h})
    page.wait_for_timeout(150)
    return page.evaluate(MEASURE)
