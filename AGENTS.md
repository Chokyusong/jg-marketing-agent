# AGENTS.md — JG 마케팅 에이전트 작업 규칙

유튜브 영상을 분석해 댓글 초안(광고 표기 `[광고]` 켬/끔)을 만들고, 사람이 검토하고 [댓글 달기]를 누르면 고른 크롬 프로필로 그 영상에 한 글자씩 입력·게시·확인하는 로컬 프로그램(FastAPI + 자체 창). 제이지그룹 AI PM 채용 과제 TRACK 2.

## 기준 문서 (이 순서로 읽는다)

1. 이 파일
2. [`docs/DESIGN.md`](docs/DESIGN.md) — 구조와 규칙의 기준. 특히 2절(원문대로 하는 것과 더한 것), 6.1(두 가지 게시 방식)
3. [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md) — 완성까지의 실행 계획. 단계마다 만들 파일·함수·API·테스트와 **실행 순서**(2 마무리 → 3 → P → 6 → 4 → 5 → 7 → 8 → 9 → 10 → 11 → 12)
4. [`docs/STAGES.md`](docs/STAGES.md) — 단계별 상태 표기와 완료 기준 요약
5. [`docs/UI_SPEC.md`](docs/UI_SPEC.md) — 화면 기준. 화면을 건드리는 단계에서 읽는다

서로 다르면 DESIGN > PLAYBOOK > STAGES 순으로 따르고, 다르다는 사실을 사용자에게 알린다.

## 절대 규칙

1. **사람이 검토하고 누른 댓글만 게시한다(R3).** 실제 게시(기본)는 어떤 영상이든 `app/browser/youtube_driver.py`가 **이번 작업의 영상 주소 하나만** 열어 입력·게시·확인한다(페이지가 그 영상 밖으로 옮겨 가면 멈춘다). 연습 모드는 이 앱의 `/sandbox/watch`만 연다(DESIGN 6.1). 어느 쪽이든 규칙 검사(V1~V6·V8~V11, docs/COMMENT_REFACTOR.md 5절)를 통과한 초안에 사람이 [댓글 달기]를 눌러야 시작하고(서버는 승인한 초안만 받는다), 영상당 1개·하루 상한·한 영상에 계정 하나·한 번에 작업 하나를 코드와 DB가 지킨다. 자동 테스트와 개발 세션은 **실제 유튜브에 입력하거나 게시하지 않는다**(가짜 유튜브 페이지만. `tests/conftest.py`가 막는다). 실제 유튜브 첫 게시는 대표가 로그인한 뒤 대표가 한다.
2. **지어낸 후기 금지, 광고 표기는 켬/끔 둘 다(기본 켬).** 처음 상태는 설정 `comment.disclose_default`(켬). 켜면 댓글은 `comment.disclosure`(`[광고]`)로 시작해야 하고, 끄면 규칙 검사 V4가 「표기 끔」으로 통과한다. 모든 영상에서 고를 수 있다(②칸 「광고 표기 붙이기」, 이유는 docs/INTENT.md). 댓글은 영상을 본 시청자가 장면 하나에 반응하고, 떠오른 내 연애 고민을 한마디 하고, 그 고민을 풀려고 운명원(연애 사주를 잘 보기로 유명한 곳)에 보러 가겠다고 다짐하며 무엇을 알고 싶은지 쓴다(기준: [`docs/COMMENT_REFACTOR.md`](docs/COMMENT_REFACTOR.md), 2026-11-18 대표 최종 지시서). 써 본 척하는 이용 후기·지어낸 애인 이야기·효능 단정·지어낸 평판은 만들지 않는다(규칙 검사 V8·V9·V10).
3. **API 키가 GitHub에 올라가면 안 된다.** 이 저장소는 공개(Public)다. API 키·토큰·브라우저 프로필 폴더를 코드·테스트 자료·로그·커밋에 넣지 않는다. `.env`를 읽어서 출력하지 않는다. 테스트용 가짜 키는 실행할 때 조립한다(`"AIza" + "x" * 35`). 자세한 규칙은 아래 "공개 저장소와 API 키" 절.
4. **기존 기능·테스트를 허락 없이 지우지 않는다.** `/`, `/api/health`, `tests/test_health.py` 포함. 실패하는 테스트를 지우거나 건너뛰게 바꿔 덮지 않는다.
5. **한 번에 한 단계.** 단계가 끝나면 `.\scripts\verify.ps1`이 통과해야 다음으로 간다. 다음 단계 모듈이나 빈 껍데기를 미리 만들지 않는다.
6. **나눠서 보고한다.** "구현함 / 자동 검증함 / 사람이 확인함 / 안 함"을 구분한다. 안 한 것을 했다고 쓰지 않는다.
7. **Git.** 단계가 끝나면 commit해도 된다. push·저장소 공개 설정 변경은 사용자가 요청할 때만. force push 금지. pre-commit 훅을 건너뛰지 않는다(`--no-verify` 금지).

## 공개 저장소와 API 키 (대표 지시, 2026-11-16)

이 저장소는 GitHub에 **공개**돼 있다. 한 번 올라간 키는 지워도 이미 복사됐다고 봐야 한다. **API 키가 GitHub에 직접 노출되는 일이 없어야 한다.**

- 진짜 키는 `.env`에만 둔다. 대표가 직접 입력한다. `.env`는 커밋하지 않는다(`.gitignore`와 커밋 훅이 막는다).
- 코드에는 키 값을 쓰지 않는다. `os.environ`·설정 모듈로 읽기만 한다. 기본값으로도 넣지 않는다.
- 키가 섞일 수 있는 곳을 모두 막는다: 소스, `config.yaml`, `.env.example`(이름만, 값은 비움), 테스트 자료와 저장해 둔 API 응답, 로그, 오류 문구, API 응답 본문, 화면, 문서·README, 커밋 메시지, 스크린샷, 시연 영상.
- YouTube 호출 주소의 `key=` 값은 로그·오류에 찍기 전에 가린다. `GET /api/status`는 키가 있는지 없는지만 알려 준다.
- 실제 API 응답을 테스트 자료로 저장할 때는 요청 주소와 머리말을 빼고 본문만 저장한다.
- **커밋 전**: 훅(`scripts/check_secrets.py --staged`)이 자동으로 돈다. `--no-verify`로 건너뛰지 않는다.
- **push 전**: `.\.venv\Scripts\python.exe scripts\check_secrets.py --all`을 돌려 통과를 확인하고, `git ls-files`에 `.env`·`*.db`·프로필 폴더가 없는지 본다. push는 사용자가 요청할 때만 한다.
- **키가 올라간 것을 발견하면**: 더 올리지 말고 바로 사용자에게 알린다. 먼저 할 일은 이력 정리가 아니라 **키 폐기와 재발급**이다(Google Cloud 콘솔). 이력 정리는 그다음에 사용자와 정한다.

## 창 규칙 (대표 공통 규칙)

- 시험·녹화·스크린샷용 창(Playwright·Chromium, 데스크톱 앱 창)은 **절대 주 모니터에 띄우지 않는다.**
- 브라우저 자동화는 기본 headless. 녹화도 창 없이.
- 창이 꼭 필요하면 위쪽 2번 모니터: Chromium 인수 `--window-position=60,-1060` (주 모니터 (0,0) 1920×1080, 위쪽 모니터 (0,-1080) 1920×1080). 배치가 바뀌었을 수 있으면 PowerShell `[System.Windows.Forms.Screen]::AllScreens`로 먼저 확인한다. (2026-11-16 확인: 2번 모니터가 왼쪽 `{X=-1920,Y=1}`에 있어 `-1860,60`을 썼다. 띄운 뒤 창 위치를 실제로 재서 2번 모니터 안인지 확인한다)
- 게시 작업·[로그인하기]·[유튜브 열기]의 크롬 창 위치는 2026-11-17부터 자동이다(`browser.window_screen: auto`, `app/browser/placement.py`): 프로그램 창이 없는 모니터, 하나뿐이면 그 왼쪽 60%. `browser.window_position`(좌표)은 기본값에서 뺐고 예전 판이 저장한 값만 그대로 읽는다. 자동 테스트는 `browser.headless: true`라 창을 띄우지 않는다. 확인용으로 창을 띄울 때는 먼저 `plan_window(read_monitors())`로 뜰 모니터를 계산해 주 모니터가 아닐 때만 띄운다.
- 서브에이전트나 다른 세션에 브라우저 일을 맡길 때도 이 조건을 지시에 넣는다.
- 서버 동작 확인은 가능하면 브라우저 대신 FastAPI `TestClient`로 한다.
- 프로그램 창(`app/desktop.py`)을 확인용으로 띄울 때는 환경 변수 `JG_DESKTOP_WINDOW_POS="x,y"`에 2번 모니터 좌표를 준다(비워 두면 주 모니터 가운데에 뜬다). 자동 테스트는 창을 띄우지 않는다.

## 자주 쓰는 명령 (PowerShell, 저장소 루트)

```powershell
py -3.12 -m venv .venv                                         # 처음 한 번
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks                            # 처음 한 번(비밀값 검사 훅)

.\JG-Marketing-Agent.cmd             # 프로그램 창으로 실행(더블클릭과 같음, app/desktop.py)
.\scripts\run.ps1                    # 개발용: 브라우저로 http://127.0.0.1:8765 (8단계부터 --reload 쓰지 않음)
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
- R5 로그인된 프로그램(Codex·Claude Code): `tests/conftest.py`가 `app.llm.cli`의 진짜 실행과 설치 찾기를 막는다(가짜 실행기를 넘겨 시험). 진짜 실행은 `tests/integration/test_live_cli.py`(live)만 — 대표의 구독 계정이라 짧은 시험 문장으로 프로그램당 1~2번만. 그 프로그램의 로그인 파일을 읽지 않는다. 다른 AI의 API 키도 키 값을 실행할 때 조립한다.
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
- 사용자에게 보이는 기능·API·UI·지원 환경·배포 방법·테스트 기준이 바뀌면 README(심사자용 3분 요약) 또는 사용자 문서도 실제 상태로 갱신한다. 단계별 변경 내용과 전체 API 표는 `docs/CHANGELOG.md`(예전 README)에 이어 적는다.
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
