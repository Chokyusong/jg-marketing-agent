r"""진짜 Ollama 1회 호출. RUN_LIVE=1일 때만 돈다(Ollama가 켜진 PC에서 확인).

    $env:RUN_LIVE='1'; .\.venv\Scripts\python.exe -m pytest -m live; Remove-Item Env:RUN_LIVE

`.env`의 OLLAMA_BASE_URL·OLLAMA_MODEL(없으면 기본값)을 그대로 쓴다. 첫 응답은 모델을
불러오느라 오래 걸릴 수 있다(config.yaml의 llm.timeout_seconds).
"""

import re

import pytest

from app.config import load_settings
from app.llm.registry import build_llm

SCHEMA = {
    "type": "object",
    "properties": {
        "concern": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["concern", "keywords"],
}


@pytest.mark.live
def test_live_ollama_korean_json(tmp_db_path):
    settings = load_settings(db_path=tmp_db_path)
    llm = build_llm(settings)
    try:
        health = llm.health()
        if not health.reachable:
            pytest.skip("Ollama가 꺼져 있음")
        assert health.installed, f"{health.model}이(가) 설치돼 있지 않음(ollama list 확인)"
        data = llm.generate_json(
            system="너는 한국어로 답하는 도우미다. JSON 하나만 답한다.",
            user="연애 상담 영상을 본 시청자의 고민 하나를 한 문장으로, 핵심 낱말 2개와 함께.",
            schema=SCHEMA,
            temperature=0.2,
            max_tokens=200,
        )
    finally:
        llm.close()
    assert isinstance(data["concern"], str) and re.search(r"[가-힣]", data["concern"])
    assert isinstance(data["keywords"], list)
