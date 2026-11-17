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
        page.fill("#ai-model-openai", "m-test-1")
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
        page.fill("#ai-model-claude", "c-test")
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
                page.fill("#ai-model-openai", "m-1")
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
