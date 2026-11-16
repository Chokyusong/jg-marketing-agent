"""R2 화면 e2e: 설정 화면에서 바꾸고 저장 → 작업 화면에 반영 → 서비스를 다시 만들어도 남음 →
[기본값으로]. API 키를 넣으면 「저장됨」만 보이고 값은 어디에도 없다. 시작 준비 상자 세 줄과
사라짐. 프로필 화면의 단추가 API를 부른다. 설정·프로필 화면이 1920×1009 · 1600×960에서 페이지
스크롤 없이 들어간다.

- 창 없는(headless) 설치된 크롬. 유튜브는 지어낸 응답, AI는 가짜 LLM. 인터넷·키·Ollama 없이 돈다.
- 사용자 설정 폴더는 임시 폴더, 키 암호화는 가짜(`FAKE_PROTECTOR`).
  이 PC의 %LOCALAPPDATA%를 건드리지 않는다.
- 로그인 창 실행기와 로그인 확인기는 가짜다. 진짜 크롬 로그인 창을 열지 않고 구글에 접속하지 않는다.
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest
from r1_support import headless_page, measure, r1_server

from app.browser.login import HOME_URL, LOGIN_URL, LoginResult

pytestmark = pytest.mark.e2e

STATUS_LOADED = "document.getElementById('status-youtube').textContent !== '확인 중'"
SETTINGS_LOADED = "document.querySelector('#settings-body .set-group') !== null"
FOCUSED = "document.activeElement && document.activeElement.id === '{}'"
LOGIN_STATE = "document.querySelector('#profiles-body .card .login-state').textContent"
MODELS_LOADED = ("document.getElementById('model-status')"
                 " && !document.getElementById('model-status').textContent.includes('읽는 중')")


class FakeProc:
    def __init__(self) -> None:
        self._closed = threading.Event()

    def poll(self):
        return 0 if self._closed.is_set() else None

    def wait(self, timeout=None):
        self._closed.wait(timeout)
        return 0

    def close(self) -> None:
        self._closed.set()


class FakeChrome:
    """로그인 창 실행기 · 로그인 확인기 흉내. 창을 띄우지 않는다."""

    def __init__(self) -> None:
        self.launches: list[list[str]] = []
        self.procs: list[FakeProc] = []
        self.checks = 0
        self.signed_in = True

    def launcher(self, args):
        assert isinstance(args, list)
        self.launches.append(list(args))
        proc = FakeProc()
        self.procs.append(proc)
        return proc

    def checker(self, _path):
        self.checks += 1
        if self.signed_in:
            return LoginResult("signed_in", "테스트 채널")
        return LoginResult("signed_out")


@pytest.fixture
def chrome():
    return FakeChrome()


@pytest.fixture
def user_dir(tmp_path):
    return tmp_path / "user"


@pytest.fixture
def app_with_key(tmp_path, make_config, fixture_json, user_dir, chrome):
    with r1_server(tmp_path, make_config, fixture_json, user_dir=user_dir,
                   launcher=chrome.launcher, login_checker=chrome.checker) as app:
        yield app


@pytest.fixture
def app_no_key(tmp_path, make_config, fixture_json, user_dir, chrome):
    with r1_server(tmp_path, make_config, fixture_json, user_dir=user_dir, key=False,
                   launcher=chrome.launcher, login_checker=chrome.checker) as app:
        yield app


def open_settings(page) -> None:
    page.click("#nav-settings")
    page.wait_for_function(SETTINGS_LOADED)


def test_settings_save_shows_on_work_screen_survives_rebuild_and_resets(app_with_key, user_dir):
    base = app_with_key["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        first_query = page.input_value("#q")
        assert page.input_value("#limit") == "10"

        open_settings(page)
        assert page.is_disabled("#settings-save")
        assert "is-dirty" not in (page.get_attribute("#settings-save", "class") or "")
        assert page.input_value("#set-daily-max") == "10"
        assert page.input_value("#set-shorts-seconds") == "181"  # 쇼츠 길이 기본 181초
        # R3부터 광고 표기 기본값 · 게시 직전 확인도 바로 쓴다(「곧 적용」 표시 없음)
        assert page.locator("#settings-body .tag-soon").count() == 0
        assert not page.is_checked("#set-confirm-before")  # 기본 꺼짐
        # 모니터는 고르기만(좌표 칸 없음). 위쪽 모니터를 골라 둔 상태
        page.wait_for_function("!document.getElementById('set-window-screen').disabled")
        options = page.locator("#set-window-screen option").all_text_contents()
        assert len(options) == 2 and all("모니터" in o for o in options), options
        assert page.locator("#set-window-position").count() == 0

        page.fill("#set-daily-max", "7")
        page.fill("#set-query", "연애 고민 상담")
        assert page.is_enabled("#settings-save")
        assert "is-dirty" in page.get_attribute("#settings-save", "class")  # 바꾼 것이 있으면 금색
        page.click("#settings-save")
        page.wait_for_function(
            "document.getElementById('settings-msg').textContent.includes('저장했습니다')")
        assert page.is_disabled("#settings-save")
        assert page.locator("#set-post .tag-changed").count() == 1  # 「바꿈」 표시
        saved = json.loads((user_dir / "settings.json").read_text(encoding="utf-8"))
        assert saved["values"] == {
            "limits.daily_max_comments": 7, "discover.query": "연애 고민 상담"}

        # 작업 화면에 바로: 기본 검색어 · ③ 하루 상한 · 아래 줄 오늘 게시 n/7
        page.click("#nav-work")
        assert page.input_value("#q") == "연애 고민 상담"
        assert page.input_value("#limit") == "7"
        limits = page.locator("#limit option").all_text_contents()
        assert limits == ["7개까지", "5개까지", "3개까지", "1개까지"]
        page.wait_for_function("document.getElementById('today-count').textContent.endsWith('/7')")

        # 다시 열어도(서비스를 새 설정으로 다시 만든 뒤) 그대로
        page.reload()
        page.wait_for_function(STATUS_LOADED)
        assert page.input_value("#q") == "연애 고민 상담" and page.input_value("#limit") == "7"
        data = httpx.get(base + "/api/settings", trust_env=False).json()
        assert data["daily_max_comments"] == 7 and data["discover"]["query"] == "연애 고민 상담"

        # 잘못된 값: 칸 옆에 이유, 아무것도 저장하지 않는다
        open_settings(page)
        page.fill("#set-min-chars", "200")
        page.fill("#set-max-chars", "100")
        page.click("#settings-save")
        page.wait_for_function("document.getElementById('settings-msg').classList.contains('is-bad')")
        reasons = " ".join(page.locator("#settings-body .set-err").all_text_contents())
        assert "최소" in reasons, reasons
        kept = json.loads((user_dir / "settings.json").read_text(encoding="utf-8"))
        assert kept["values"] == saved["values"]

        # [기본값으로]: 두 번 눌러야 한다
        page.click("#settings-reset")
        assert "한 번 더" in page.text_content("#settings-reset")
        page.click("#settings-reset")
        page.wait_for_function(
            "document.getElementById('settings-msg').textContent.includes('기본값으로 돌렸습니다')")
        assert page.input_value("#set-daily-max") == "10"
        assert page.input_value("#set-min-chars") != "200"
        assert not (user_dir / "settings.json").exists()
        page.click("#nav-work")
        assert page.input_value("#q") == first_query and page.input_value("#limit") == "10"
    assert not errors, errors


def test_youtube_key_saved_shows_only_saved_and_never_the_value(app_no_key, user_dir):
    base = app_no_key["base"]
    key = "AIza" + "k" * 35  # 가짜 키(실행할 때 조립)
    bodies: list[str] = []
    with headless_page(base) as (page, errors):
        page.on("response", lambda r: bodies.append(r.text()) if "/api/" in r.url else None)
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        assert page.is_visible("#setup-box")
        page.click("#setup-youtube-btn")  # [API 키 넣기] → 설정 화면 키 칸
        page.wait_for_function(FOCUSED.format("set-key"))
        assert page.get_attribute("#set-key", "type") == "password"
        page.click("#key-guide > summary")  # 접어 둔 키 받는 법
        assert page.locator("#key-guide li").count() == 5
        page.fill("#set-key", key)
        assert "is-dirty" in page.get_attribute("#key-save", "class")
        page.click("#key-save")
        page.wait_for_function("document.getElementById('set-youtube').textContent.includes('저장됨')")
        assert page.locator("#set-key").count() == 0  # 저장 뒤에는 칸 대신 「저장됨」
        assert "프로그램에 저장" in page.text_content("#key-source")
        assert page.is_visible("#key-change") and page.is_visible("#key-delete")
        # [연결 확인]: 쉬운 말 한 줄
        page.click("#key-test")
        page.wait_for_function(
            "document.getElementById('key-test-result').textContent.length > 8"
            " && !document.getElementById('key-test-result').textContent.includes('확인하는 중')")
        # 아래 줄 · 시작 준비도 「연결됨」
        page.wait_for_function("document.getElementById('status-youtube').textContent === '연결됨'")
        page.click("#nav-work")
        assert page.locator("#setup-youtube.is-done").count() == 1
        assert key not in page.content()
        # [바꾸기]를 눌러도 저장한 값은 칸에 들어오지 않는다
        open_settings(page)
        page.click("#key-change")
        assert page.input_value("#set-key") == ""
        assert key not in page.content()
    assert not errors, errors
    for body in bodies:
        assert key not in body
    for path in ("/api/settings", "/api/status"):
        assert key not in httpx.get(base + path, trust_env=False).text
    blob = (user_dir / "youtube_key.bin").read_bytes()
    assert key.encode() not in blob  # 파일에 평문이 없다


def test_setup_box_three_lines_jump_and_disappear(app_no_key, chrome):
    base = app_no_key["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        assert page.is_visible("#setup-box")
        assert "has-setup" in page.get_attribute("#screen-work", "class")
        names = page.locator("#setup-box .setup-name").all_text_contents()
        assert names == ["유튜브 연결", "AI 모델", "프로필 로그인"]
        assert page.is_visible("#setup-youtube-btn")
        assert page.text_content("#setup-youtube-btn") == "API 키 넣기"
        assert not page.is_visible("#setup-ai-btn")  # 가짜 AI는 준비됨
        assert page.locator("#setup-ai.is-done").count() == 1
        assert page.text_content("#setup-profile-btn") == "유튜브1 로그인"
        assert "연습 모드는 키와 로그인 없이도" in page.text_content("#setup-box")

        # [유튜브1 로그인] → 프로필 화면의 [로그인하기]
        page.click("#setup-profile-btn")
        page.wait_for_function(FOCUSED.format("profile-1-login"))
        assert page.is_visible("#screen-profiles")
        assert "is-primary" in page.get_attribute("#profile-1-login", "class")
        page.click("#profile-1-check")
        page.wait_for_function(
            LOGIN_STATE + " === '로그인됨 · 테스트 채널'")
        assert chrome.checks == 1
        page.wait_for_function(
            "document.getElementById('status-browser').textContent === '1/3 로그인됨'")
        assert page.locator("#profile option").all_text_contents()[1] == "유튜브1 · 로그인됨"

        # [모델 확인] → 설정 화면 모델 칸. 코드용 모델도 보이되 아래에
        page.click("#nav-work")
        assert page.locator("#setup-profile.is-done").count() == 1
        page.evaluate("document.getElementById('setup-ai-btn').hidden = false")
        page.click("#setup-ai-btn")
        page.wait_for_function(FOCUSED.format("set-model"))
        page.wait_for_function(MODELS_LOADED)
        options = page.locator("#set-model option").all_text_contents()
        assert "코드용" in options[-1], options

        # [닫기] → 이번에는 보이지 않는다(다시 열어도 같은 창에서는 닫힌 채)
        page.click("#nav-work")
        page.click("#setup-close")
        assert not page.is_visible("#setup-box")
        assert "has-setup" not in (page.get_attribute("#screen-work", "class") or "")
        page.reload()
        page.wait_for_function(STATUS_LOADED)
        assert not page.is_visible("#setup-box")

    # 새 창: 키를 넣으면 셋 다 되어 상자가 저절로 없다
    key = "AIza" + "s" * 35
    assert httpx.put(base + "/api/settings/youtube-key", json={"key": key},
                     trust_env=False).status_code == 200
    with headless_page(base) as (page, errors2):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        page.wait_for_timeout(200)
        assert not page.is_visible("#setup-box")
    assert not errors and not errors2, (errors, errors2)


def test_profile_buttons_call_apis_and_close_checks_once(app_with_key, chrome):
    base = app_with_key["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        page.click("#nav-profiles")
        page.wait_for_selector("#profile-1-login")
        assert page.locator("#profiles-body .card").count() == 3
        assert "로그아웃" in page.text_content("#screen-profiles")  # 로그아웃 안내

        page.click("#profile-1-login")
        page.wait_for_function(
            "document.getElementById('profiles-msg').textContent.includes('크롬 창을 닫은 다음')")
        args = chrome.launches[0]
        assert args[-1] == LOGIN_URL and any(a.startswith("--user-data-dir=") for a in args)
        assert not any(a.startswith(("--remote-debugging", "--enable-automation", "--headless"))
                       for a in args)
        page.wait_for_selector("#profiles-body .card .notice")
        assert page.is_disabled("#profile-1-check")  # 창이 열려 있는 동안은 확인하지 않는다
        chrome.procs[0].close()  # 사람이 로그인을 마치고 창을 닫았다
        page.wait_for_function(
            LOGIN_STATE + ".startsWith('로그인됨')",
            timeout=15000)
        assert chrome.checks == 1  # 창을 닫으면 한 번 저절로

        page.click("#profile-2-open")
        page.wait_for_function("document.getElementById('profiles-msg').textContent.includes('유튜브2')")
        assert chrome.launches[-1][-1] == HOME_URL
        chrome.procs[-1].close()
    assert not errors, errors


@pytest.mark.parametrize("size", [(1920, 1009), (1600, 960)])
def test_settings_and_profile_screens_fit(app_with_key, size):
    base = app_with_key["base"]
    with headless_page(base, size=size) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_settings(page)
        page.wait_for_function(MODELS_LOADED)
        page.click("#key-change")  # 키 칸까지 펼친 가장 긴 상태
        page.click("#facts-add")
        page.click("#key-guide > summary")
        m = measure(page, *size)
        where = f"설정 {size}"
        assert not m["pageScroll"] and not m["hScroll"], (
            where, m["scrollHeight"], m["scrollWidth"])
        assert m["minFont"] >= 12, (where, m["minFont"], m["minFontAt"])
        assert m["buttons"]["min"] >= 36, (where, m["buttons"])
        assert page.locator("#screen-settings .set-foot").bounding_box()["y"] + 36 <= size[1]

        page.click("#nav-profiles")
        page.wait_for_selector("#profile-1-login")
        m = measure(page, *size)
        where = f"프로필 {size}"
        assert not m["pageScroll"] and not m["hScroll"], (
            where, m["scrollHeight"], m["scrollWidth"])
        assert m["minFont"] >= 12, (where, m["minFont"], m["minFontAt"])
        assert m["buttons"]["min"] >= 36, (where, m["buttons"])
    assert not errors, errors
