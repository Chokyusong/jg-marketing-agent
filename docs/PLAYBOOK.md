# 완성까지의 단계별 실행 계획 (PLAYBOOK)

- 작성: 2026-11-16, 기획 담당(Fable 5.2). 개발 담당(Opus 5.5)이 이 문서를 보고 한 단계씩 완성한다.
- 문서 역할
  - [DESIGN.md](DESIGN.md) — 왜, 무엇을 (구조와 규칙의 기준)
  - **이 문서** — 어떤 순서로, 어떤 파일·함수·API로 (실행 계획)
  - [STAGES.md](STAGES.md) — 단계별 상태 표기와 완료 기준 요약
  - [UI_SPEC.md](UI_SPEC.md) — 화면 모양과 구성
- 서로 다르면 DESIGN > PLAYBOOK > STAGES 순으로 따르고, 다르다는 사실을 사용자에게 알린다.
- 이 문서의 함수 이름과 표 모양은 **출발점**이다. 더 나은 이름이 있으면 바꿔도 되지만, 동작과 완료 기준은 바꾸지 않는다. 바꾼 곳은 끝날 때 보고한다.

## 0. 쓰는 법

1. 새 Opus 5.5 세션을 저장소 폴더에서 연다. 한 세션에 한 단계만 한다.
2. `/stage <번호>`를 치거나, "docs/PLAYBOOK.md의 <번호>단계를 진행해줘"라고 한다.
3. 세션은 AGENTS.md → DESIGN.md → 이 문서의 해당 단계 → (화면을 건드리면) UI_SPEC.md 순으로 읽고, 짧은 계획을 보여 준 뒤 구현한다.
4. 끝나면 `scripts/verify.ps1` 통과, STAGES.md 상태 표기, README, 옵시디언 기록을 갱신하고 로컬 커밋한다. push는 사용자가 말할 때만.
5. 단계가 끝날 때마다 "사람이 확인할 것"을 대표가 화면에서 직접 해 본다.

## 1. 지금 상태 (2026-11-16)

| 된 것 | 근거 |
|---|---|
| 0단계 하네스, 공개 저장소 | `AGENTS.md`, `scripts/verify.ps1`, 커밋 훅 |
| 2단계 코드: 설정, SQLite, YouTube 검색·상세·인기 댓글, 링크 해석, 할당량, 10분 저장, 오류 6종 | `app/config.py`, `app/db.py`, `app/youtube/`, `app/api/videos.py`, `app/api/status.py` |
| 목업 기준 화면 골격, 01칸 연결, 제목 글꼴 | `app/templates/index.html`, `app/static/` |
| 자동 테스트 181개 통과 | `tests/` |

남은 것: 2·3·P·6·4·5단계의 사람 확인, 그리고 7~11단계. 3단계 코드는 2026-11-16에 끝났다(테스트 252개 통과). P단계(프로그램으로 실행)도 같은 날 코드·자동 테스트가 끝났다(테스트 274개 통과, 대표가 직접 더블클릭해 보는 확인만 남음). 6단계(규칙 검사)도 같은 날 코드·자동 테스트가 끝났다(테스트 407개 통과, 화면 확인과 5단계 몫인 승인 거절 테스트가 남음). 4단계(Ollama 연결)도 같은 날 코드·자동 테스트·실제 모델 시험이 끝났다(테스트 481개 통과, 결과는 `docs/MODEL_EVAL.md`. Ollama를 끄고 켜며 위 줄을 보는 화면 확인이 남음). 5단계(분석과 초안, 모델 비교)도 같은 날 코드·자동 테스트·실제 모델 비교가 끝났다(테스트 549개 통과, 점검 보정(V12·권유 문장) 뒤 571개, 비교 결과와 고른 모델은 `docs/MODEL_EVAL.md`. 실제 영상으로 눌러 보는 화면 확인과 대표의 초안 읽기가 남음).

## 2. 실행 순서

단계 번호는 STAGES.md와 같고, **실행 순서는 아래 표**다. 6단계(규칙 검사)를 4·5단계보다 먼저 한다. LLM이 필요 없고, 5단계의 "검사에 걸리면 다시 생성"이 6단계 결과물을 쓰기 때문이다.

| 순서 | 단계 | 한 줄 | 끝나면 화면에서 되는 것 | 먼저 필요한 것 |
|---:|---|---|---|---|
| 1 | 2 마무리 | 실제 키로 확인 | 진짜 영상 목록 | **대표: API 키** |
| 2 | 3 | 영상 맥락 수집 | 자막 붙여넣기, 인기 댓글 수, 자막 출처 표시 | 결정 D1 |
| 2.5 | P | 프로그램으로 실행 | 더블클릭하면 자체 창이 뜬다(브라우저 탭·주소창 없음) | 결정 D7 |
| 3 | 6 | 규칙 검사 12종(V12는 5단계 점검에서 추가) | 초안 칸에 직접 써 보면 통과·실패가 뜬다 | 결정 D4 |
| 4 | 4 | Ollama 연결 | 위 줄 AI 상태가 실제 값 | Ollama 실행 |
| 5 | 5 | 분석과 초안 + 모델 비교 | 영상을 고르면 고민 한 줄과 초안 | 끝에 결정 D3 |
| 6 | 7 | 운영 규칙과 기록 | 오늘 통계, 작업 기록, 프로필 선택 | – |
| 7 | 8 | 브라우저 연결 | 프로필이 열리고 타이핑·승인·게시·확인 (테스트 페이지) | 결정 D2, D6 |
| 8 | 9 | 대시보드 완성 | 설명 없이 쓸 수 있는 화면 | – |
| 9 | 10 | 가점 | 뜨기 직전 영상 찾기, 프로필 자동 배정 표시 | – |
| 10 | 11 | 시연 준비 | README, 제작 의도, 시연 대본 | 결정 D5 |
| 그 뒤 | 12 | 다른 LLM 물리기 | 설정만 바꿔 OpenAI·Grok·Gemini·Claude API나 로그인된 CLI(Codex·Claude Code·Gemini)로 | 쓸 공급자의 키 또는 CLI 로그인 |

4단계에서 "LLM을 바꿔 끼우는 틀"(규격·등록부·설정 모양)을 먼저 만들고 Ollama만 구현한다. 다른 공급자는 12단계에서 어댑터만 더한다.

### MVP 범위 (대표 지시 2026-11-16: "MVP까지 완성")

MVP는 **과제의 필수 흐름이 처음부터 끝까지 도는 프로그램**이다: 프로그램 창 → 영상 불러오기 → 선택 → 고민 한 줄과 초안(규칙 검사 통과) → 승인 → 프로필이 열려 한 글자씩 입력·게시·확인(테스트 페이지) → 영상당 1개·하루 상한·기록.

- MVP에 드는 단계: **P → 6 → 4 → 5 → 7 → 8**. 8단계는 테스트 페이지(sandbox) 전 과정과, 실제 유튜브를 프로필로 열어 주는 것까지.
- MVP 뒤: 9(화면 다듬기), 10(가점), 11(시연 준비), 12(다른 LLM).
- 대표가 자리를 비운 동안은 기획 담당(Fable)이 단계마다 Opus 세션을 시작하고, 끝나면 점검하고, 다른 점은 그 세션에 고치게 한 뒤 다음 단계로 간다. 결정이 필요한 것은 아래 표의 기본값을 쓴다.
- 그동안 하지 않는 것: GitHub에 올리기(push), API 키·구글 계정이 필요한 확인, 실제 유튜브에 무엇이든 쓰는 일. 창이 필요한 확인은 2번 모니터에서만.

### 대표가 정하거나 해 줄 것

| 번호 | 무엇 | 언제까지 | 정하지 않으면 쓰는 기본값 |
|---|---|---|---|
| D0 | YouTube API 키 발급, `.env`에 직접 입력 | 지금 | 없음 (2단계 확인이 멈춘다) |
| D1 | 자막 출처: 수동 붙여넣기만 / 비공식 조회도 허용 | 3단계 전 | 수동 붙여넣기만 |
| D7 | 프로그램 창 방식 | **정해짐(2026-11-16): 내장 웹뷰 창.** 지금 화면을 그대로 창에 담는다 | – |
| D4 | 운명원에 대해 쓸 수 있는 사실 문장(`config.yaml`의 `brand.facts`) | 6단계 전 | "운명원은 연애 사주 상담을 하는 곳이다" 한 줄 |
| D3 | LLM 모델. 로컬 모델 초안이 못 쓸 정도면 외부 LLM을 쓸지(12-1을 앞당김) | 5단계 끝(비교 결과를 보고) | 비교에서 규칙 통과율이 가장 높은 로컬 모델 |
| D2 | 실제 유튜브 게시 방법: 사람이 직접만 / 승인 뒤 공식 API 추가 | 8단계 전 | 사람이 직접만 |
| D6 | 크롬 프로필에 구글 계정 로그인(유튜브1 필수, 2·3 선택) | 8단계 중 | 테스트 페이지 시연만 (로그인 불필요) |
| D5 | 시연 영상 올릴 곳(구글 드라이브 / 유튜브) | 11단계 전 | – |

### 시간이 모자라면 빼는 순서

1. 10단계의 프로필 자동 배정 화면 다듬기
2. 9단계의 SETTINGS 패널(설정값 보기)
3. 8단계 assist의 "게시했어요 → Data API로 확인"(사람이 확인했다고 누르는 것으로 대신)
4. 10단계 뜨기 직전 영상 찾기
5. 3단계 비공식 자막 조회(기본도 꺼져 있다)

빼면 안 되는 것: 6단계 규칙 검사, 7단계 영상당 1개·하루 상한·기록, 8단계 테스트 페이지 전 과정, 11단계 원문과 다른 점·제작 의도.

## 3. 기존 코드에 붙이는 방법 (모든 단계 공통)

2단계에서 만들어진 틀을 그대로 따른다.

- **테이블 추가**: `app/db.py`의 `MIGRATIONS` 끝에 한 덩어리를 붙인다. 이미 있는 덩어리는 고치지 않는다.
- **서비스 추가**: `app/api/deps.py`의 `Services`에 필드를 더하고 `build_services()`에서 만든다. 바깥 호출(LLM, 브라우저)은 가짜로 바꿀 수 있게 생성자 인자로 받는다(`create_app(settings, transport=..., clock=...)`처럼).
- **오류**: `app/errors.py`의 `ErrorKind`와 `ERROR_TEXTS`에 종류와 한국어 문구·다음 행동을 더한다. 라우터에서는 `AppError`를 던지기만 한다.
- **API**: `app/api/<이름>.py`에 라우터를 만들고 `app/main.py`에서 `include_router`. 입출력 모델은 `app/schemas.py`.
- **화면**: 칸마다 `app/static/js/<칸>.js`. 상태는 `state.js` 한 곳에 필드를 더하고 `subscribe`로 다시 그린다. 서버 호출은 `api.js`에 더한다. 꺼 둔 요소를 켤 때는 `is-off`와 "n단계에서 연결" 문구를 함께 지운다.
- **시간**: 날짜는 `app/youtube/quota.py`의 `kst_day()`(한국 날짜)를 쓴다. 테스트는 고정 시계(`Clock`)를 넣는다.
- **버전 표시**: 단계가 끝나면 `app/main.py`의 `STAGE`와 `APP_VERSION`(0.3.0, 0.4.0 …)을 올린다. `/api/health` 응답은 바꾸지 않는다.
- **테스트**: 단위는 `tests/unit/`, 라우터·서비스 묶음은 `tests/integration/`(`make_client`, `mock_http`, `fake_llm`, `tmp_db_path` 사용). 화면 문구 테스트는 `tests/integration/test_dashboard_page.py`에 보강.
- **비밀값**: 새 비밀값은 `.env.example`에 이름만, `app/config.py`의 `SECRET_ENV_NAMES`에 추가, 로그 가리기 대상에 포함.

---

## 4. 단계별 상세

### 2단계 마무리 — 실제 키 확인

**목표.** 2단계 완료 기준의 남은 두 줄(실제 호출, 화면 확인)을 채우고 `[x]`로 바꾼다.

**대표가 할 일**
1. Google Cloud 콘솔 → 프로젝트 만들기 → "YouTube Data API v3" 사용 설정 → 사용자 인증 정보 → API 키 만들기.
2. 키 제한: API 제한을 "YouTube Data API v3"만으로.
3. 저장소 폴더에서 `.env.example`을 `.env`로 복사하고 `YOUTUBE_API_KEY=` 뒤에 키를 직접 붙여 넣는다. 채팅에 키를 붙여 넣지 않는다.

**세션이 할 일**
- `$env:RUN_LIVE='1'`로 `live` 테스트 실행(검색 1회 = 100단위). 결과에 키가 찍히지 않는지 확인.
- 대표와 함께 `scripts\run.ps1` → [영상 찾기] → 목록·썸네일 확인.
- STAGES.md 2단계를 `[x]`로, README 갱신.

**함정.** 키를 방금 만들면 몇 분 동안 거부될 수 있다. `key_rejected`가 나오면 API 사용 설정 여부부터 본다.

---

### 3단계 — 영상 맥락 수집

**목표.** 영상 하나에 대해 "AI가 읽을 글 묶음"을 만든다. 자막 → 없으면 제목·설명, 그리고 인기 댓글.

**만들 것**

| 파일 | 내용 |
|---|---|
| `app/transcript/base.py` | `Transcript(text, source, language)`, `TranscriptProvider` 규격(`fetch(video_id) -> Transcript | None`) |
| `app/transcript/manual.py` | 사용자가 붙여 넣은 자막 저장·읽기. 정리: 앞뒤 공백, 연속 공백·빈 줄 줄이기, 최대 20,000자. 시간 표시(`1:23`)는 지우지 않는다(장면 언급의 근거가 된다) |
| `app/transcript/unofficial.py` | **D1이 "허용"일 때만.** 기본은 만들지 않고, `transcript.provider: unofficial`이면 "켜져 있지 않다"는 오류만 낸다 |
| `app/analysis/context.py` | `VideoContext`와 `ContextService` |

```text
VideoContext
  video              저장된 영상(StoredVideo)
  body               AI가 읽을 본문
  body_source        'transcript' | 'title_description'
  transcript_source  'manual' | 'unofficial' | 'none'
  comments           인기 댓글 목록(최대 20)
  comments_disabled  댓글이 막힌 영상인지

ContextService
  build(video_id) -> VideoContext            자막 → 없으면 제목·설명, 인기 댓글 조회(1단위), 저장
  set_manual_transcript(video_id, text)      붙여 넣은 자막 저장 후 다시 build
  clear_manual_transcript(video_id)
  prompt_text(context, max_chars) -> str     모델에 넣을 글. 길이 맞추기 규칙은 아래
  search_text(context) -> str                근거 대조용 전체 글(자르지 않음): 제목+설명+자막+댓글
```

**길이 맞추기 규칙(`prompt_text`).** 기본 한도 `llm.context_chars`(기본 6,000자). 설명은 1,500자까지, 댓글은 한 개 200자까지 20개. 자막이 남은 한도를 넘으면 **앞 절반 + 뒤 절반**을 남기고 가운데를 `…(중략)…`으로 바꾼다. 자른 사실을 `VideoContext`에 표시한다.

**DB (MIGRATIONS에 추가).** `video_context(video_id PK, transcript_source, transcript_text, comments_json, comments_disabled, body_source, built_at)`.

**API**

| 주소 | 동작 |
|---|---|
| `POST /api/videos/{id}/context` | 맥락을 만들고 요약을 돌려준다: 본문 출처, 자막 출처, 자막 글자 수, 댓글 수, 댓글 막힘 여부, 잘렸는지 |
| `PUT /api/videos/{id}/transcript` | `{text}` 저장 후 같은 요약 |
| `DELETE /api/videos/{id}/transcript` | 붙여 넣은 자막 지우기 |

**화면(02칸).** 영상을 고르면 맥락을 만들고 「자막 출처」 줄을 실제 값으로("붙여 넣은 자막 3,210자" / "자막 없음 · 제목과 설명으로 대신" / "인기 댓글 18개" / "댓글이 막힌 영상"). 「자막 붙여넣기」 접이식 글 상자와 [저장]. 안내 한 줄: "유튜브 영상 아래 '스크립트 표시'에서 복사해 붙여 넣으세요."

**테스트.** 자막 있음 / 자막 없음(제목·설명 대체) / 댓글 막힘 세 경우. 길이 맞추기(짧음·딱 맞음·넘침). 붙여넣기 정리. 댓글 조회가 1단위로 기록되는지. API 3개.

**완료 기준.** STAGES.md 3단계 + 위 테스트. 영상을 고르면 자막 출처가 뜨고, 자막을 붙여 넣으면 출처가 바뀐다(사람이 확인).

**함정.** 댓글 막힘은 오류가 아니라 정상 흐름이다(빈 목록으로 진행). 같은 영상의 맥락은 저장해 두고 다시 만들 때만 댓글을 새로 부른다(할당량).

---

### P단계 — 프로그램으로 실행 (3단계 다음, 6단계 전)

**왜.** 과제는 "웹에 올린 페이지가 아니라 내 컴퓨터에서 실행하는 프로그램"을 요구한다. 지금도 내 PC에서 돌지만 브라우저 탭에 `127.0.0.1` 주소로 떠서 웹페이지처럼 보인다. 대표 지시(2026-11-16): 대시보드는 프로그램 방식이어야 한다.

**목표.** 파일 하나를 더블클릭하면 **자체 창**이 뜬다. 브라우저 탭도 주소창도 없다. 창을 닫으면 프로그램이 끝난다. 화면 내용과 서버 코드는 지금 것을 그대로 쓴다(목업 기준 화면을 버리지 않는다).

**방식(D7, 대표 결정 2026-11-16: 내장 웹뷰 창).** 한 프로세스 안에서 FastAPI 서버를 스레드로 띄우고, 데스크톱 창 라이브러리(`pywebview`, Windows에서는 Edge WebView2)가 그 주소를 창에 담는다.

| 방식 | 장점 | 단점 |
|---|---|---|
| **내장 웹뷰 창 (권장)** | 진짜 프로그램 창, 지금 화면·코드 그대로, 나중에 실행 파일로 묶기 쉬움 | 라이브러리 하나 추가 |
| 크롬 앱 창(`chrome --app=주소`) | 추가 설치 없음 | 여전히 크롬 창이고 프로세스가 둘 |
| 화면을 네이티브로 다시 짜기(PySide 등) | 완전한 데스크톱 앱 | 목업 화면을 버리고 처음부터. 일정에 맞지 않음 |

**만들 것**

| 파일 | 내용 |
|---|---|
| `app/desktop.py` | `main()`: 빈 포트 고르기 → uvicorn을 스레드로 시작 → `/api/health`가 응답하면 창 열기(제목 "JG Marketing Agent", 기본 1600×1000, 최소 1100×720) → 창이 닫히면 서버를 멈추고 끝. 이미 실행 중이면 새로 띄우지 않고 알린다 |
| `JG-Marketing-Agent.cmd` | 더블클릭용. 검은 콘솔 창 없이 실행(`.venv`의 `pythonw.exe -m app.desktop`). `.venv`가 없으면 준비 방법 안내 |
| `scripts/run.ps1` | 그대로 둔다(개발용, 브라우저로 확인) |

- `requirements.txt`에 창 라이브러리 추가. 이름·지원 환경·라이선스는 **구현할 때 공식 문서로 확인**하고 README "오픈소스 출처"에 적는다.
- 창 안의 바깥 링크("YouTube에서 보기" 등)는 창 안에서 열지 않고 기본 브라우저로 연다.
- 저장소 루트의 `run-dashboard.cmd`(브라우저로 여는 임시 실행 파일, 커밋 안 됨)는 이 실행 파일로 바꾼다.
- 8단계의 브라우저 작업 스레드는 같은 프로세스에서 돈다. 창을 닫을 때 진행 중인 작업이 있으면 먼저 묻는다(8단계에서).
- 실행 파일 한 개(`.exe`)로 묶기는 11단계에서 한다(PyInstaller 등, 선택).

**테스트.** 창을 실제로 띄우지 않는다. 서버 시작·포트 고르기·준비 대기·종료·중복 실행 감지를 창 여는 함수만 가짜로 바꿔 확인한다. `app/desktop.py`는 창 라이브러리를 `main()` 안에서 import해, 라이브러리가 없어도 자동 테스트가 돈다.

**완료 기준.** `JG-Marketing-Agent.cmd` 더블클릭 → 창이 뜨고 [영상 찾기]가 된다 → 창을 닫으면 남는 python 프로세스가 없다(사람이 확인). 콘솔 창이 보이지 않는다. 자동 테스트 통과.

**함정.** 창 라이브러리의 화면 루프는 주 스레드를 차지한다 — 서버는 다른 스레드에서. 서버가 뜨기 전에 창을 열면 빈 화면이 된다 — 준비될 때까지 기다린다. 한글 경로에서도 실행되는지 확인한다.

---

### 6단계 — 규칙 검사 (LLM 없이, 4·5단계보다 먼저)

**목표.** 어떤 글이든 넣으면 V1~V12의 통과·실패가 나온다. AI가 쓴 글과 사람이 고친 글이 같은 검사를 거친다.

**만들 것.** `app/analysis/validator.py` — 네트워크·DB·LLM 없이 도는 순수 함수.

```text
CheckResult(code, name, passed, message)        예: ('V2', '링크 없음', False, '주소로 보이는 글자가 있습니다: example.com')
Validation(passed, checks, char_count, evidence_quote)

validate(text, *, context_text, rules, brand_facts, previous_texts, evidence_quote=None) -> Validation
find_evidence(text, context_text) -> str | None   글과 영상 자료에 함께 나오는 가장 긴 구절
normalize(s) -> str                               대조용: 공백·문장부호·이모지 제거, 소문자, NFC
```

**규칙별 판정**

| 번호 | 판정 방법 |
|---|---|
| V1 | NFC로 맞춘 뒤 앞뒤 공백을 뺀 글자 수가 `min_chars`~`max_chars`. 줄바꿈이 있으면 실패. **홍보 표기를 포함한 전체 길이** |
| V2 | `http`, `www.`, `글자.com/kr/net/co/io/me/app/shop` 모양이 있으면 실패 |
| V3 | `#`이 있으면 실패 |
| V4 | `comment.disclosure` + 공백으로 시작하지 않으면 실패 |
| V5 | `comment.brand`가 1~2번 들어 있어야 통과 |
| V6 | 근거 구절이 영상 자료에 실제로 있는가. `evidence_quote`가 주어지면 `normalize` 후 포함 여부(안 되면 유사도 0.85 이상인 구간이 있는지). 주어지지 않으면 `find_evidence`로 찾는다. 6자(정리 후) 미만이면 실패 |
| V7 | 글 자체가 그 근거를 담고 있는가. 글과 근거 구절이 정리 후 4자 이상 연속으로 겹쳐야 통과 |
| V8 | 직접 이용한 후기 표현. 목록(정규식)에 걸리면 실패: 봤는데·봐봤·받아봤·받았는데·다녀왔·가봤·상담받·후기·소름·맞더라·맞췄·맞히 등 |
| V9 | 소비자인 척하는 표현: 보고 싶다/싶어/싶네·봐야겠·가봐야·예약했·나도 한번·저도 한번·저도 비슷한 고민 등 |
| V10 | 확인할 수 없는 효능·최상급: 100%·무조건·반드시·보장·제일·최고·유일·족집게·용한·유명 등. `brand.facts`에 그대로 있는 구절은 허용 |
| V11 | 이전에 승인·게시한 글들과 유사도 0.6 이상이면 실패(표기와 브랜드 이름은 빼고 비교) |
| V12 | 허용 글자만 썼는가: 한글(완성형·낱자), 영문, 숫자, 공백, 기본 문장부호(`. , ! ? ~ ' " ‘ ’ “ ” … · - ( ) [ ] % : /`). 한자·일본어 글자·그 밖의 문자·이모지가 있으면 실패하고 걸린 글자를 알려 준다 (5단계 점검에서 추가) |

- 표현 목록은 `validator.py` 안의 상수로 두고, `config.yaml`의 `validator.extra_patterns`로 더할 수 있게 한다.
- 실패 문구는 **무엇이 걸렸고 어떻게 고치면 되는지** 한 줄로(화면과 재생성 프롬프트 양쪽에 쓴다).

**API.** `POST /api/validate` — `{video_id, text}` → `Validation`. 영상의 `search_text`(3단계)를 대조 자료로 쓴다.

**화면(02칸).** 댓글 초안 글 상자를 켠다. 아직 AI 초안은 없으므로 사람이 직접 쓴다. 입력이 멈추면(0.4초) 검사를 불러 글자 수와 통과·실패 목록을 그린다. 표기 `[광고]`는 금색. 상태 이름표: `DRAFT · REVIEW REQUIRED` ↔ `CHECKED`.

**테스트.** 규칙마다 통과 예 2개와 실패 예 2개 이상(총 50개 안팎). 경계값(39·40·120·121자). 이모지·영문 섞인 글. 사람이 고친 글도 같은 함수로 검사된다는 테스트. API 테스트.

**완료 기준.** STAGES.md 6단계. 초안 칸에 링크를 넣으면 V2가 빨갛게 뜨고, 지우면 사라진다(사람이 확인).

**함정.** V8~V10은 과하게 잡는 쪽이 안전하다(걸리면 다시 만들면 된다). 다만 "공감돼요", "도움이 됐으면" 같은 홍보 담당자의 정상 표현이 걸리지 않는지 통과 예로 확인한다.

---

### 4단계 — Ollama 연결

**목표.** 로컬 모델에게 "이 모양의 JSON으로 답해라"를 시키고 받는 통로를 만든다. 프롬프트와 초안은 5단계다.

**이 PC의 모델(2026-11-16 확인, `ollama show`).** Ollama 0.34.0.

| 모델 | 크기 | 생각 출력 | 12GB 그래픽 메모리 |
|---|---|---|---|
| `qwen2.5:7b` | 4.7GB | 없음 | 전부 올라감(빠름) |
| `qwen3.8:27b` | 17GB | 있음 | 일부만 올라감(느림) |
| `qwen3.6:latest` | 23GB | 있음 | 일부만 올라감(더 느림) |

**만들 것**

| 파일 | 내용 |
|---|---|
| `app/llm/base.py` | `LLMClient` 규격: `generate_json(*, system, user, schema, temperature, max_tokens) -> dict`, `health() -> LLMHealth(provider, model, reachable, installed, local)`. 공통 코드: 받은 글에서 JSON 꺼내기(`extract_json`), 스키마와 맞는지 확인(`check_schema`, 필수 키·자료형만 보는 작은 검사), 안 맞으면 한 번 다시 시키기 |
| `app/llm/registry.py` | `build_llm(settings, *, transport=None) -> LLMClient` — `config.yaml`의 `llm.active` 이름으로 `llm.providers`에서 찾아 만든다. 모르는 `type`이면 "아직 지원하지 않는 공급자" 오류 |
| `app/llm/ollama.py` | `POST {base}/api/chat` — `model`, `messages`, `stream: false`, `format: <JSON 스키마>`, `options{temperature, num_ctx, num_predict}`, `keep_alive`. 생각 출력 기능이 있는 모델이면 `think: false`. 시작 때 `/api/show`로 기능을 읽어 둔다 |
| `scripts/ollama_smoke.py` | 설치된 모델마다 한국어 JSON 한 번을 시켜 성공 여부와 걸린 시간을 표로 |

**공급자를 바꿔 끼울 수 있게(DESIGN 5.2.1).** 이 단계에서 구현하는 공급자는 Ollama 하나지만, 틀은 지금 잡는다.
- 분석·초안 코드(5단계)는 `LLMClient` 규격만 쓴다. `ollama`라는 이름을 `app/llm/` 밖에서 import하지 않는다(테스트로 확인).
- 설정을 DESIGN 5.2.1의 모양으로 바꾼다: `llm.active`, `llm.providers.<이름>.type`. 지금 `config.yaml`의 `llm.provider: ollama`는 `llm.active: ollama`로 옮기고 옛 키도 읽어 준다.
- `providers`에 `ollama` 말고 다른 항목이 있어도 앱은 뜬다. 고른 공급자(`active`)의 종류가 아직 없을 때만 오류를 낸다.
- API 키를 쓰는 공급자를 위해 `app/config.py`가 `providers.*.api_key_env`에 적힌 환경 변수 이름을 비밀값 목록과 로그 가리기 대상에 자동으로 넣게 한다(값은 12단계 전까지 쓰지 않는다).
- `LLMHealth.local`이 거짓인 공급자는 화면에 "외부"로 표시한다.

- 설정: `.env`의 `OLLAMA_BASE_URL`, `OLLAMA_MODEL`. `config.yaml`의 `llm: {active: ollama, timeout_seconds: 180, num_ctx: 8192, keep_alive: "30m", context_chars: 6000, providers: {ollama: {type: ollama}}}`.
- 오류 종류 추가: `llm_down`(서버 꺼짐) · `llm_model_missing` · `llm_timeout` · `llm_bad_output`(JSON이 깨짐, 한 번 다시 시도 후에도 실패). 각각 한국어 문구와 다음 행동(`ollama serve`, `ollama pull <모델>` 등).
- `GET /api/status`에 `ai: {provider, model, reachable, installed, local}` 추가. 위 줄 AI 상태를 실제 값으로("ollama · 모델 이름 · 로컬").
- `POST /api/llm/warmup` — 모델을 미리 불러 둔다(시연 전용 버튼은 9단계).

**테스트(`mock_http`).** 정상 / 깨진 JSON 후 재시도 성공 / 두 번 다 깨짐 / 시간 초과 / 서버 꺼짐 / 모델 없음. 요청에 `format`과 `think: false`가 실리는지. 상태 API. 등록부: `active`로 공급자를 고르는지, 모르는 종류면 알기 쉬운 오류인지, 옛 설정 키도 읽는지. `extract_json`·`check_schema`: 앞뒤에 다른 글이 붙은 답, 코드 블록에 싸인 답, 필수 키가 빠진 답.

**완료 기준.** STAGES.md 4단계(모델 비교는 5단계로 옮김). `scripts/ollama_smoke.py` 결과를 `docs/MODEL_EVAL.md`에 적는다. 위 줄 AI 상태가 Ollama를 끄면 "꺼짐"으로 바뀐다(사람이 확인).

**함정.** 새 모델 계열의 요청 옵션은 기억에 의존하지 말고 Ollama 문서와 `ollama show`로 확인한다. 큰 모델의 첫 응답은 모델을 읽어 들이느라 1분 넘게 걸릴 수 있다 — 시간 제한과 화면 안내에 반영한다.

---

### 5단계 — 분석과 초안, 모델 비교

**목표.** 영상을 고르면 고민 한 줄과 규칙을 통과한 초안이 나온다. 끝에 모델을 정한다.

**만들 것**

| 파일 | 내용 |
|---|---|
| `app/llm/prompts.py` | 분석·초안·재작성 프롬프트와 JSON 스키마 |
| `app/analysis/analyzer.py` | `analyze(context) -> Analysis` |
| `app/analysis/drafter.py` | `DraftService` |
| `scripts/eval_drafts.py` | 모델 비교 |
| `tests/fixtures/contexts/*.json` | 직접 쓴 가상 영상 맥락 5개(서로 다른 연애 주제, 자막 발췌·설명·댓글 포함). 실제 영상 내용을 베끼지 않는다 |

```text
Analysis   topic(주요 주제) · concern(핵심 고민 한 줄, 40자 안쪽) · tone(영상 톤) · viewer_needs(시청자 니즈)
           evidence: [{quote, source}] 2~4개   quote는 영상 자료에 실제로 있는 구절, source는 transcript|title|description|comment

DraftService
  analyze(video_id) -> Analysis                      낮은 온도(0.2). 근거 구절마다 V6로 대조해 없는 것은 버린다
  generate(video_id, *, avoid_quotes=()) -> Draft    높은 온도(0.8). 최대 3번 시도
  update_text(draft_id, text) -> Draft               사람이 고친 글. 다시 검사
  approve(draft_id) -> Draft                         검사 통과한 것만. 아니면 오류
```

**초안 만들기 흐름**
1. 근거 구절 하나를 고른다(`avoid_quotes`에 없는 것, 자막 > 댓글 > 설명 > 제목 순).
2. 모델에게 **본문만** 쓰게 한다. 홍보 표기 `[광고] `는 코드가 앞에 붙인다(모델이 빼먹을 수 없게). 모델에게 주는 길이 한도는 `max_chars − 표기 길이 − 1`.
3. `validate()`로 검사한다. 걸리면 실패 문구를 넣어 다시 쓰게 한다(최대 3번).
4. 세 번 다 걸리면 실패가 가장 적은 것을 저장하고 걸린 항목을 표시한다(사람이 고친다).
5. [다른 초안 생성]은 이미 쓴 근거 구절을 `avoid_quotes`에 넣고 다시 1번부터.

**프롬프트 원칙(반드시 포함)**
- 역할: 운명원의 홍보 담당자. 영상을 보고 공감하며 권한다. 시청자·이용자인 척하지 않는다.
- 근거 구절을 댓글 안에 직접 언급한다("○○라는 말", "○분쯤 ○○ 장면").
- 운명원에 대해서는 `brand.facts` 문장만 쓴다. 후기·효능·실적을 지어내지 않는다.
- 금지: 링크, 해시태그, 줄바꿈, 이모지 남용.
- 좋은 예 2개와 나쁜 예 2개(왜 나쁜지 한 줄). 예시는 규칙을 통과하는 글로 직접 쓴다.
- 출력은 JSON 스키마대로: `{body, used_quote, tone_label}`.

**DB.** `analyses(video_id PK, topic, concern, tone, viewer_needs, evidence_json, model, created_at)`, `drafts(id, video_id, body, evidence_quote, evidence_source, tone_label, model, attempts, validation_json, passed, status['draft'|'approved'|'superseded'], edited_by_human, created_at)`.

**API.** 화면이 단계별로 진행을 보이도록 셋으로 나눈다.

| 주소 | 동작 |
|---|---|
| `POST /api/analysis/{video_id}` | 맥락이 없으면 만들고 분석 → `Analysis` |
| `POST /api/drafts` | `{video_id}` → 초안 생성 → `Draft`(검사 결과 포함) |
| `GET /api/drafts?video_id=` | 그 영상의 초안들(최신이 위) |
| `PATCH /api/drafts/{id}` | `{body}` 사람이 고침 → 다시 검사한 `Draft` |
| `POST /api/drafts/{id}/approve` | 승인. 검사 실패면 409와 걸린 항목 |

**화면(02칸).** 영상을 고르면 "맥락 수집 → 분석 → 초안 → 검사"를 차례로 표시하며 채운다. 영상 맥락 분석 다섯 줄, 근거 구절과 출처, 초안과 글자 수, 말투 분류, 규칙 검사 목록, [다른 초안 생성], [이 초안 승인]. 승인하면 흐름 띠 03이 밝아지고 03칸 큰 버튼의 조건이 풀린다(실행은 8단계).

**모델 비교(`scripts/eval_drafts.py`).** 가상 맥락 5개 × 모델마다 초안 3개. 표: 첫 시도 통과율, 3번 안 통과율, 평균 시간, 초안 원문. `docs/MODEL_EVAL.md`에 붙이고 **대표가 초안을 읽고 모델을 고른다(D3)**. 통과율이 같으면 읽었을 때 자연스러운 쪽, 그것도 같으면 빠른 쪽.

**테스트(`fake_llm`).** 1번에 통과 / 2번째에 통과 / 3번 모두 실패 / 모델이 지어낸 근거를 버리는지 / 표기를 코드가 붙이는지 / 사람이 고친 글 재검사 / 실패한 초안 승인 거절 / [다른 초안]이 다른 근거를 쓰는지.

**완료 기준.** STAGES.md 5단계. 진짜 모델로 영상 3개에서 서로 다른 초안이 나오고 각각 그 영상의 구절을 담고 있다(사람이 확인).

**함정.** 작은 모델은 길이를 못 맞춘다 — 길이는 프롬프트로 부탁하고 검사로 강제한다. 분석과 초안을 한 번에 시키지 않는다(근거를 먼저 고정해야 지어내지 않는다).

---

### 7단계 — 운영 규칙과 기록

**목표.** 영상당 1개, 하루 상한, 기록을 코드와 DB로 강제한다. 평가 15점이 여기 있다.

**DB.**

```text
posts       id, target('sandbox'|'youtube'), video_id, profile, draft_id, status('reserved'|'posted'|'failed'),
            day(한국 날짜), created_at, posted_at          UNIQUE(target, video_id)
runs        id, at, action('analyze'|'draft'|'approve'|'post'), video_id, video_title, profile, comment_text,
            target, result('success'|'failure'|'info'), reason, screenshot_path, job_id       지우지 않는다
job_events  job_id, at, state, message
```

**만들 것**

| 파일 | 내용 |
|---|---|
| `app/ops/rules.py` | `reserve(video_id, target, profile, draft_id) -> post_id` — `BEGIN IMMEDIATE` 안에서 오늘 수(예약+게시) 확인 → 넣기. `mark_posted`, `mark_failed`, `remaining_today(target)`, `is_commented(video_id, target)` |
| `app/ops/profiles.py` | `list_profiles()`(설정의 이름 ↔ 폴더 `profile-1`…), `pick_auto(target)` — 가장 오래 안 쓴 프로필 |
| `app/ops/ledger.py` | `record(...)`, `recent(limit)`, `today_stats(target)` |

- 거절 오류 종류: `already_commented`(이미 댓글을 단 영상) · `daily_limit_reached`(오늘 상한) · `draft_not_approved`.
- 실패한 예약은 `failed`가 되고 상한에 세지 않는다. 같은 영상을 다시 시도하면 그 행을 `reserved`로 되돌린다.
- 5단계의 분석·초안·승인도 `runs`에 `info`로 남긴다(작업 기록의 ACTION 열).

**API.** `GET /api/profiles` · `GET /api/records?limit=` · `GET /api/stats/today?target=` · 영상 목록 항목에 `commented: {sandbox, youtube}` 추가(기존 필드는 그대로).

**화면.** 제목 영역의 오늘 통계 4개를 실제 값으로. 작업 기록 표. 03칸 설정(프로필 선택, 작업 방식, 일일 제한, 오늘 작업 n / 상한)을 켠다. 01칸 목록에 "댓글 단 영상" 표시.

**테스트.** 같은 영상 두 번 → 두 번째 거절. 상한 뒤 거절. 한국 자정이 지나면 다시 가능(고정 시계). 스레드 두 개가 동시에 예약 → 하나만 성공. 실패 후 다시 시도 가능. 실패는 상한에 안 셈. sandbox와 youtube를 따로 셈. 기록이 시간순. 통계 계산(기록 없음이면 성공률 없음).

**완료 기준.** STAGES.md 7단계. 승인만 해도 작업 기록에 줄이 생기고 통계가 바뀐다(사람이 확인).

---

### 8단계 — 브라우저 연결

**목표.** 버튼을 누르면 크롬 프로필이 열리고, 테스트 페이지에서 한 글자씩 타이핑 → 사람 승인 → 게시 → 내 댓글 확인까지 진행 상태와 함께 보인다. 실제 유튜브는 열어 주기만 한다. **DESIGN 6절을 먼저 다시 읽는다.**

**먼저.** `requirements.txt`에 `playwright` 추가. 크롬은 설치된 것을 쓴다(`channel="chrome"`, 브라우저 내려받기 없음).

**테스트 페이지(sandbox)**
- `GET /sandbox/watch?v=<영상ID>&profile=<이름>` — 이 앱의 자체 화면. 영상 제목, 영상 자리 상자, 「댓글 추가...」 입력, 「취소」「댓글」 단추, 댓글 목록. 위에 "통제된 테스트 페이지 — 실제 유튜브가 아닙니다" 표시. 유튜브 화면을 베끼지 않는다.
- `POST /sandbox/api/comments`, `GET /sandbox/api/comments?v=` — `sandbox_comments` 표에 저장.
- 실패 스위치: `&fail=hide_button`(게시 단추 없음) · `slow`(응답 지연) · `reject`(저장 거절). 실패 처리 시험용.

**작업(job)**

```text
JobService
  start(video_id, draft_id, profile, target) -> job_id    승인된 초안인지 확인 → rules.reserve → 작업 스레드에 넣기
  approve(job_id)        승인 대기 중인 작업의 게시를 허락
  confirm(job_id, posted: bool)   assist에서 사람이 "게시했어요 / 안 했어요"
  cancel(job_id)
  get(job_id) -> 상태, 지난 단계, 메시지, 실패 사유, 캡처 유무, 댓글 보기 주소
```

상태: 대기 → 프로필 실행 → 댓글 입력 → **승인 대기** → 게시 중 → 확인 → 게시 완료 / 실패. 한 번에 작업 하나.

| | sandbox | assist(실제 유튜브) |
|---|---|---|
| 여는 방법 | Playwright `launch_persistent_context(프로필 폴더, channel="chrome")` | 자동화 없이 크롬 실행(`chrome.exe --user-data-dir=… <주소>`) |
| 입력 | 댓글 상자 누르고 한 글자씩(글자마다 `typing_delay_ms` 사이 무작위) | 사람이 직접. 대시보드에 초안 [복사] |
| 게시 | 대시보드 [게시 승인]을 누른 뒤 단추 클릭 | 사람이 직접 |
| 확인 | 페이지에서 내 댓글 글을 찾음 | 사람이 [게시했어요] → Data API로 조회, 못 찾으면 "게시됨(확인 못 함)" |
| 승인 대기 시간 | 5분 넘으면 실패 "승인 시간 초과" | 10분 |

- 끝나면 `rules.mark_posted` / `mark_failed`와 `ledger.record`. 실패하면 `error_screenshots/<작업ID>.png` 저장.
- Playwright는 **동기 API를 전용 스레드 하나에서만** 쓴다.
- 프로필 폴더: `%LOCALAPPDATA%\JGMarketingAgent\profiles\profile-1`… 화면 이름만 유튜브1.
- 창: `browser.headless`(기본 false, 테스트는 true), `browser.window_position`(기본 `60,-1060`, 2번 모니터).
- `scripts/setup_profile.ps1`(ASCII로 작성) — 일반 크롬을 프로필 폴더로 열어 사람이 구글 로그인.
- `GET /api/status`에 `browser: {chrome_found, playwright_ready, profiles: [{name, exists}]}`.

**API.** `POST /api/jobs` · `GET /api/jobs/{id}` · `POST /api/jobs/{id}/approve` · `POST /api/jobs/{id}/confirm` · `POST /api/jobs/{id}/cancel` · `GET /api/jobs/{id}/screenshot`.

**화면(03칸).** 큰 버튼을 켠다(조건: 승인된 초안 + 댓글 안 단 영상 + 오늘 남은 횟수). 진행 단계 표시를 0.5초마다 갱신. 승인 대기에서 [게시 승인]. assist에서는 초안 [복사]와 [게시했어요]·[게시 안 함]. 실패 사유와 화면 캡처 링크. 끝나면 [댓글 보기].

**테스트.** 단위: 상태 전이, 승인 없이는 게시 단계로 못 감, 시간 초과. `e2e`(창 없는 크롬, 임시 서버): 전 과정 성공 / `fail=hide_button`에서 실패 사유와 캡처 파일 / 같은 영상 두 번째 시작 거절 / 한 글자씩 입력됐는지(입력 이벤트 수). assist는 크롬 실행 명령을 가짜로 바꿔 인자만 확인.

**완료 기준.** STAGES.md 8단계. 2번 모니터에 크롬이 열려 타이핑 → 승인 → 게시 → 확인이 눈에 보인다(사람이 확인). 주 모니터에 창이 뜨지 않는다.

**함정**
- 같은 프로필 폴더를 일반 크롬이 열고 있으면 Playwright가 못 연다 → "그 프로필의 크롬 창을 닫아 주세요" 안내.
- `--reload`로 서버를 켜면 작업 스레드가 끊긴다 → 8단계부터 `run.ps1`은 `--reload` 없이.
- **실제 유튜브 화면의 요소를 찾거나 누르는 코드를 쓰지 않는다.** assist는 주소로 여는 것이 전부다.

---

### 9단계 — 대시보드 완성

**목표.** 처음 보는 사람이 설명 없이 세 칸을 쓴다(사용성 10점).

- **다음 행동 하나만 강조.** 영상 전 → [영상 찾기], 고른 뒤 → 초안, 승인 뒤 → [브라우저에서 영상 열기]. 흐름 띠와 함께 움직인다.
- **한글 이름을 앞에.** 통계·시스템 상태·작업 기록 머리글의 영문 이름표 옆이나 위에 한글 이름을 둔다(오늘 처리 · 초안 · 게시 완료 · 성공률 / AI 모델 · 유튜브 · 브라우저 / 시간 · 영상 · 작업 · 댓글 · 상태 · 프로필).
- **글자 한 단계 키우기.** 본문 14px, 목록 제목 14px, 보조 글 12px, 가장 작은 이름표 11.5px 이상. 1920×1080에서 3열이 스크롤 없이 보이는지 다시 확인.
- 빈 상태·불러오는 중·오류마다 문구와 다음 행동. 긴 작업(분석·초안)에는 걸리는 시간 안내.
- SETTINGS 패널: 설정값 보기(글자 수, 상한, 프로필과 폴더 준비 여부, 모델, 브랜드 사실), [모델 미리 불러오기].
- 작업 기록 [VIEW ALL]: 전체 기록과 실패 사유.
- 메뉴를 누르면 해당 칸으로 이동하고 잠깐 강조.
- 좁은 화면(1000px, 390px) 다시 확인.

**테스트.** `e2e` 한 개: 가짜 YouTube·가짜 LLM으로 찾기 → 선택 → 초안 → 승인 → sandbox 실행 → 기록 확인까지.

**완료 기준.** STAGES.md 9단계. 프로젝트를 모르는 사람에게 화면만 주고 끝까지 가게 해 본다(사람이 확인).

---

### 10단계 — 가점

1. **뜨기 직전 영상 찾기.** `app/youtube/rising.py` — `publishedAfter = 지금 − 34시간`, `q = rising.query`, 최대 50개(100단위) → 영상 상세(1단위) → 조회수 1,000~5,000이면서 `조회수 ÷ 경과 시간 ≥ 150` → 시간당 조회수 내림차순. `GET /api/videos/rising`(10분 저장). 화면: 거르기 옆 [뜨기 직전] 단추, 줄마다 "시간당 n회". 이 목록의 영상은 **초안까지만** — 03칸 큰 버튼이 막히고 이유가 적힌다.
2. **프로필 배정.** 03칸에서 "자동 배정"을 고르면 이번에 쓸 프로필 이름을 미리 보여 준다. 기록에서 영상마다 다른 프로필이 돌아가며 쓰인 것이 보이게.
3. **링크 직접 입력·즉석 초안.** 이미 있다. URL 탭 → 불러오기 → 바로 분석·초안으로 이어지는지 확인만.

**테스트.** 경계값(조회수 999·1,000·5,000·5,001, 시간당 149·150, 올린 지 1분). 뜨기 직전 영상으로 작업 시작 거절. 프로필 순환(3개가 차례로).

---

### 11단계 — 시연 준비

**만들 것**
- `README.md` 완성: 무엇인가, 원문과 다른 점(요약), 설치·실행·설정, 프로필 준비, 테스트, 구조, 오픈소스 출처.
- `docs/DEVIATIONS.md`: 원문과 다르게 만든 곳과 이유(DESIGN 2절을 심사자가 읽기 좋게).
- `docs/INTENT.md`: 제작 의도. 왜 3열인가, 왜 근거 대조인가, 왜 DB로 강제하는가, 왜 사람 승인인가, 무엇을 포기했는가.
- `docs/DEMO.md`: 시연 대본(아래).
- 시연용 저장 데이터: 인터넷·할당량 문제에 대비해 미리 찾아 둔 영상과 붙여 넣은 자막이 든 DB 사본을 쓰는 방법.

**시연 대본 초안(2분 40초)**

| 시간 | 화면 | 말 |
|---|---|---|
| 0:00 | 대시보드 | 무엇을 만들었고, 원문과 어디가 왜 다른지 한 문장씩 |
| 0:15 | 01 | [영상 찾기] 한 번 → 목록. 하나 선택 |
| 0:30 | 02 | 고민 한 줄, 근거 구절, `[광고]`로 시작하는 초안, 글자 수 |
| 0:50 | 02 | 초안에 링크를 넣어 본다 → 검사 실패, 버튼 막힘. 지우고 승인 |
| 1:10 | 03 | 테스트 모드로 실행 → 크롬 프로필이 열리고 한 글자씩 입력 → [게시 승인] → 게시 → 내 댓글 확인 |
| 1:50 | 기록·통계 | 기록 한 줄, 오늘 1/10. 같은 영상으로 다시 실행 → 거절 |
| 2:05 | 03 | 수동 승인 모드: 실제 유튜브가 프로필로 열리고 초안 복사까지. 게시는 사람이 |
| 2:20 | 01 | [뜨기 직전] → 조건에 맞는 영상, 초안까지만 |
| 2:35 | 끝 | 저장소 주소 |

**찍기 전 확인.** 화면에 API 키·구글 이메일이 없는지. 모델 미리 불러오기. 크롬 창은 2번 모니터. 영상 링크가 로그인 없는 창에서 재생되는지.

**완료 기준.** STAGES.md 11단계. 새 폴더에 내려받아 README대로 실행된다. 올리기 전 `scripts\check_secrets.py --all` 통과.

---

### 12단계 — 다른 LLM 물리기 (제출 뒤, 또는 로컬 모델 품질이 모자랄 때 앞당김)

**목표.** 설정의 `llm.active`만 바꾸면 Ollama 대신 다른 LLM으로 분석·초안이 돌아간다. 분석·초안 코드는 한 줄도 바꾸지 않는다. **DESIGN 5.2.1을 먼저 읽는다.**

**순서.** 어댑터 하나가 한 걸음이다. 위에서부터 필요한 만큼만 한다.

| 걸음 | 파일 | 물리는 것 | 인증 |
|---|---|---|---|
| 12-1 | `app/llm/openai_compatible.py` | OpenAI API, xAI Grok, Gemini의 OpenAI 호환 주소, OpenRouter, LM Studio 등 — 주소(`base_url`)와 모델만 다르다 | `.env`의 API 키(`api_key_env`가 가리키는 이름) |
| 12-2 | `app/llm/anthropic.py` | Claude API | `.env`의 API 키 |
| 12-3 | `app/llm/cli.py` | 로그인된 CLI를 대신 실행: Codex, Claude Code, Gemini CLI | CLI 자신의 로그인. 이 앱은 토큰을 읽지 않는다 |
| 12-4 | 화면 | SETTINGS 패널에서 공급자 고르기, 외부 전송 안내 | – |

**공통 규칙**
- 주소, 모델 이름, 요청 모양, CLI 옵션은 **구현할 때 각 회사 공식 문서와 `<명령> --help`로 확인**한다. 기억이나 추측으로 쓰지 않는다. 확인한 날짜와 출처를 어댑터 파일 맨 위에 적는다.
- 스키마 강제를 지원하면 그 기능을 쓰고, 아니면 `base.py`의 `extract_json`·`check_schema`로 확인한다.
- 오류는 4단계의 종류를 그대로 쓴다(`llm_down`, `llm_model_missing`, `llm_timeout`, `llm_bad_output`)에 `llm_auth`(키 거부·로그인 안 됨)와 `llm_rate_limited`를 더한다. 한국어 문구와 다음 행동 포함.
- API 키는 `.env`에만. 요청 머리말·주소·오류 문구가 로그에 찍힐 때 키가 가려지는지 테스트한다(2단계 `test_secret_leak.py`와 같은 방식).
- 테스트는 `mock_http`(API)와 가짜 실행기(CLI)로. 진짜 호출은 `@pytest.mark.live`.
- `scripts/eval_drafts.py`가 `--provider`를 여러 개 받아 공급자끼리 비교할 수 있게 한다.

**12-3 CLI 방식의 안전 조건(반드시 지킨다)**
- 영상 자막과 댓글은 남이 쓴 글이다. 파일·명령 도구를 가진 CLI에 넣으면 글 속의 지시를 따를 수 있다.
- 그래서: 빈 임시 폴더를 작업 폴더로, 도구 사용을 끄거나 읽기 전용으로, 한 번 답하고 끝나는 비대화 모드로, 시간 제한을 걸고 실행한다. 이 네 가지를 그 CLI가 지원하지 않으면 그 CLI는 물리지 않는다.
- 프롬프트는 표준 입력으로 넘긴다(명령줄 인자에 넣지 않는다). 셸을 거치지 않고 인자 목록으로 실행한다.
- CLI가 저장해 둔 로그인 토큰 파일을 읽거나 복사하지 않는다.
- `health()`는 CLI가 설치돼 있고 로그인돼 있는지만 본다(버전 명령 등 부작용 없는 것으로).

**화면.** 위 줄 AI 상태에 공급자·모델·"로컬/외부". SETTINGS에서 설정에 있는 공급자 목록과 준비 여부(키 있음 / CLI 설치·로그인됨)를 보이고 고를 수 있게 한다. 외부 공급자를 고르면 "영상 제목·설명·자막·댓글이 이 회사로 전송됩니다. 비용이 들 수 있습니다" 안내와 확인.

**완료 기준.** `llm.active`를 바꾸고 서버를 다시 켜면 같은 화면 흐름으로 초안이 나온다. 자동 테스트는 키·CLI·인터넷 없이 통과한다. 키가 로그·응답에 없다. CLI 방식은 빈 폴더·도구 꺼짐 조건이 테스트로 확인된다(실행 인자 검사).

**앞당기는 경우.** 5단계 모델 비교(D3)에서 로컬 모델의 초안이 쓸 수 없을 정도면 12-1만 5단계 직후에 한다.

---

## 5. 화면 요소가 켜지는 단계

| 요소 | 단계 |
|---|---|
| 01칸 전체, 위 줄 YOUTUBE 상태 | 2 (완료) |
| 02칸 자막 출처, 자막 붙여넣기 | 3 (코드 완료) |
| 프로그램 창, 더블클릭 실행 | P |
| 02칸 초안 글 상자(직접 쓰기), 글자 수, 규칙 검사 목록 | 6 |
| 위 줄 AI 상태 | 4 |
| 02칸 영상 맥락 분석, AI 초안, 다른 초안 생성, 승인 | 5 |
| 오늘 통계 4개, 작업 기록, 03칸 설정, 댓글 단 영상 표시 | 7 |
| 03칸 큰 버튼, 진행 단계 표시, 승인·복사·확인 단추, 위 줄 BROWSER 상태 | 8 |
| SETTINGS 패널, VIEW ALL, 한글 이름표, 글자 키우기 | 9 |
| 뜨기 직전 단추, 자동 배정 미리 보기 | 10 |
| SETTINGS의 LLM 공급자 고르기, 외부 전송 안내 | 12 |

## 6. 단계가 끝날 때마다 기획 담당이 확인하는 것

1. `scripts/verify.ps1` 통과, `scripts/check_secrets.py --all` 통과.
2. 그 단계의 "완료 기준"과 "테스트" 항목이 실제로 있는지.
3. 화면을 창 없이 찍어 UI_SPEC과 비교(화면을 건드린 단계).
4. 절대 규칙: 실제 유튜브 자동 조작 코드 없음, 표기 없는 초안이 승인되지 않음, 키가 응답·로그·테스트 자료에 없음, 기존 API 유지.
5. "구현함 / 자동 검증함 / 사람이 확인함 / 안 함"이 나뉘어 보고됐는지.
