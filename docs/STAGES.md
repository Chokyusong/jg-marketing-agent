# 단계별 개발 계획

- 구조와 규칙의 기준은 [DESIGN.md](DESIGN.md)다. 이 문서는 순서와 완료 기준만 적는다.
- 화면 모양과 구성의 기준은 [UI_SPEC.md](UI_SPEC.md)다(대표가 넣은 목업).
- **단계마다 만들 파일·함수·API·테스트의 상세는 [PLAYBOOK.md](PLAYBOOK.md)에 있다.** 이 문서는 상태 표기와 완료 기준 요약이다.
- **실행 순서: 2 마무리 → 3 → P → 6 → 4 → 5 → 7 → 8 → 9 → 10 → 11.** 6단계(규칙 검사)를 4·5단계보다 먼저 한다(PLAYBOOK 2절).
- 앞 단계가 `[-]`여도 남은 것이 "사람이 확인할 것"뿐이면 다음 단계를 시작해도 된다.
- 한 번에 한 단계만 한다. 단계가 끝나면 `scripts/verify.ps1`이 통과해야 다음으로 간다.
- 상태 표기: `[ ]` 미시작 · `[-]` 진행 중 · `[x]` 완료 기준 충족

## 모든 단계에 공통인 완료 조건

1. 새 기능마다 테스트가 있고 `scripts/verify.ps1`(형식 검사 + pytest)이 통과한다.
2. 자동 테스트는 인터넷·API 키·Ollama 없이 돈다.
3. 기존 테스트와 기존 기능(`/`, `/api/health`)을 지우지 않는다.
4. API 키·토큰·프로필 폴더가 코드, 테스트 자료, 로그, 커밋에 없다.
5. 실제 유튜브 화면을 자동으로 조작하는 코드를 넣지 않는다(DESIGN 6.1).
6. 끝낼 때 "구현함 / 자동 검증함 / 사람이 확인함 / 안 함"을 나눠 보고한다. 안 한 것을 했다고 쓰지 않는다.
7. README와 이 문서의 상태 표기를 실제대로 고친다.

## 단계

### [x] 1단계 — 뼈대 (GPT 초안)

FastAPI 앱, 읽기 전용 3열 화면, `/api/health`, 테스트 2개.

### [x] 0단계 — 하네스

작업 규칙(AGENTS.md), 검증 스크립트, pytest 설정, 테스트 도우미, 설정 파일, Git 저장소.

### [-] 2단계 — YouTube API 연동

**만들 것**
- `app/config.py`: `.env` + `config.yaml` 읽기. 키가 없어도 앱은 뜨고, 호출할 때 알기 쉬운 오류를 낸다.
- `app/db.py`: SQLite 연결과 테이블 만들기(우선 `videos`, `quota_usage`).
- `app/youtube/url_parser.py`: `watch?v=`, `youtu.be/`, `shorts/`, `embed/`, `live/`, 시간·목록 꼬리표가 붙은 주소, 영상 ID만 입력한 경우.
- `app/youtube/client.py`: 최신 영상 검색, 영상 상세, 인기 댓글. 오류 분류(키 없음·키 거부·할당량 초과·댓글 막힘·영상 없음·네트워크).
- `app/youtube/quota.py`: 사용 단위 기록, 같은 검색 10분 저장.
- 라우터: `GET /api/videos`(버튼 한 번, 입력 없이 기본 검색어로 동작), `POST /api/videos/resolve`(링크 직접 입력), `GET /api/videos/{id}`.
- 화면 골격을 [UI_SPEC.md](UI_SPEC.md)대로 새로 짠다: 사이드바, 통계 카드 4개, 3열, 반응형. 이 단계에서는 ①칸만 실제로 연결하고 ②③칸과 통계는 꺼진 상태로 "n단계에서 연결"이라고 표시한다. 예시 수치를 박아 넣지 않는다.
- 화면 ①칸 연결: 탭(키워드 검색 / URL 직접 입력), 검색창과 거르기, 썸네일·제목·채널·올린 날짜 목록, 선택, 오류 문구.
- `GET /api/status`: 사이드바 시스템 상태(이 단계에서는 YouTube 키 유무만).

**완료 기준**
- 링크 해석 테스트가 위 주소 형태와 잘못된 주소를 모두 다룬다.
- 저장해 둔 응답으로 검색·상세·댓글·오류 6종이 테스트된다.
- 오류 문구와 로그, `GET /api/status` 응답에 API 키 값이 실리지 않는다는 테스트가 있다(키가 있는지 없는지만 알려 준다).
- `RUN_LIVE=1`과 실제 키로 `live` 테스트 1개가 통과한다(대표 PC에서 확인).
- 화면에서 [영상 불러오기] 한 번으로 목록이 뜬다(사람이 확인).

**진행 상황 (2026-11-16)** — 코드와 자동 테스트는 끝났고, 사람이 확인할 두 가지가 남아 `[-]`로 둔다.
- [x] 링크 해석: 24가지 주소 형태 + 잘못된 주소 20가지 (`tests/unit/test_url_parser.py`)
- [x] 저장해 둔 응답(`tests/fixtures/youtube/`)으로 검색·상세·댓글·오류 6종 (`tests/integration/test_youtube_client.py`, `test_videos_api.py`)
- [x] 오류 문구·로그·응답·`GET /api/status`·화면에 키가 없다는 테스트 (`tests/integration/test_secret_leak.py`)
- [ ] `live` 테스트 1개(`tests/integration/test_live_youtube.py`) — 대표 PC에서 `.env`에 키를 넣고 `RUN_LIVE=1`로 확인
- [ ] 화면에서 [영상 찾기] 한 번으로 목록이 뜬다 — 대표 확인. (가짜 응답 서버 + 창 없는 크롬으로 검색·선택·10분 저장·오류·링크 입력·화살표 키·1920/1100/1000/390px 배치는 개발 중에 눌러 봤다)
- 화면은 작업 중에 바뀐 UI_SPEC 세 번째 판(검정·금색 에디토리얼 목업)을 따랐다. 제목 명조는 함께 들어온 `app/static/fonts/fonts.css`(Noto Serif KR)를 불러 쓴다.
- 설계와 다르게 둔 것: 같은 검색 10분 저장을 위해 `search_cache` 표를 더했다. 서비스 묶음은 `app/youtube/service.py`, 라우터 공용 준비는 `app/api/deps.py`에 두었다(DESIGN 3.1·4절에는 아직 없음).

### [-] 3단계 — 영상 맥락 수집

- `app/transcript/`(수동 붙여넣기, 비공식 조회는 꺼진 채로 규격만), `app/analysis/context.py`.
- 자막 → 없으면 제목·설명, 인기 댓글 20개, 댓글 막힌 영상 처리, 출처 표시, `video_context` 저장.
- 완료 기준: 자막 있음·없음·댓글 막힘 세 경우의 맥락 묶음 테스트. 너무 긴 자막을 모델 입력 길이에 맞게 자르는 규칙과 테스트.

**진행 상황 (2026-11-16)** — 코드와 자동 테스트는 끝났고, 사람이 화면에서 확인할 것이 남아 `[-]`로 둔다.
- [x] 자막 있음·없음(제목·설명 대체)·댓글 막힘(오류가 아니라 빈 목록) 세 경우 (`tests/integration/test_context_api.py`)
- [x] 길이 맞추기: 설명 1,500자, 댓글 200자 × 20개, 자막은 앞 절반 + 뒤 절반(`…(중략)…`), 짧음·딱 맞음·넘침, 결과는 항상 한도 이하 (`tests/unit/test_context_fit.py`)
- [x] 붙여넣기 정리(공백·빈 줄 줄이기, 시간 표시 유지, NFC, 20,000자 한도) (`tests/unit/test_transcript_manual.py`)
- [x] 인기 댓글 조회가 할당량 1단위로 기록되고, 저장된 맥락은 댓글을 다시 부르지 않음(`refresh=true`일 때만)
- [x] API 3개(`POST /api/videos/{id}/context`, `PUT`·`DELETE /api/videos/{id}/transcript`), 응답·로그에 API 키 없음
- [x] `video_context` 표(MIGRATIONS 2번째 덩어리), 2단계 DB에서 올려도 기존 자료 유지 (`tests/unit/test_db.py`)
- [x] D1(자막 출처)은 기본값 "수동 붙여넣기만". `transcript.provider: unofficial`이면 "켜져 있지 않다" 오류만 내고 `unofficial.py`는 만들지 않았다
- [ ] 화면: 영상을 고르면 자막 출처가 뜨고, 자막을 붙여 넣으면 출처가 바뀐다 — 대표 확인. (가짜 응답 서버 + 창 없는 크롬으로 선택·붙여넣기·저장·지우기·댓글 막힘·선택 해제·390px 배치는 개발 중에 눌러 봤다)
- [ ] 실제 YouTube 키로 인기 댓글을 받아 보는 확인(2단계 `live` 확인과 함께)
- PLAYBOOK과 다르게 둔 것: `build(video_id, refresh=False)`에 `refresh`를 더했다(저장된 댓글 재사용, PLAYBOOK "함정"의 할당량 규칙). 응답에 `transcript_text`(글 상자를 다시 채우려고)와 `transcript_truncated`·`context_chars`를 더했다. `config.yaml`에 `llm.context_chars: 6000`을 적었다.

### [-] P단계 — 프로그램으로 실행 (3단계 다음, 6단계 전)

- `app/desktop.py`(서버를 스레드로 띄우고 자체 창에 담는다), `JG-Marketing-Agent.cmd`(더블클릭 실행, 콘솔 창 없음). 화면과 서버 코드는 그대로. 상세는 PLAYBOOK P단계.
- 완료 기준: 더블클릭 → 창이 뜨고 [영상 찾기] 동작 → 창을 닫으면 남는 프로세스 없음(사람이 확인). 창을 띄우지 않는 자동 테스트(서버 시작·포트·종료·중복 실행).

**진행 상황 (2026-11-16)** — 코드·자동 테스트·개발 PC 창 확인은 끝났고, 대표가 직접 더블클릭해 보는 확인이 남아 `[-]`로 둔다.
- [x] 창 라이브러리 pywebview 6.2.1(BSD 3-Clause, Windows는 Edge WebView2). 공식 문서 확인 날짜·출처는 `app/desktop.py` 맨 위, 라이선스는 README "오픈소스 출처"
- [x] `app/desktop.py`: 중복 실행 확인(Windows 이름 있는 뮤텍스) → 빈 포트(운영체제가 고른 포트의 소켓을 uvicorn에 그대로 넘김) → 서버 스레드 → `/api/health` 대기 → 창(1600×1000, 최소 1100×720, 가운데) → 닫으면 서버 정지·잠금 해제. pythonw라 출력은 `data/desktop.log`, 알림은 메시지 상자
- [x] 바깥 링크(`target=_blank`, "YouTube에서 보기")는 pywebview 설정 `OPEN_EXTERNAL_LINKS_IN_BROWSER`로 기본 브라우저에서 연다. WebView2가 없으면 창을 열지 않고 설치를 안내한다
- [x] 자동 테스트 22개(`tests/integration/test_desktop.py`): 포트·준비 대기·실제 대시보드 서버로 열고 닫기·닫은 뒤 포트 닫힘·잠금 해제·중복 실행 거절·서버 시작 실패·창 오류·WebView2 없음·pywebview 없음·실행 파일 ASCII
- [x] 개발 PC에서 창 한 번 띄워 봄(2번 모니터, 확인용 환경 변수 `JG_DESKTOP_WINDOW_POS`): 자체 창에 화면이 그려지고 `/api/status`까지 불림 → 창을 닫자 서버 종료, python·WebView2 프로세스 남지 않음. 한글 이름 폴더에서 실행해도 같음
- [x] 브라우저로 여는 임시 `run-dashboard.cmd`는 지웠다. `scripts/run.ps1`은 개발용으로 그대로
- [ ] 대표 확인: `JG-Marketing-Agent.cmd` 더블클릭 → 창이 화면 가운데에 뜨고 [영상 찾기] 동작 → "YouTube에서 보기"가 기본 브라우저로 열림 → 창 닫기 → 작업 관리자에 남는 python 없음. 이미 떠 있을 때 한 번 더 더블클릭하면 "이미 실행 중" 알림
- 알아 둘 것: `.cmd`는 cmd.exe가 열기 때문에 더블클릭하면 콘솔 창이 잠깐 나타났다가 바로 닫힐 수 있다(`.cmd`는 pythonw를 띄우고 곧바로 끝난다. 개발 중에는 숨긴 채로 실행해 직접 보지는 못했다). 이것까지 없애려면 11단계 실행 파일(.exe)로 묶는다

### [-] 4단계 — Ollama 연동

- `app/llm/base.py`, `app/llm/registry.py`, `app/llm/ollama.py`: JSON 스키마 출력, 시간 제한, 재시도, 모델 없음·서버 꺼짐 오류.
- LLM을 바꿔 끼우는 틀을 이 단계에서 잡는다(DESIGN 5.2.1): 규격 하나, 설정의 `llm.active`로 공급자 선택. 구현하는 공급자는 Ollama 하나.
- `scripts/ollama_smoke.py`: 설치된 모델마다 한국어 JSON 한 번을 시켜 성공 여부와 시간을 본다. `GET /api/status`에 AI 항목 추가.
- 완료 기준: 가짜 응답으로 정상·깨진 JSON·시간 초과·서버 꺼짐·모델 없음 테스트. 확인 결과를 `docs/MODEL_EVAL.md`에 적는다. (초안 품질로 모델을 고르는 비교는 5단계 끝으로 옮겼다.)
- 주의: `ollama list`와 `ollama show <모델>`로 실제 설치 모델과 기능을 먼저 확인한다. `.env.example`의 모델 이름은 이 PC에 없는 이름이었다.

**진행 상황 (2026-11-16)** — 코드·자동 테스트·실제 모델 시험은 끝났고, Ollama를 끄고 켜며 위 줄을 보는 사람 확인이 남아 `[-]`로 둔다.
- [x] 요청 모양은 공식 문서(docs.ollama.com의 chat·thinking·structured outputs·show·errors, GitHub `docs/api.md`)와 이 PC의 실제 응답(Ollama 0.34.0)으로 확인했다. 확인 날짜·출처·실제로 본 것은 `app/llm/ollama.py` 맨 위
- [x] `app/llm/base.py`: `LLMClient` 규격(`generate_json`·`health`·`warmup`·`close`), `LLMHealth(provider, model, reachable, installed, local)`, `extract_json`(앞뒤 글·코드 블록·글 속 중괄호), `check_schema`(type·required·properties·items·enum만), 안 맞으면 사유를 붙여 한 번 다시 시키는 `TextJSONLLM`. 스키마 강제를 쓰는 Ollama도 같은 확인을 거친다
- [x] `app/llm/ollama.py`: `POST /api/chat`(`stream: false`, `format`에 JSON 스키마, 프롬프트에도 스키마 글, `options{temperature, num_ctx, num_predict}`, `keep_alive`). `/api/show`의 `capabilities`에 `thinking`이 있으면 `think: false`(문서의 `thinking.values`가 오면 그것을 따른다). 기능 목록은 한 번만 읽는다. 상태는 `/api/tags`(3초 제한, `qwen3.6` = `qwen3.6:latest`), 불러 두기는 빈 `messages`, 내리기는 `keep_alive: 0`
- [x] `app/llm/registry.py`: `build_llm(settings, *, transport=None)` — `llm.active`로 `llm.providers`에서 고른다. 없는 이름·모르는 종류는 `llm_provider_unknown`(한국어 문구, 지금 쓸 수 있는 종류 안내). 그래도 앱은 뜨고 AI 상태와 AI 기능에서 이유를 알린다
- [x] 설정(DESIGN 5.2.1 모양): `llm.active`, `timeout_seconds` 180, `num_ctx` 8192, `keep_alive` 30m, `providers.ollama.type`. 옛 키 `llm.provider`도 읽는다. `providers.*.api_key_env`의 이름은 비밀값 목록(`Settings.secret_env_names`)과 가리기 값(`secret_values()`)에 자동으로 들어간다(값은 아직 쓰지 않는다). 이름 자리에 키 모양 값을 쓰면 앱을 켤 때 막는다. `.env.example`의 `OLLAMA_MODEL`은 `qwen2.5:7b`(확정은 5단계 끝)
- [x] 오류: `llm_down`(→ `ollama serve`, OLLAMA_BASE_URL), `llm_model_missing`(→ `ollama pull`), `llm_timeout`, `llm_bad_output`(한 번 다시 시켜도 실패), 그리고 `llm_error`(그 밖 서버 오류), `llm_provider_unknown`
- [x] `GET /api/status`에 `ai{provider, model, reachable, installed, local, error}` (기존 `youtube` 그대로). `POST /api/llm/warmup`
- [x] 화면 위 줄 AI 상태: 「ollama · 모델 · 로컬」(연두) / 「ollama · 꺼짐」 / 「모델 · 모델 없음」(붉은 점, 마우스를 올리면 할 일). 30초마다 다시 보고 바뀐 것이 있을 때만 다시 그린다. "4단계에서 연결" 문구 지움
- [x] 화면 높이(1920×1080, 창 없는 크롬): 위 줄 높이 72px 그대로, 상태 문구는 한 줄(가장 긴 「ollama · qwen3.6:latest · 로컬」에서도). 영상 선택·검사 실패 2건일 때 3열 끝 **1039px**(6단계와 같음). 1401~1500px 너비에서도 가로 스크롤 없음
- [x] 테스트 74개 추가(481개 통과): 공통 코드 단위(앞뒤 글·코드 블록·필수 키 빠짐·자료형·재시도), Ollama `mock_http`(정상·깨진 JSON 후 재시도 성공·두 번 다 깨짐·시간 초과·서버 꺼짐·모델 없음·서버 오류·`format`·`think: false`·생각 기능 없는 모델엔 안 실음·불러 두기·비밀값 가림), 등록부(고르기·모르는 종류·없는 이름·옛 키·다른 종류가 있어도 뜸·api_key_env), 상태·불러 두기 API, 모듈 경계(`app/llm/` 밖에서 `app.llm.ollama`를 import하는 곳 없음, 안에서도 `registry`만), 진짜 Ollama 1회(`live`)
- [x] `scripts/ollama_smoke.py`를 이 PC에서 실제로 돌렸다. 결과는 [MODEL_EVAL.md](MODEL_EVAL.md)
- [ ] 사람 확인: 프로그램을 켠 채 Ollama를 끄면 30초 안에 위 줄 AI가 「ollama · 꺼짐」(붉은 점)으로, 다시 켜면 「ollama · qwen2.5:7b · 로컬」로 바뀐다
- PLAYBOOK과 다르게 둔 것: 규격에 `warmup()`·`close()`를 더했다(불러 두기 API가 공급자를 모르게). 오류 종류를 둘 더했다(`llm_error`, `llm_provider_unknown`). 상태 응답 `ai`에 `error`(문제일 때만)를 더했다. `create_app`·`build_services`에 `llm_transport`를 더해 YouTube 가짜 전송과 따로 받는다(테스트 도우미 `make_client`는 주지 않으면 「Ollama 꺼짐」으로 본다). 설정의 공급자 항목에 `model`·`base_url`을 적으면 `.env`보다 먼저 쓴다. 비교 스크립트는 Ollama 전용이라 `app.llm.ollama`를 직접 쓴다(경계 테스트는 `app/`만 본다). 버전 0.5.0, 화면 표시 4단계

### [-] 5단계 — 분석과 초안

- `app/llm/prompts.py`, `app/analysis/analyzer.py`, `app/analysis/drafter.py`.
- 2단계 생성(고민 한 줄 + 근거 → 초안), 검사 실패 사유를 넣어 최대 3번 재생성, 즉석 재생성 버튼.
- 라우터 `POST /api/analysis/{video_id}`, 화면 ②칸 연결.
- 완료 기준: 가짜 LLM으로 재생성 흐름 테스트(1번에 통과, 2번째에 통과, 3번 모두 실패). 화면에서 영상을 고르면 고민 한 줄과 초안이 보인다(사람이 확인).
- 6단계에서 넘어온 것: 검사에 걸린 초안을 승인 API가 거절한다는 테스트, V11용 이전 글(승인·게시한 글)을 DB에서 꺼내 `POST /api/validate`와 재생성에 넘기기. 재생성 프롬프트에는 `Validation.failure_lines()`를 쓴다.

**진행 상황 (2026-11-16)** — 코드·자동 테스트·실제 모델 비교는 끝났고, 대표가 화면에서 눌러 보는 확인과 초안 글을 읽어 보는 일이 남아 `[-]`로 둔다.
- [x] `app/llm/prompts.py`: 분석·초안 프롬프트와 JSON 스키마. 초안 규칙 7가지(운명원 홍보 담당자로 말함·시청자나 이용자인 척 금지, 고른 근거 문장을 따옴표로 담기, `brand.facts`에 있는 사실만, 전해 들은 효능「잘 본다던데」「유명하다던데」 금지, 링크·해시태그·줄바꿈·이모지 금지, 본문 35~115자, 표기는 쓰지 않음). 좋은 예 2개·나쁜 예 2개는 직접 썼고 실제 `validate()`로 좋은 예는 통과·나쁜 예는 V8·V9 / V10에 걸리는 것을 테스트로 확인한다(과제 예시 댓글은 쓰지 않았다). 영상 자료는 「[영상 자료 시작]…[끝]」으로 감싸고 그 안의 지시는 따르지 말라고 적는다
- [x] `app/analysis/analyzer.py`: 분석(주제·고민·톤·시청자 니즈·근거 문장과 출처). 근거는 3단계 `search_text`와 V6 방식(정규화 6자 이상, 그대로 들어 있거나 비슷한 정도 0.85 이상)으로 대조해 자료에 없는 것은 버리고, 출처는 코드가 자료에서 찾은 곳으로 고치고, 40자가 넘으면 마디에서 자른다. 하나도 안 남으면 한 번 다시 시키고, 그래도 없으면 제목을 근거로 대신한다(`fallback`)
- [x] `app/analysis/drafter.py` `DraftService`(analyze·generate·update_text·approve): 근거 하나를 골라(자막 > 댓글 > 설명 > 제목, [다른 초안]은 이미 쓴 근거를 피함) 모델이 본문만 쓰고 `[광고] `는 코드가 붙인다. `validate()`에 걸리면 걸린 항목 문구(`failure_lines()`)와 앞의 본문을 넣어 최대 3번, 다 걸리면 가장 덜 걸린 초안을 저장. 모델이 중간에 실패해도 이미 쓴 초안이 있으면 그것을 남긴다. 사람이 고친 글은 다시 검사하고, 승인할 때 서버가 다시 검사해 걸리면 거절(409)
- [x] DB: `analyses`(영상마다 하나), `drafts`(상태 draft·approved·superseded, 시도 횟수, 첫 시도 통과, 검사 결과, 사람이 고쳤는지). 마이그레이션 3번째로 덧붙임
- [x] API: `POST /api/analysis/{video_id}`, `POST /api/drafts`, `GET /api/drafts?video_id=`, `PATCH /api/drafts/{id}`, `POST /api/drafts/{id}/approve`(걸리면 409와 `failures`). `POST /api/validate`는 그대로, V11 이전 글은 DB에서(다른 영상에서 승인한 초안)
- [x] V10에 전해 들은 효능 표현을 더했다(「~다던데」「~라더라」「~라고 하던데」「잘 본다」「용하다」「입소문」「평이 좋」「인기 많」「다들 찾」 등). 홍보 담당자의 정상 표현은 계속 통과하는지 테스트
- [x] 화면 02칸: [분석하고 초안 만들기]를 눌러야 돈다(영상을 고르기만 하면 저장된 분석·초안만 불러온다). 「맥락 수집 → 분석 → 초안 → 검사」 진행 표시와 걸린 초, 「큰 모델은 처음에 1분쯤 걸립니다」. 분석 다섯 줄(한 줄 말줄임, 마우스를 올리면 전체), 근거 문장과 출처, AI 초안은 6단계 글 상자에(고칠 수 있음), 말투 이름표, [다른 초안 생성], [이 초안 승인]. 승인하면 흐름 띠 03. 「5단계에서 연결」 문구를 지웠고 03칸 실행 버튼은 8단계까지 꺼 둔다
- [x] 화면 높이(1920×1080, 가짜 YouTube·가짜 LLM + 창 없는 크롬): 분석과 초안이 채워지고 검사를 모두 통과한 상태에서 3열 끝 **1014px**, 승인한 뒤에도 1014px, 3번 모두 걸려 실패 항목이 펼쳐진 상태 1059px. 1100px·390px 너비에서 가로 스크롤 없음
- [x] 테스트 68개 추가(549개 통과, 4개는 `live`라 건너뜀): 가짜 LLM으로 1번에 통과·2번째에 통과(재시도 프롬프트에 걸린 항목이 들어감)·3번 모두 실패(가장 덜 걸린 것 저장), 지어낸 근거 버림·출처 고침, 표기를 코드가 붙임(모델이 붙여도 하나만), 사람이 고친 글 다시 검사, 검사에 걸린 초안 승인 409, 다른 초안은 다른 근거, V11이 승인한 초안과 비교, API 5개, 화면 문구, 프롬프트 예시가 실제 검사를 통과·실패, 전해 들은 효능 표현. 진짜 모델 호출은 `live` 1개
- [x] 모델 비교 `scripts/eval_drafts.py`를 이 PC에서 실제로 돌렸다(가상 맥락 5개 × 모델 3개 × 초안 3개, 한 번에 한 모델만 올리고 내림). 결과와 초안 글은 [MODEL_EVAL.md](MODEL_EVAL.md)
- [x] 모델 결정(D3 기본 규칙: 3번 안 통과율 → 첫 시도 통과율 → 빠른 것): **`qwen3.8:27b`** — 3번 안 100%·첫 시도 80%·초안 평균 10.2초(`qwen2.5:7b` 80%·67%·1.9초, `qwen3.6:latest` 93%·67%·4.1초). `app/config.py` 기본값과 `.env.example`을 바꿨다. 대표가 초안을 읽고 `.env`의 `OLLAMA_MODEL`로 바꿀 수 있다(`.env`가 기본값보다 먼저). 기본값을 바꾸며 기존 테스트 두 파일(`test_llm_registry.py`·`test_llm_api.py`)의 기본 모델 이름을 같이 고쳤다
- [ ] 사람 확인: 실제 영상을 골라 [분석하고 초안 만들기]를 눌러 분석 다섯 줄과 초안이 그럴듯한지, [다른 초안 생성]이 다른 근거로 쓰는지, 초안을 고쳐 [이 초안 승인]하면 흐름 띠가 03으로 넘어가는지
- [ ] 사람 확인: 대표가 MODEL_EVAL.md의 초안 글을 읽고 모델을 바꿀지 정한다(`.env`의 `OLLAMA_MODEL`)
- PLAYBOOK과 다르게 둔 것: 저장된 분석을 다시 부르는 `GET /api/analysis/{video_id}`를 더했다(영상을 고를 때 모델을 부르지 않으려고). `POST /api/drafts`에 `another`(이 영상에서 쓴 근거를 서버가 모아 피함)를 더했다. 초안 오류 종류 셋(`draft_not_found`·`draft_not_passed`·`draft_superseded`)과 오류 응답의 덧붙임 항목(`AppError.extra`, 승인 거절 때 `failures`)을 더했다. V11의 「이전 글」은 다른 영상에서 승인한 초안이다(같은 영상의 초안끼리는 비교하지 않음, 7단계에서 게시한 글이 생기면 더한다). V8~V10은 따옴표로 감싼 영상 속 말(영상 자료에 실제로 있고 브랜드와 8자 넘게 떨어진 것)을 검사에서 뺀다 — 영상 속 「제일 걱정」 같은 말을 인용했다고 최상급으로 걸리지 않게. 기존 테스트를 고친 곳: `test_db.py`의 스키마 버전 `== 2`를 `db.SCHEMA_VERSION`으로, `test_dashboard_page.py`의 버전 표시·꺼 둔 분석 칸 확인을 5단계 화면에 맞게. 버전 0.6.0, 화면 표시 5단계

### [-] 6단계 — 규칙 검사

- `app/analysis/validator.py`: DESIGN 5.4의 V1~V11.
- 완료 기준: 규칙마다 통과 예와 실패 예 테스트. 사람이 고친 글도 같은 검사를 거친다. 검사에 걸린 초안은 승인 API가 거절한다는 테스트.
- 5단계보다 먼저 해도 된다(LLM이 필요 없다). 순서를 바꾸면 이 문서에 적는다. → 실행 순서대로 P단계 다음, 4·5단계보다 먼저 했다(2026-11-16).

**진행 상황 (2026-11-16)** — 코드와 자동 테스트는 끝났고, 사람이 화면에서 확인할 것과 5단계 몫이 남아 `[-]`로 둔다.
- [x] `validator.py`: 네트워크·DB·LLM 없는 순수 함수. `CheckResult`, `Validation`, `ValidatorRules`, `validate(text, *, context_text, rules, brand_facts, previous_texts, evidence_quote=None)`, `find_evidence`, `normalize`. V1~V11 판정은 PLAYBOOK 표대로. 실패 문구는 "걸린 것 — 고치는 법" 한 줄(`failure_lines()`를 5단계 재생성 프롬프트에 그대로 쓴다)
- [x] 테스트 109개(`tests/unit/test_validator.py`): 규칙마다 통과 2개 이상·실패 2개 이상, 경계값 39·40·120·121자, 이모지·영문 섞인 글, 홍보 담당자의 정상 표현("공감돼요", "도움이 됐으면 해요", "상담받아 보세요", "상담받으실 수 있어요")이 V8~V10에 걸리지 않음, `brand.facts`에 쓴 구절은 V10 허용, 사람이 고친 글도 같은 함수로 검사, 추가 표현 설정, 긴 자료(약 2만 자)에서도 2초 안
- [x] `config.yaml`: `brand.facts`(D4 기본값 한 줄), `validator.extra_patterns`(빈 목록). `app/config.py`가 읽고 잘못된 항목은 앱을 켤 때 한국어 오류로 알린다 (`tests/unit/test_config.py`)
- [x] `POST /api/validate` — `{video_id, text}` → 검사 결과. 대조 자료는 3단계 `search_text`. 맥락이 없으면 만들어서 쓰고, 있으면 저장된 맥락을 그대로 써서 입력마다 불러도 YouTube를 다시 부르지 않는다 (`tests/integration/test_validate_api.py` 17개: 통과·링크 넣고 빼기·근거 없음·붙여 넣은 자막이 근거가 됨·댓글 막힘·설정 반영·잘못된 ID·키 없음·키가 응답과 로그에 없음)
- [x] 화면 02칸: 댓글 초안 글 상자(사람이 직접 씀, `[광고] `가 미리 들어감, 표기 금색), 입력이 0.4초 멈추면 검사, 글자 수 `n / 120자`, 통과 항목은 「11개 중 n개 통과」 한 줄로 접고 실패만 펼침, 이름표 `DRAFT · REVIEW REQUIRED` ↔ `CHECKED`, 통과하면 흐름 띠 03. 다른 초안 생성·영상 맥락 분석(5단계)은 꺼 둔 채
- [x] 화면 높이(1920×1080, 창 없는 크롬으로 잼): 영상을 고르고 자막 상자를 닫은 채 검사 실패 2건일 때 3열 끝 **1039px**(이전 1046px). 맞추려고 꺼 둔 분석 줄 간격, 초안 상자 위 여백, 열 아래 여백을 줄였다. 실패 문구가 두 줄이 되는 긴 글(115자)이면 1060px, 통과 목록까지 펼치면 1077px — 모두 1080 안
- [ ] 화면: 초안 칸에 링크를 넣으면 V2가 빨갛게 뜨고 지우면 사라진다 — 대표 확인. (가짜 응답 서버 + 창 없는 크롬으로 넣고 빼기, `CHECKED`, 1100px·390px 배치는 개발 중에 눌러 봤다)
- [x] 검사에 걸린 초안을 승인 API가 거절한다는 테스트 — 5단계에서 했다(`POST /api/drafts/{id}/approve` → 409 `draft_not_passed`, `tests/integration/test_drafts_api.py`). V11의 이전 글도 5단계부터 DB(다른 영상에서 승인한 초안)에서 꺼내 `POST /api/validate`와 초안 생성에 넘긴다
- PLAYBOOK과 다르게 둔 것: `rules`는 `ValidatorRules`(글자 수·브랜드·표기·추가 표현)로 받는다. `ContextService.current()`(저장된 맥락을 다시 쓰지 않고 묶음)와 `VideoService.stored()`를 더했다(기존 메서드는 그대로). 서비스 `app/analysis/checking.py`의 `CheckService`가 맥락과 설정을 모아 `validate`에 넘긴다. V8의 "상담받"은 권하는 말(상담받아 보세요·상담받으실 수 있어요 등)을 빼고 잡는다. V7은 근거를 글에서 찾는 경우 V6이 실패하면 "V6을 고치면 함께 풀립니다"로 함께 실패한다. 버전은 0.4.0(단계마다 하나씩, 화면에는 6단계)

### [ ] 7단계 — 운영 규칙과 기록

- `app/ops/rules.py`, `ledger.py`, `profiles.py`, `posts`·`runs`·`job_events` 테이블.
- 영상당 1개(DB 제약), 하루 상한(한국 날짜), 실패는 상한에 안 셈, 프로필 선택과 순환 배정, 시간순 기록 API.
- 완료 기준: 같은 영상 두 번 → 두 번째 거절. 상한 10개 뒤 11번째 거절. 자정(한국 시각) 넘으면 다시 가능. 동시에 두 요청이 와도 하나만 통과. 실패 후 재시도 가능. 기록이 시간순으로 나온다.

### [ ] 8단계 — 브라우저 연결

- sandbox 페이지(`/sandbox/watch`), `app/browser/`(작업 스레드, 크롬 실행, 한 글자씩 입력, 화면 캡처), assist 대상(열기만), `scripts/setup_profile.ps1`.
- 완료 기준: 창 없는 크롬으로 sandbox 전 과정(`e2e`) 통과. 일부러 낸 실패에서 사유와 캡처 파일이 남는다. 승인 전에는 게시 버튼이 눌리지 않는다는 테스트. 창이 보이는 실행은 2번 모니터에서 사람이 확인.

### [ ] 9단계 — 대시보드 완성

- [UI_SPEC.md](UI_SPEC.md) 전체를 채운다: 통계 카드 실제 값(`GET /api/stats/today`), 사이드바 메뉴와 시스템 상태, ③칸에 프로필 선택, 게시 방식(수동 승인 / 테스트 모드), 승인 버튼, 진행 상태, 시간순 기록, 오늘 남은 횟수.
- 좁은 화면 배치(UI_SPEC 6절) 확인.
- 처음 보는 사람이 설명 없이 쓸 수 있게: 다음에 누를 버튼 하나만 강조, 빈 상태 안내, 오류마다 다음 행동.
- 완료 기준: 화면 흐름 `e2e` 1개. 사람이 처음부터 끝까지 한 번 써 본다.

### [ ] 10단계 — 가점

- 뜨기 직전 영상 찾기(`app/youtube/rising.py`, 초안까지만), 프로필 3개 순환 배정 화면, 링크 직접 입력과 즉석 생성 다듬기.
- 완료 기준: 조회수·시간당 계산 경계값 테스트. 뜨기 직전 목록에서는 게시 작업이 열리지 않는다는 테스트.

### [ ] 11단계 — 시연 준비

- 한국어 README(설치·실행·설정·테스트), `docs/DEVIATIONS.md`(원문과 다른 점), `docs/INTENT.md`(제작 의도), 시연 순서 대본, 시연용 저장 데이터.
- 완료 기준: 새 폴더에 내려받아 README대로 실행된다. 공개 저장소에 비밀값이 없다. 시연 대본대로 2~3분 안에 끝난다.

### [ ] 12단계 — 다른 LLM 물리기 (제출 뒤, 또는 로컬 모델 품질이 모자랄 때 앞당김)

- 설정의 `llm.active`만 바꿔 다른 LLM을 쓴다(DESIGN 5.2.1, PLAYBOOK 12단계). 어댑터 하나가 한 걸음: `openai_compatible`(OpenAI·Grok·Gemini 호환 주소 등, API 키) → `anthropic`(Claude API, API 키) → `cli`(로그인된 Codex·Claude Code·Gemini CLI를 대신 실행) → 화면에서 공급자 고르기.
- 완료 기준: 분석·초안 코드를 바꾸지 않고 공급자만 바꿔 초안이 나온다. 자동 테스트는 키·CLI·인터넷 없이 통과. 키가 로그·응답에 없다. CLI 방식은 빈 폴더·도구 꺼짐·비대화 모드·시간 제한 조건이 테스트로 확인된다. CLI의 로그인 토큰 파일을 읽지 않는다.
