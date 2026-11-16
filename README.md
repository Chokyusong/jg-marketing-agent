# JG 마케팅 에이전트

유튜브 영상을 분석해 홍보 표기(`[광고]`)가 붙은 댓글 초안을 만들고, 사람이 승인하는 로컬 대시보드(FastAPI). 제이지그룹 AI PM 채용 과제 TRACK 2 「마케팅 AI 에이전트 개발」.

## 지금 되는 것 / 아직 안 되는 것 (2026-11-16)

**되는 것**
- 1단계 뼈대: FastAPI 앱, 읽기 전용 3열 화면(`/`), 상태 확인 API(`/api/health`)
- 0단계 하네스: 작업 규칙(`AGENTS.md`), 검증 스크립트(`scripts/verify.ps1`), pytest 설정과 테스트 도우미, 비밀값 검사(`scripts/check_secrets.py` + pre-commit 훅), 설정 파일(`config.yaml`)

**아직 안 되는 것** (화면의 버튼은 동작하지 않는다)
- 유튜브 영상 불러오기·링크 입력 (2단계)
- 자막·맥락 수집, Ollama 연동, 고민 한 줄·댓글 초안 생성, 규칙 검사 (3~6단계)
- 영상당 1개·하루 상한·기록 (7단계)
- 브라우저 연결(sandbox 자동 게시, 실제 유튜브는 열기만) (8단계)
- `config.yaml`은 아직 앱이 읽지 않는다(2단계에서 연결)

## 과제 원문과 다르게 만드는 부분

원문은 시청자인 척하는 댓글을 실제 유튜브에 자동 게시하라고 요구한다. 이 프로젝트는

- 댓글 맨 앞에 `[광고]`를 붙여 홍보 계정임을 밝히고, 시청자를 사칭하지 않는다.
- 자동 타이핑·게시·확인은 이 앱이 주는 **통제된 테스트 페이지(sandbox)**에서만 한다. 실제 유튜브에서는 프로필과 영상을 열어 주고 **사람이 직접 게시**한다.

이유(표시광고법·공정위 추천·보증 심사지침, 유튜브 약관)와 점수 영향은 [docs/DESIGN.md 2절](docs/DESIGN.md#2-원문과-다르게-만드는-부분-의도적-변경)에 있다.

## 설치와 실행 (Windows 11, PowerShell)

필요: Python 3.12(`py -3.12`). Ollama·YouTube API 키는 해당 단계부터 필요하다.

```powershell
cd "E:\Projects\JG\JG-Marketing-Agent-Stage1"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks      # 커밋 전 비밀값 검사 훅
Copy-Item .env.example .env              # 비밀값은 .env에만 (커밋 금지)

.\scripts\run.ps1                        # http://127.0.0.1:8765
```

## 검증과 테스트

```powershell
.\scripts\verify.ps1                     # ruff check → pytest -q, 실패하면 0이 아닌 종료 코드
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest -m e2e      # Playwright 필요(8단계부터)
$env:RUN_LIVE='1'; .\.venv\Scripts\python.exe -m pytest -m live; Remove-Item Env:RUN_LIVE
.\.venv\Scripts\python.exe scripts\check_secrets.py --all
```

- 기본 테스트는 인터넷·API 키·Ollama 없이 돈다.
- `live`(진짜 YouTube·Ollama 호출)는 `RUN_LIVE=1`일 때만, `e2e`(창 없는 크롬)는 Playwright가 설치돼 있을 때만 돈다.

## 설정

| 파일 | 내용 | 커밋 |
|---|---|---|
| `config.yaml` | 프로필, 댓글 글자 수·브랜드·홍보 표기, 하루 상한 등 규칙 ([DESIGN 8절](docs/DESIGN.md#8-설정)) | 함 |
| `.env` | `YOUTUBE_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | 금지 |

## 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 뼈대 (GPT 초안) | 완료 |
| 0 | 하네스 | 완료 |
| 2 | YouTube API 연동, 화면 골격 | 미시작 |
| 3 | 영상 맥락 수집 | 미시작 |
| 4 | Ollama 연동, 모델 비교 | 미시작 |
| 5 | 분석과 초안 | 미시작 |
| 6 | 규칙 검사 | 미시작 |
| 7 | 운영 규칙과 기록 | 미시작 |
| 8 | 브라우저 연결 | 미시작 |
| 9 | 대시보드 완성 | 미시작 |
| 10 | 가점 | 미시작 |
| 11 | 시연 준비 | 미시작 |

자세한 할 일과 완료 기준: [docs/STAGES.md](docs/STAGES.md)

## 문서

- [AGENTS.md](AGENTS.md) — 작업 규칙(사람·AI 공통)
- [docs/DESIGN.md](docs/DESIGN.md) — 구조와 규칙의 기준
- [docs/STAGES.md](docs/STAGES.md) — 단계별 계획과 상태
- [docs/UI_SPEC.md](docs/UI_SPEC.md) — 화면 기준

## 보안

`.env`, API 키, 토큰, 브라우저 프로필 폴더, DB 파일, 과제 원문 PDF는 저장소에 넣지 않는다. pre-commit 훅이 커밋 전에 `scripts/check_secrets.py`로 검사한다.
