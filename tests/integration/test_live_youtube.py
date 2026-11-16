"""진짜 YouTube Data API 1회 호출. RUN_LIVE=1이고 키가 있을 때만 돈다(대표 PC에서 확인).

    $env:RUN_LIVE='1'; .\\.venv\\Scripts\\python.exe -m pytest -m live; Remove-Item Env:RUN_LIVE

키 값은 출력하지 않는다.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app


@pytest.mark.live
def test_live_default_search(tmp_db_path):
    settings = load_settings(db_path=tmp_db_path)
    if not settings.youtube_key_configured:
        pytest.skip("YOUTUBE_API_KEY가 .env에 없음")
    with TestClient(create_app(settings)) as client:
        res = client.get("/api/videos", params={"max_results": 3})
    leaked = settings.youtube_api_key in res.text  # 실패 메시지에 키가 찍히지 않게 이름으로 비교
    assert not leaked, "응답 본문에 API 키가 들어 있음"
    assert res.status_code == 200, res.json().get("error")
    data = res.json()
    assert data["query"] == settings.discover.query
    assert 1 <= len(data["items"]) <= 3
    first = data["items"][0]
    assert first["title"] and first["channel_title"] and first["published_at"]
    assert data["quota"]["used_today"] >= 101
