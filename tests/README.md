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
