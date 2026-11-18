"""모든 테스트가 함께 쓰는 도우미.

- 인터넷·API 키·Ollama 없이 돌아야 한다. 외부 호출은 아래 가짜로 바꾼다.
- `live` 표시 테스트는 환경 변수 RUN_LIVE=1일 때만 실행한다.
- `e2e` 표시 테스트는 playwright가 설치돼 있지 않으면 건너뛴다.
- 아직 없는 앱 모듈(app.config 등)을 여기서 import하지 않는다.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
CONFIG_PATH = ROOT / "config.yaml"

# 표시 건너뛰기를 시험하는 하네스 테스트(tests/unit/test_markers.py)에서 쓴다.
pytest_plugins = ["pytester"]


# ---------------------------------------------------------------- 표시(marker)


def pytest_configure(config: pytest.Config) -> None:
    # pyproject.toml에도 등록돼 있다. 다른 루트에서 이 conftest만 쓸 때를 위해 한 번 더 등록.
    config.addinivalue_line("markers", "e2e: Playwright sandbox 화면 테스트")
    config.addinivalue_line("markers", "live: 진짜 외부 호출. RUN_LIVE=1일 때만")
    config.addinivalue_line("markers", "real_review: AI 검수의 진짜 ask를 쓴다")


def live_enabled() -> bool:
    return os.environ.get("RUN_LIVE") == "1"


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_live = pytest.mark.skip(reason="live 테스트: RUN_LIVE=1일 때만 실행")
    skip_e2e = pytest.mark.skip(reason="e2e 테스트: playwright 미설치(8단계에서 설치)")
    run_live = live_enabled()
    has_playwright = playwright_available()
    for item in items:
        if "live" in item.keywords and not run_live:
            item.add_marker(skip_live)
        if "e2e" in item.keywords and not has_playwright:
            item.add_marker(skip_e2e)


# ---------------------------------------------------------------- AI 검수 가짜 답


REVIEW_OK = {"ok": True, "problems": [], "wish_kind": "기타"}


@pytest.fixture(autouse=True)
def _ai_review_answers(request, monkeypatch):
    """AI 검수 한 번(2026-11-18)의 가짜 답을 한곳에서 정한다.

    검수는 `app.analysis.review.ask`로만 AI를 부른다. 자동 테스트에서는 이것을 바꿔:
    - 가짜 LLM에 `answer_review`가 있으면(아래 `FakeLLM`) 그것이 답한다 — 준비한 검수 답이
      다음 차례에 있으면 그것, 없으면 통과.
    - 그 밖의 가짜(e2e의 ScriptedLLM, compare_drafts 시험의 가짜 등)는 부르지 않고 통과로 답한다.
    그래서 그 전에 짠 시험의 응답 차례와 `calls`가 그대로다. 진짜 `ask`를 시험할 때는
    `@pytest.mark.real_review`를 붙인다."""
    if request.node.get_closest_marker("real_review"):
        return
    from app.analysis import review

    real_parse = review.parse

    def fake_ask(llm, *, system, user):
        answer = getattr(llm, "answer_review", None)
        data = REVIEW_OK if answer is None else answer(
            system=system, user=user, schema=review.REVIEW_SCHEMA)
        return real_parse(data)

    monkeypatch.setattr(review, "ask", fake_ask)


# ---------------------------------------------------------------- 실제 유튜브 막기(R3)


@pytest.fixture(autouse=True)
def _never_real_youtube(monkeypatch):
    """자동 테스트는 실제 유튜브에 접속하지 않는다(R3: 실제 게시가 기본이 되어 더 조심한다).

    실제 게시 실행기는 가짜 페이지를 끼운 것(`prepare_context`가 있는 것)만 열 수 있다. 설정 기본값
    그대로 실제 실행기가 만들어지면 크롬을 띄우기 전에 실패한다. 진짜 로그인 확인도 막는다.
    """
    from app.browser import login, youtube_driver

    real_open = youtube_driver.PlaywrightYouTubeDriver.open

    def guarded_open(self, user_data_dir, url):
        if self.prepare_context is None:
            raise AssertionError(f"자동 테스트가 실제 유튜브를 열려고 했다: {url}")
        return real_open(self, user_data_dir, url)

    real_check = login.check_login

    def guarded_check(*args, **kwargs):
        if kwargs.get("prepare_context") is None:
            raise AssertionError("자동 테스트가 실제 유튜브 로그인 확인을 하려고 했다")
        return real_check(*args, **kwargs)

    monkeypatch.setattr(youtube_driver.PlaywrightYouTubeDriver, "open", guarded_open)
    monkeypatch.setattr(login, "check_login", guarded_check)

    # R4: 자막 자동 읽기도 실제로 접속하지 않는다. 가짜 공급처를 끼우지 않은 테스트에서는
    # 「이 영상에는 자막이 없습니다」(빈 목록)로 돈다 — 3단계 이전과 같은 흐름
    from app.transcript import auto

    monkeypatch.setattr(auto, "default_lister", lambda timeout=10.0: lambda video_id: [])

    # R5: 로그인된 프로그램(Codex·Claude Code 등)도 진짜로 실행하지 않는다. 가짜 실행기를 끼우지
    # 않은 테스트에서는 「설치되지 않음」으로 보이고, 실행하려 하면 실패한다
    from app.llm import cli

    def blocked_runner(req):
        raise AssertionError(f"자동 테스트가 진짜 프로그램을 실행하려고 했다: {req.args[:2]}")

    monkeypatch.setattr(cli, "default_runner", blocked_runner)
    monkeypatch.setattr(cli, "default_which", lambda program: None)

    # 2026-11-17 [로그인하기]: 진짜 로그인 명령 창을 열지 않는다(가짜 창을 끼워 시험)
    from app.llm import cli_login

    def blocked_launcher(args, env):
        raise AssertionError(f"자동 테스트가 진짜 로그인 명령을 열려고 했다: {args[1:]}")

    monkeypatch.setattr(cli_login, "default_launcher", blocked_launcher)


# ---------------------------------------------------------------- 임시 저장소·설정


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """테스트마다 새로 쓰는 SQLite 파일 경로(파일은 만들지 않는다)."""
    return tmp_path / "test.sqlite3"


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@pytest.fixture
def base_config() -> dict[str, Any]:
    """저장소의 config.yaml 내용(dict). 테스트에서 고쳐도 원본에는 영향 없음."""
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # 2026-11-18: 게시 뒤 크롬 창은 자동 테스트에서 바로 닫는다(열어 두기는 그 시험만 켠다)
    data.setdefault("posting", {})["keep_window_seconds"] = 0
    return data


@pytest.fixture
def make_config(tmp_path: Path, base_config: dict[str, Any]) -> Callable[..., Path]:
    """config.yaml을 바탕으로 일부만 바꾼 임시 설정 파일을 만든다.

    사용: path = make_config({"limits": {"daily_max_comments": 2}})
    """

    counter = {"n": 0}

    def _make(overrides: dict[str, Any] | None = None) -> Path:
        counter["n"] += 1
        data = _deep_merge(base_config, overrides or {})
        path = tmp_path / f"config_{counter['n']}.yaml"
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    return _make


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """실제 .env·환경 변수의 비밀값이 테스트에 섞이지 않게 지운다."""
    for name in ("YOUTUBE_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ---------------------------------------------------------------- 저장해 둔 응답


def load_fixture_json(name: str) -> Any:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    """tests/fixtures/<이름> JSON을 읽는다. 사용: fixture_json("youtube/search.json")"""
    return load_fixture_json


# ---------------------------------------------------------------- 가짜 LLM


class FakeLLM:
    """정해 둔 응답을 차례로 돌려주는 가짜 LLM.

    응답이 Exception이면 그 차례에 예외를 던진다. 응답이 다 떨어지면 AssertionError.
    부른 기록은 `calls`에 남는다(프롬프트에 실패 사유가 들어갔는지 확인할 때 쓴다).
    """

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.review_calls: list[dict[str, Any]] = []  # AI 검수 호출(`calls`에는 넣지 않는다)

    def answer_review(self, **kwargs: Any) -> Any:
        """AI 검수 답. 다음 차례가 「ok」가 든 dict면 그것을 쓴다(「raise」가 있으면 그 예외를
        던진다). 아니면 차례를 쓰지 않고 통과로 답한다(그 전에 짠 시험은 검수 답이 없다)."""
        self.review_calls.append({"args": (), "kwargs": kwargs})
        nxt = self._responses[0] if self._responses else None
        if not (isinstance(nxt, dict) and "ok" in nxt):
            return dict(REVIEW_OK)
        item = self._responses.pop(0)
        if item.get("raise") is not None:
            raise item["raise"]
        return copy.deepcopy(item)

    def generate_json(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append({"args": args, "kwargs": kwargs})
        if not self._responses:
            raise AssertionError(f"FakeLLM: 준비한 응답보다 많이 불림({len(self.calls)}번째)")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return copy.deepcopy(item)

    @property
    def remaining(self) -> int:
        return len(self._responses)


@pytest.fixture
def fake_llm() -> Callable[[list[Any]], FakeLLM]:
    """사용: llm = fake_llm([{"concern": "..."}, {"body": "..."}])"""
    return FakeLLM


# ---------------------------------------------------------------- httpx.MockTransport


class MockHTTP:
    """httpx.MockTransport 도우미. 경로(+메서드)별로 응답을 정하고 요청을 기록한다.

    사용:
        mock = mock_http()
        mock.add("GET", "/youtube/v3/search", json={...})
        mock.add("GET", "/youtube/v3/videos", status_code=403, json={...})
        client = httpx.Client(transport=mock.transport, base_url="https://example.test")
    같은 경로를 여러 번 add하면 차례로 돌려주고, 마지막 것은 계속 돌려준다.
    정하지 않은 경로로 요청이 오면 실패한다(실수로 진짜 주소를 부르는 것을 잡는다).
    """

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list[Any]] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def add(
        self,
        method: str,
        path: str,
        *,
        status_code: int = 200,
        json: Any = None,
        text: str | None = None,
        exc: Exception | None = None,
        handler: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> MockHTTP:
        if handler is None:

            def handler(request: httpx.Request) -> httpx.Response:
                if exc is not None:
                    raise exc
                if json is not None:
                    return httpx.Response(status_code, json=json)
                return httpx.Response(status_code, text=text or "")

        self.routes.setdefault((method.upper(), path), []).append(handler)
        return self

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        handlers = self.routes.get(key)
        if not handlers:
            raise AssertionError(f"MockHTTP: 정하지 않은 요청 {request.method} {request.url.path}")
        handler = handlers.pop(0) if len(handlers) > 1 else handlers[0]
        return handler(request)

    def client(self, **kwargs: Any) -> httpx.Client:
        kwargs.setdefault("base_url", "https://example.test")
        return httpx.Client(transport=self.transport, **kwargs)


@pytest.fixture
def mock_http() -> Callable[[], MockHTTP]:
    return MockHTTP
