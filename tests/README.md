# 테스트 안내

| 폴더 | 내용 | 기본 실행 |
|---|---|---|
| `unit/` | 네트워크·LLM 없이 도는 단위 테스트(링크 해석, 규칙 검사, 운영 규칙 등) | 예 |
| `integration/` | YouTube·Ollama를 `httpx.MockTransport`와 저장해 둔 응답으로 바꾼 통합 테스트 | 예 |
| `e2e/` | 창 없는 크롬으로 sandbox 화면을 도는 테스트. `@pytest.mark.e2e` | Playwright가 있으면 |
| `fixtures/` | 저장해 둔 API 응답, 표본 자막 등 테스트 자료. 진짜 키·개인정보 금지 | — |

- `@pytest.mark.live`는 진짜 외부 호출이다. `$env:RUN_LIVE='1'`일 때만 돈다.
- 공통 도우미는 `conftest.py`: `tmp_db_path`, `base_config`, `make_config`, `clean_env`, `fixture_json`, `fake_llm`, `mock_http`.
- 테스트 자료에 가짜 키가 필요하면 `"AIza" + "x" * 35`처럼 실행할 때 조립한다. 파일에 키 모양 문자열을 그대로 쓰면 비밀값 검사에 걸린다.
- `tests/test_health.py`는 1단계 원본 테스트라 자리를 옮기지 않는다.
- `integration/conftest.py`: `fake_key`(실행할 때 조립한 가짜 키), `clock`(고정 시계, `advance(minutes=…)`), `make_client(mock, key=…, llm=…)`(임시 설정·임시 DB·가짜 YouTube로 만든 `TestClient`. `llm`에 가짜 Ollama(`mock_http`)를 주지 않으면 「Ollama 꺼짐」으로 본다 — 진짜 Ollama를 부르지 않는다). Ollama 저장 응답은 `fixtures/ollama/`(이 PC의 Ollama 0.34.0 응답을 줄인 것). 공용 값은 `integration/yt_helpers.py`.
- 5단계 모델 비교용 가상 영상 맥락 5개는 `fixtures/contexts/`(모두 지어낸 자료, `scripts/eval_drafts.py`와 `test_eval_drafts.py`가 쓴다). 분석·초안 테스트는 `fake_llm`(정해 둔 JSON을 차례로)을 `services.llm`에 넣어 쓴다.
- 저장해 둔 YouTube 응답은 `fixtures/youtube/`. 실제 응답을 저장할 때는 요청 주소와 머리말을 빼고 본문만, 영상 ID·채널 이름은 가짜로 바꾼다.
