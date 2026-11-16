# 단계별 개발 계획

- 구조와 규칙의 기준은 [DESIGN.md](DESIGN.md)다. 이 문서는 순서와 완료 기준만 적는다.
- 화면 모양과 구성의 기준은 [UI_SPEC.md](UI_SPEC.md)다(대표가 넣은 목업).
- **단계마다 만들 파일·함수·API·테스트의 상세는 [PLAYBOOK.md](PLAYBOOK.md)에 있다.** 이 문서는 상태 표기와 완료 기준 요약이다.
- **실행 순서: 2 마무리 → 3 → 6 → 4 → 5 → 7 → 8 → 9 → 10 → 11.** 6단계(규칙 검사)를 4·5단계보다 먼저 한다(PLAYBOOK 2절).
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

### [ ] 4단계 — Ollama 연동

- `app/llm/base.py`, `app/llm/registry.py`, `app/llm/ollama.py`: JSON 스키마 출력, 시간 제한, 재시도, 모델 없음·서버 꺼짐 오류.
- LLM을 바꿔 끼우는 틀을 이 단계에서 잡는다(DESIGN 5.2.1): 규격 하나, 설정의 `llm.active`로 공급자 선택. 구현하는 공급자는 Ollama 하나.
- `scripts/ollama_smoke.py`: 설치된 모델마다 한국어 JSON 한 번을 시켜 성공 여부와 시간을 본다. `GET /api/status`에 AI 항목 추가.
- 완료 기준: 가짜 응답으로 정상·깨진 JSON·시간 초과·서버 꺼짐·모델 없음 테스트. 확인 결과를 `docs/MODEL_EVAL.md`에 적는다. (초안 품질로 모델을 고르는 비교는 5단계 끝으로 옮겼다.)
- 주의: `ollama list`와 `ollama show <모델>`로 실제 설치 모델과 기능을 먼저 확인한다. `.env.example`의 모델 이름은 이 PC에 없는 이름이었다.

### [ ] 5단계 — 분석과 초안

- `app/llm/prompts.py`, `app/analysis/analyzer.py`, `app/analysis/drafter.py`.
- 2단계 생성(고민 한 줄 + 근거 → 초안), 검사 실패 사유를 넣어 최대 3번 재생성, 즉석 재생성 버튼.
- 라우터 `POST /api/analysis/{video_id}`, 화면 ②칸 연결.
- 완료 기준: 가짜 LLM으로 재생성 흐름 테스트(1번에 통과, 2번째에 통과, 3번 모두 실패). 화면에서 영상을 고르면 고민 한 줄과 초안이 보인다(사람이 확인).

### [ ] 6단계 — 규칙 검사

- `app/analysis/validator.py`: DESIGN 5.4의 V1~V11.
- 완료 기준: 규칙마다 통과 예와 실패 예 테스트. 사람이 고친 글도 같은 검사를 거친다. 검사에 걸린 초안은 승인 API가 거절한다는 테스트.
- 5단계보다 먼저 해도 된다(LLM이 필요 없다). 순서를 바꾸면 이 문서에 적는다.

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
