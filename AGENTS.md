# AGENTS.md — JG 마케팅 에이전트 작업 규칙

유튜브 영상을 분석해 홍보 표기(`[광고]`)가 붙은 댓글 초안을 만들고, 사람이 승인하는 로컬 대시보드(FastAPI). 제이지그룹 AI PM 채용 과제 TRACK 2.

## 기준 문서 (이 순서로 읽는다)

1. 이 파일
2. [`docs/DESIGN.md`](docs/DESIGN.md) — 구조와 규칙의 기준. 특히 2절(원문과 다르게 만드는 부분), 6.1(브라우저 대상)
3. [`docs/STAGES.md`](docs/STAGES.md) — 단계별 할 일과 완료 기준, 현재 상태 표기
4. [`docs/UI_SPEC.md`](docs/UI_SPEC.md) — 화면 기준. 화면을 건드리는 단계에서 읽는다

설계 문서끼리 또는 코드와 어긋나면 고치기 전에 사용자에게 알린다.

## 절대 규칙

1. **실제 유튜브 화면을 자동 조작하는 코드 금지.** 자동 타이핑·게시·확인은 이 앱의 sandbox 페이지(`/sandbox/watch`)에서만. 실제 유튜브(assist)는 크롬을 프로필·영상 주소로 여는 것까지만(DESIGN 6.1).
2. **시청자 사칭·광고 관계 숨김 금지.** 모든 댓글은 `config.yaml`의 `comment.disclosure`(`[광고]`)로 시작한다. 지어낸 이용 후기, 소비자인 척하는 표현을 만들지 않는다.
3. **비밀값을 남기지 않는다.** API 키·토큰·브라우저 프로필 폴더를 코드·테스트 자료·로그·커밋에 넣지 않는다. `.env`를 읽어서 출력하지 않는다. 테스트용 가짜 키는 실행할 때 조립한다(`"AIza" + "x" * 35`).
4. **기존 기능·테스트를 허락 없이 지우지 않는다.** `/`, `/api/health`, `tests/test_health.py` 포함. 실패하는 테스트를 지우거나 건너뛰게 바꿔 덮지 않는다.
5. **한 번에 한 단계.** 단계가 끝나면 `.\scripts\verify.ps1`이 통과해야 다음으로 간다. 다음 단계 모듈이나 빈 껍데기를 미리 만들지 않는다.
6. **나눠서 보고한다.** "구현함 / 자동 검증함 / 사람이 확인함 / 안 함"을 구분한다. 안 한 것을 했다고 쓰지 않는다.
7. **Git.** 단계가 끝나면 commit해도 된다. push·저장소 공개 설정 변경은 사용자가 요청할 때만. force push 금지. pre-commit 훅을 건너뛰지 않는다(`--no-verify` 금지).

## 창 규칙 (대표 공통 규칙)

- 시험·녹화·스크린샷용 창(Playwright·Chromium, 데스크톱 앱 창)은 **절대 주 모니터에 띄우지 않는다.**
- 브라우저 자동화는 기본 headless. 녹화도 창 없이.
- 창이 꼭 필요하면 위쪽 2번 모니터: Chromium 인수 `--window-position=60,-1060` (주 모니터 (0,0) 1920×1080, 위쪽 모니터 (0,-1080) 1920×1080). 배치가 바뀌었을 수 있으면 PowerShell `[System.Windows.Forms.Screen]::AllScreens`로 먼저 확인한다.
- 서브에이전트나 다른 세션에 브라우저 일을 맡길 때도 이 조건을 지시에 넣는다.
- 서버 동작 확인은 가능하면 브라우저 대신 FastAPI `TestClient`로 한다.

## 자주 쓰는 명령 (PowerShell, 저장소 루트)

```powershell
py -3.12 -m venv .venv                                         # 처음 한 번
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks                            # 처음 한 번(비밀값 검사 훅)

.\scripts\run.ps1                    # 대시보드 http://127.0.0.1:8765 (--reload 붙일 수 있음)
.\scripts\verify.ps1                 # 단계 끝 검증: ruff check → pytest -q

.\.venv\Scripts\python.exe -m pytest tests\unit -q          # 단위
.\.venv\Scripts\python.exe -m pytest tests\integration -q   # 통합
.\.venv\Scripts\python.exe -m pytest -m e2e                 # 화면 자동화(Playwright 필요, 8단계~)
$env:RUN_LIVE='1'; .\.venv\Scripts\python.exe -m pytest -m live; Remove-Item Env:RUN_LIVE   # 진짜 호출
.\.venv\Scripts\python.exe scripts\check_secrets.py --all   # 추적 파일 전체 비밀값 검사
```

PowerShell 5.1이다. `&&`, `||`, 삼항 연산자를 쓰지 않는다. `.ps1` 파일은 ASCII로 쓴다(5.1은 BOM 없는 UTF-8 한글을 깨뜨린다).

## 폴더 구조 (요약)

```text
app/            FastAPI 앱 (main.py, templates/, static/) — 2단계부터 DESIGN 3.1 구조로 늘어난다
docs/           DESIGN.md, STAGES.md, UI_SPEC.md, design/(레퍼런스 이미지 자리)
scripts/        verify.ps1, run.ps1, check_secrets.py
tests/          conftest.py(공통 도우미), unit/, integration/, e2e/, fixtures/, test_health.py
.githooks/      pre-commit → scripts/check_secrets.py --staged
.claude/        Claude Code 프로젝트 설정, /stage·/verify 명령
config.yaml     비밀이 아닌 규칙(커밋함)
.env            비밀값만(커밋 금지, .env.example 참고)
```

## 테스트 규칙

- 자동 테스트는 **인터넷·API 키·Ollama 없이** 통과해야 한다. 외부 호출은 `tests/conftest.py`의 `mock_http`(httpx.MockTransport), `fake_llm`(정해 둔 JSON을 차례로 반환)으로 바꾼다.
- 그 밖의 도우미: `tmp_db_path`(임시 SQLite 경로), `base_config`·`make_config`(임시 설정), `clean_env`(비밀 환경 변수 제거), `fixture_json`(`tests/fixtures/` 읽기).
- 진짜 YouTube·Ollama 호출은 `@pytest.mark.live` — `RUN_LIVE=1`일 때만 돈다.
- 브라우저 테스트는 `@pytest.mark.e2e` — Playwright가 없으면 건너뛴다. 항상 headless.
- 새 기능마다 테스트를 쓴다. `validator.py`와 `ops/rules.py`는 가장 두껍게 테스트한다(DESIGN 3.2).

<!-- bootstrap-project-context:start -->
## 프로젝트 기록과 필수 문맥

- 프로젝트 문맥 폴더: `C:\Users\User\Documents\Obsidian\LLM WIKI\60. 프로젝트\JG 마케팅 에이전트`
- 개발·제작을 시작하기 전에 다음 문서를 읽는다.
1. [[00. JG 마케팅 에이전트 MAIN|프로젝트 MAIN]]
2. [[02. 로드맵|로드맵]]
3. [[03. 구조와 주요 결정|구조와 주요 결정]]
4. [[90. 아카이브/2026-11-16 JG 마케팅 에이전트 작업 기록|가장 최근 작업 기록]]
- 사용자가 따로 요청하지 않아도 코드·설정·설계·검증 결과·Git 상태·운영 또는 전달 상태·다음 작업 순서가 바뀌면 최종 답변 전에 기록한다. 절차는 `project-worklog` 스킬을 따른다.
  1. 같은 날짜의 `90. 아카이브/YYYY-MM-DD JG 마케팅 에이전트 작업 기록.md`를 만들거나 기존 기록에 이어서 변경 이유, 실제 변경, 검증, 미완료, Git·전달 상태와 다음 순서를 남긴다.
  2. 작업을 끝낼 때마다 `00. JG 마케팅 에이전트 MAIN.md` 맨 위 `## 지금 상태 (YYYY-MM-DD)` 세 줄(단계·다음 한 가지·막힌 것)을 고치고 제목 날짜를 그날로 바꾼다. 줄마다 한 줄로 짧게, 해당 없으면 `없음`.
  3. 같은 MAIN의 "최근 작업 기록" 맨 위에 그날 기록 링크와 한 줄 요약을 넣는다. 사용자는 MAIN부터 보므로 하위 노트만 고치면 갱신이 안 된 것처럼 보인다.
  4. 로드맵 등 관련 핵심 노트도 같은 작업 안에서 갱신한다.
- Claude Code에서는 계정 설정의 검사가 파일을 바꾼 턴이 끝날 때 1~3번 누락을 잡아 한 번 되돌린다. 로드맵은 검사하지 못하고, 다른 도구(Codex 등)에는 이 검사가 없으니 위 순서를 직접 지킨다.
- 사용자에게 보이는 기능·API·UI·지원 환경·배포 방법·테스트 기준이 바뀌면 README 또는 사용자 문서도 실제 상태로 갱신한다.
- 계획, 구현, 자동 검증, 수동 확인, 배포·공개를 구분한다.
- 단순 질문·읽기 전용 조회는 불필요한 기록을 만들지 않는다. 노트를 고치기 전에 백업 사본을 따로 만들지 않는다.
- 비밀번호, 토큰, 키, 개인정보, 고객 데이터, 비공개 URL·IP, 운영 로그·DB·백업 원문은 프로젝트 노트에도 기록하지 않는다.
- 문맥 폴더에 접근하거나 저장하지 못하면 누락 범위와 이유를 최종 답변에 알린다.
<!-- bootstrap-project-context:end -->

<!-- bootstrap-project-context:llm-wiki:start -->
## LLM WIKI 연동

옵시디언 `LLM WIKI`는 LLM Wiki 방식(원본 자료 → 요약·개념 페이지 → `index.md`·`log.md`)으로 운영된다. 이 저장소 작업에서는 다음을 지킨다.

- 옵시디언 기록은 이 프로젝트 폴더(`C:\Users\User\Documents\Obsidian\LLM WIKI\60. 프로젝트\JG 마케팅 에이전트`) 안에서만 한다. `LLM WIKI/index.md`·`log.md`와 지식 폴더(`10`~`50`)의 노트·개념 페이지는 고치지 않는다.
  - 예외: 새 MAIN(최상위 프로젝트 입구) 노트를 만들면 `LLM WIKI/index.md`의 "프로젝트 입구" 구역에 `- [[노트 이름]] — 한 줄 요약` 한 줄만 추가한다. 상위 프로젝트 아래 하위 폴더 프로젝트는 상위 MAIN에 링크 한 줄만 둔다.
- 이 프로젝트 밖에서도 다시 쓸 일반 지식(도구 사용법, 설치·빌드 함정과 해결법, 외부 서비스·라이브러리 특성 등)을 새로 알게 되면, 그날 작업 기록 맨 끝에 `## 재사용 지식` 항목으로 한두 줄씩 따로 적는다. 프로젝트 고유 결정·상태와 비밀값·주소·고객 정보는 적지 않는다. 이 항목은 LLM WIKI 점검 때 개념 페이지로 옮겨진다.
- 옵시디언 노트 이름에 `#`, `|`, `[`, `]`, `^`를 쓰지 않는다(Obsidian 링크가 걸리지 않는다).
- 작업을 끝낼 때마다(최종 답변 전) `00. JG 마케팅 에이전트 MAIN.md`의 맨 위 `## 지금 상태 (YYYY-MM-DD)` 세 줄을 고친다(위 "프로젝트 기록과 필수 문맥" 절과 같은 규칙).
<!-- bootstrap-project-context:llm-wiki:end -->
