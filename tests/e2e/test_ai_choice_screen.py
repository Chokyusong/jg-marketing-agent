"""R5 화면 e2e: 설정 「글 쓰는 AI」 — 목록 세 묶음 → AI 보기 → 키 저장(값은 어디에도 안 보임) →
모델 적기 → [이 AI 쓰기] → 바깥 전송 확인 → [저장] → 위 줄·아래 줄에 「이름 · 모델 · 외부」.
그리고 1920×1009 · 1600×960 · 1366×720에서 화면 전체 스크롤 없음,
가장 작은 글자 12px 이상.

- 창 없는(headless) 설치된 크롬. AI는 가짜 LLM(진짜 AI 회사 주소를 부르지 않는다).
- 사용자 설정 폴더는 임시 폴더, 키 암호화는 가짜(`FAKE_PROTECTOR`).
- 로그인된 프로그램은 자동 테스트에서 「설치 안 됨」으로 보인다
  (tests/conftest.py가 진짜 실행을 막는다).
"""

from __future__ import annotations

import json

import httpx
import pytest
from r1_support import headless_page, measure, r1_server

pytestmark = pytest.mark.e2e

STATUS_LOADED = "document.getElementById('status-youtube').textContent !== '확인 중'"
AI_LOADED = "document.getElementById('ai-list') !== null"
FORBIDDEN = ("LLM", "공급자", "CLI")


@pytest.fixture
def user_dir(tmp_path):
    return tmp_path / "user"


@pytest.fixture
def app(tmp_path, make_config, fixture_json, user_dir):
    with r1_server(tmp_path, make_config, fixture_json, user_dir=user_dir) as served:
        yield served


def open_ai(page) -> None:
    page.click("#nav-settings")
    page.wait_for_function(AI_LOADED)


def type_model(page, name: str, model: str) -> None:
    """2026-11-17 「모델」은 고르는 목록: 맨 아래 「직접 입력…」을 고르면 글 칸이 나온다."""
    page.select_option(f"#ai-model-sel-{name}", "__custom__")
    assert page.is_visible(f"#ai-model-{name}")
    page.fill(f"#ai-model-{name}", model)


def test_pick_ai_confirm_external_save_and_status(app, user_dir):
    base = app["base"]
    key = "sk-" + "e2e" * 12  # 실행할 때 조립한 가짜 키
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        assert page.text_content("#top-ai-text").startswith("AI · Ollama · ")
        open_ai(page)
        kinds = page.locator("#ai-list .ai-kind").all_text_contents()
        assert kinds == ["이 PC에서", "API 키로", "로그인된 프로그램으로"]
        assert "사용 중" in page.text_content("#ai-item-ollama")
        assert "설치 안 됨" in page.text_content("#ai-item-codex-cli")
        assert "is-dim" in page.get_attribute("#ai-item-codex-cli", "class")
        assert page.is_visible("#ai-pane-ollama") and page.is_visible("#warmup-btn")

        # 줄을 누르면 오른쪽 칸만 바뀐다(아직 바꾸지 않는다)
        page.click("#ai-item-openai")
        assert page.is_visible("#ai-pane-openai") and not page.is_visible("#ai-pane-ollama")
        notice = page.text_content("#ai-external-openai")
        assert "영상 제목·설명·자막·댓글이 OpenAI(으)로 전송됩니다. 요금이 들 수 있습니다" in notice
        assert page.is_disabled("#ai-use-openai")
        assert "API 키를 먼저 넣어 주세요" in page.text_content("#ai-use-row-openai")
        assert page.is_disabled("#settings-save")

        # 키 저장 → 「저장됨」만. 칸은 비운다
        page.fill("#ai-key-openai", key)
        page.click("#ai-key-save-openai")
        page.wait_for_function(
            "document.getElementById('ai-pane-openai').textContent.includes('저장됨')")
        assert page.is_visible("#ai-pane-openai")  # 다시 그려도 보던 칸 그대로
        assert key not in page.content()
        assert (user_dir / "llm_keys" / "openai.bin").is_file()

        # 모델 적기 → [이 AI 쓰기] → 같은 글로 한 번 확인 → [쓰기]
        type_model(page, "openai", "m-test-1")
        assert page.is_enabled("#ai-use-openai")
        page.click("#ai-use-openai")
        confirm = page.text_content("#ai-confirm-openai")
        assert "OpenAI(으)로 전송됩니다. 요금이 들 수 있습니다" in confirm
        page.click("#ai-confirm-yes-openai")
        assert "저장하면 사용" in page.text_content("#ai-item-openai")
        assert "is-dirty" in page.get_attribute("#settings-save", "class")

        with page.expect_request(lambda r: r.url.endswith("/api/settings")
                                 and r.method == "PUT") as req:
            page.click("#settings-save")
        sent = json.loads(req.value.post_data)["values"]
        assert sent == {"llm.active": "openai", "llm.models": {"openai": "m-test-1"}}
        page.wait_for_function(
            "document.getElementById('settings-msg').textContent.includes('저장했습니다')")
        assert "사용 중" in page.text_content("#ai-item-openai")
        page.wait_for_function(
            "document.getElementById('status-ai').textContent.includes('ChatGPT(OpenAI)')")
        assert page.text_content("#status-ai") == "ChatGPT(OpenAI) · m-test-1 · 외부"
        assert page.text_content("#top-ai-text") == "AI · ChatGPT(OpenAI) · m-test-1 · 외부"

        # 화면 글에 「LLM」「공급자」「CLI」가 없다
        for screen in ("settings", "work"):
            page.click(f"#nav-{screen}")
            text = page.inner_text("body")
            for word in FORBIDDEN:
                assert word not in text, (screen, word)
        assert key not in page.content()

        # 시작 준비 줄은 고른 AI를 본다(가짜 AI는 준비됨)
        assert page.locator("#setup-ai.is-done").count() in (0, 1)
    saved = json.loads((user_dir / "settings.json").read_text(encoding="utf-8"))["values"]
    assert saved["llm.active"] == "openai"
    for path in user_dir.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes(), path.name
    status = httpx.get(base + "/api/status", trust_env=False).json()["ai"]
    assert status["provider"] == "openai" and status["local"] is False
    assert not errors, errors


def test_cancel_external_confirm_keeps_current_ai(app):
    base = app["base"]
    key = "sk-" + "c" * 36
    assert httpx.put(base + "/api/settings/llm-key/claude", json={"key": key},
                     trust_env=False).status_code == 200
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        page.click("#ai-item-claude")
        type_model(page, "claude", "c-test")
        page.click("#ai-use-claude")
        assert page.is_visible("#ai-confirm-claude")
        page.click("#ai-confirm-claude >> text=취소")
        assert not page.is_visible("#ai-confirm-claude")
        assert "저장하면 사용" not in page.text_content("#ai-item-claude")
        # 모델 칸은 바꿨으니 [저장]은 그 칸만 보낸다(AI는 그대로)
        with page.expect_request(lambda r: r.url.endswith("/api/settings")
                                 and r.method == "PUT") as req:
            page.click("#settings-save")
        assert json.loads(req.value.post_data)["values"] == {"llm.models": {"claude": "c-test"}}
        page.wait_for_function(
            "document.getElementById('settings-msg').textContent.includes('저장했습니다')")
        assert "사용 중" in page.text_content("#ai-item-ollama")
    assert not errors, errors


@pytest.mark.parametrize("size", [(1920, 1009), (1600, 960), (1366, 720)])
def test_ai_group_fits_without_page_scroll(app, size):
    base = app["base"]
    key = "sk-" + "f" * 36  # 키가 있어야 [이 AI 쓰기] → 확인 상자까지 펼칠 수 있다
    assert httpx.put(base + "/api/settings/llm-key/openai", json={"key": key},
                     trust_env=False).status_code == 200
    with headless_page(base, size=size) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        for name in ("ollama", "openai", "custom", "codex-cli"):
            page.click(f"#ai-item-{name}")
            if name == "openai":
                page.click("#ai-pane-openai .key-guide > summary")
                type_model(page, "openai", "m-1")
                page.click("#ai-use-openai")  # 확인 상자까지 펼친 가장 긴 상태
            m = measure(page, *size)
            where = f"{name} {size}"
            assert not m["pageScroll"] and not m["hScroll"], (
                where, m["scrollHeight"], m["scrollWidth"])
            assert m["minFont"] >= 12, (where, m["minFont"], m["minFontAt"])
            assert m["buttons"]["min"] >= 36, (where, m["buttons"])
            assert page.locator("#screen-settings .set-foot").bounding_box()["y"] + 36 <= size[1]
        page.click("#nav-work")
        m = measure(page, *size)
        assert not m["pageScroll"] and not m["hScroll"], ("work", size)
        assert m["minFont"] >= 12, ("work", size, m["minFont"], m["minFontAt"])
    assert not errors, errors


def test_model_field_is_a_list_refilled_after_key_save(app):
    """2026-11-17 「모델」은 고르는 목록: 추천 목록 → 키 저장 뒤 받아 온 목록,
    맨 아래 「직접 입력…」.

    저장된 모델이 목록에 없어도 사라지지 않고 고른 상태로 보인다. 받아 오는 곳은 가짜 AI 회사."""
    base = app["base"]
    key = "sk-" + "m" * 36  # 실행할 때 조립한 가짜 키
    saved = {"values": {"llm.models": {"openai": "keep-me"}}}
    assert httpx.put(base + "/api/settings", json=saved, trust_env=False).status_code == 200
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        page.click("#ai-item-openai")
        options = page.locator("#ai-model-sel-openai option").all_text_contents()
        assert options[0] == "모델을 고르세요" and options[-1] == "직접 입력…", options
        assert "keep-me · 저장된 모델" in options and len(options) > 3  # 추천 목록 + 저장된 값
        assert page.input_value("#ai-model-sel-openai") == "keep-me"
        assert not page.is_visible("#ai-model-openai")  # 빈 글 칸만 두지 않는다
        note = page.text_content("#ai-models-note-openai")
        assert "계정에 따라 쓸 수 없는 모델이 있을 수 있습니다" in note
        assert "키를 넣으면 쓸 수 있는 목록을 받아 옵니다" in note

        page.fill("#ai-key-openai", key)
        page.click("#ai-key-save-openai")
        page.wait_for_function("(document.getElementById('ai-models-note-openai') || {})"
                               ".textContent?.includes('받아 온 모델 2개')")
        options = page.locator("#ai-model-sel-openai option").all_text_contents()
        assert options[1:3] == ["e2e-model-a", "e2e-model-b"], options
        assert page.input_value("#ai-model-sel-openai") == "keep-me"
        page.select_option("#ai-model-sel-openai", "e2e-model-b")
        assert not page.is_visible("#ai-model-openai")
        with page.expect_request(lambda r: r.url.endswith("/api/settings")
                                 and r.method == "PUT") as req:
            page.click("#settings-save")
        sent = json.loads(req.value.post_data)["values"]
        assert sent == {"llm.models": {"openai": "e2e-model-b"}}
        page.wait_for_function(
            "document.getElementById('settings-msg').textContent.includes('저장했습니다')")

        # 로그인된 프로그램: 맨 위 「기본값 (그 프로그램이 정한 모델)」이 기본
        page.click("#ai-item-claude-cli")
        first = page.locator("#ai-model-sel-claude-cli option").first.text_content()
        assert first == "기본값 (그 프로그램이 정한 모델)"
        assert page.input_value("#ai-model-sel-claude-cli") == ""
        texts = page.locator("#ai-model-sel-claude-cli option").all_text_contents()
        assert "sonnet" in texts and texts[-1] == "직접 입력…"
        assert key not in page.content()
    assert not errors, errors


def test_ollama_model_list_has_custom_entry(app):
    """2026-11-17: 이 PC 모델 목록 맨 아래에도 「직접 입력…」.

    고르면 글 칸이 나오고 적은 이름을 저장한다."""
    base = app["base"]
    with headless_page(base) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        page.wait_for_function(
            "[...document.querySelectorAll('#set-model option')]"
            ".some(o => o.value === '__custom__')")
        assert not page.is_visible("#set-model-custom")
        page.select_option("#set-model", "__custom__")
        assert page.is_visible("#set-model-custom")
        assert page.is_disabled("#settings-save")  # 이름을 적기 전에는 바꾼 것이 없다
        page.fill("#set-model-custom", "my-ollama:1b")
        with page.expect_request(lambda r: r.url.endswith("/api/settings")
                                 and r.method == "PUT") as req:
            page.click("#settings-save")
        assert json.loads(req.value.post_data)["values"] == {"llm.model": "my-ollama:1b"}
    assert not errors, errors


LIST_FIT = """() => {
  const list = document.getElementById('ai-list');
  const body = document.getElementById('settings-body').getBoundingClientRect();
  const items = [...list.querySelectorAll('.ai-item')];
  const last = items[items.length - 1].getBoundingClientRect();
  const use = document.getElementById('ai-use-openai').getBoundingClientRect();
  return {rows: items.length, listScroll: list.scrollHeight > list.clientHeight + 1,
          lastBottom: last.bottom, bodyBottom: body.bottom, viewport: innerHeight,
          useBottom: use.bottom};
}"""


@pytest.mark.parametrize("size", [(1920, 1009), (1600, 960)])
def test_ai_list_last_row_is_visible_without_scrolling(app, size):
    """2026-11-17: 넓은 창에서는 AI 목록 9줄이 목록 안쪽·설정 칸 스크롤 없이 다 보인다."""
    base = app["base"]
    with headless_page(base, size=size) as (page, errors):
        page.goto(base + "/")
        page.wait_for_function(STATUS_LOADED)
        open_ai(page)
        page.click("#ai-item-openai")
        m = page.evaluate(LIST_FIT)
        assert m["rows"] == 9 and not m["listScroll"], m
        assert m["lastBottom"] <= m["bodyBottom"] <= m["viewport"], m  # 마지막 줄(Gemini 프로그램)
        assert m["useBottom"] <= m["bodyBottom"], m  # [이 AI 쓰기]도 가려지지 않는다
        assert page.locator("#ai-item-gemini-cli").is_visible()
        fit = measure(page, *size)
        assert not fit["pageScroll"] and not fit["hScroll"] and fit["minFont"] >= 12, fit
    assert not errors, errors
