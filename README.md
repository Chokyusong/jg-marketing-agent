# JG 마케팅 에이전트

유튜브 영상을 분석해 홍보 표기(`[광고]`)가 붙은 댓글 초안을 만들고, 사람이 승인하는 로컬 대시보드(FastAPI). 제이지그룹 AI PM 채용 과제 TRACK 2 「마케팅 AI 에이전트 개발」.

## 지금 되는 것 / 아직 안 되는 것 (2026-11-16, 3단계 + P단계 + 6단계 + 4단계 + 5단계 + 7단계 + 8단계)

**되는 것**
- 프로그램으로 실행 (P단계): `JG-Marketing-Agent.cmd`를 더블클릭하면 브라우저 탭·주소창 없는 자체 창(「JG Marketing Agent」)이 뜬다. 창을 닫으면 프로그램이 끝난다. 이미 떠 있으면 새로 띄우지 않고 알린다. 창 안의 바깥 링크("YouTube에서 보기")는 기본 브라우저로 열린다
- 대시보드 화면(`/`): 디자인 기준([docs/UI_SPEC.md](docs/UI_SPEC.md), 검정·금색 에디토리얼 목업)대로 위 줄 메뉴·시스템 상태, 제목과 오늘 통계, 흐름 띠, 3열, 작업 기록, 좁은 화면 배치
- 01 영상 탐색 (2단계): [영상 찾기] 한 번으로 `config.yaml`의 기본 검색어(`discover.query`) 최신 영상 목록(썸네일·길이·제목·채널·조회수·올린 때). 검색어, 업로드 기간·정렬(최신·관련성·조회수)·표시 개수 거르기, 「쇼츠 제외」 체크(기본 켬 — 길이 61초 미만·길이 정보가 없는 영상을 빼고 표시 개수를 채운다. 결과 줄에 「쇼츠 n개 제외」. 검색 1회 100단위는 같다), URL 직접 입력, 영상 선택, 오류마다 문구와 다음 행동
- YouTube Data API 연동: 검색·영상 상세·인기 댓글, 오류 6종 분류(키 없음·키 거부·할당량 초과·댓글 막힘·영상 없음·네트워크), 같은 검색 10분 저장, 오늘 사용 단위 기록(SQLite `data/app.sqlite3`)
- 위 줄 시스템 상태: YouTube 키가 있는지 없는지(값은 보이지 않음). 01칸 아래에 오늘 할당량 사용량. 영상을 고르면 흐름 띠가 02로 넘어가고 02칸에 선택한 영상이 보인다
- 02 영상 자료 (3단계): 영상을 고르면 맥락을 모으고 「자막 출처」(붙여 넣은 자막 n자 / 자막 없음 · 제목과 설명으로 대신)와 「인기 댓글」(n개 / 댓글이 막힌 영상) 줄을 보인다. 「자막 붙여넣기」(접어 둠)에 유튜브 '스크립트 표시'에서 복사한 자막을 넣고 [저장]하면 출처가 바뀐다. 붙여 넣은 자막은 지울 수 있다. 자막은 수동 붙여넣기만 쓴다(비공식 조회는 만들지 않았다)
- 02 댓글 초안과 규칙 검사 (6단계): 영상을 고르면 「댓글 초안」 글 상자가 켜지고 `[광고] `가 미리 들어간다(표기는 금색). 사람이 직접 쓰고 입력을 0.4초 멈추면 V1~V12(길이 40~120자·한 줄, 링크, 해시태그, 표기 맨 앞, 브랜드 1~2번, 근거가 영상 자료에 있음, 글이 근거를 담음, 이용 후기 표현(써 본 척), 지어낸 연애 사연(내 애인 이야기), 효능·최상급, 이전 글과 유사, 한글·영문·숫자·기본 문장부호만 — 한자·일본어 글자·이모지가 있으면 걸린 글자를 알려 줌)을 검사해 글자 수와 결과를 보인다. 통과한 항목은 「12개 중 n개 통과」 한 줄로 접고, 걸린 항목만 무엇이 걸렸고 어떻게 고치면 되는지 펼친다. 모두 통과하면 이름표가 `DRAFT · REVIEW REQUIRED`에서 `CHECKED`로 바뀌고 흐름 띠가 03으로 넘어간다. 대조 자료는 3단계 맥락(제목·설명·붙여 넣은 자막·인기 댓글)이다
- 02 AI 분석과 초안 (5단계): 영상을 고르고 [분석하고 초안 만들기]를 누르면 「맥락 수집 → 분석 → 초안 → 검사」 진행과 걸린 초를 보이며(큰 모델은 처음에 1분쯤 걸린다) 주요 주제·핵심 고민·영상 톤·시청자 니즈·분석 근거(근거 문장과 출처: 자막·제목·설명·댓글) 다섯 줄과 AI 댓글 초안을 채운다. 영상을 고르기만 해서는 AI를 부르지 않는다(저장된 분석·초안이 있으면 불러온다). AI가 내놓은 근거 문장은 영상 자료에 실제로 있는지 V6과 같은 방법으로 대조해 없는 것은 버린다. 분석은 영상의 **연애 고민**을 찾는 것이 목적이라 설명란·댓글의 광고·협찬·상품 소개·이벤트 응모 글은 무시하고 근거로도 받지 않는다. 사연이 없는 연애 심리·강의·팁 영상도 시청자 입장의 연애 고민으로 정리한다(과제 예시와 같은 방식). 자료가 광고·협찬뿐이거나 연애와 관계없어 연애 고민을 찾지 못하면 초안을 만들지 않고 「이 영상 자료에서 연애 고민을 찾지 못했습니다」와 다음 행동(자막을 붙여 넣고 다시 분석하거나 다른 영상 고르기)을 띄우고 「자막 붙여넣기」를 연다. 초안은 운명원만 권하고 영상 자료에 나오는 다른 상품·브랜드 이름을 쓰지 않게 한다. 초안은 근거 문장 하나를 골라 AI가 본문만 쓰고 `[광고] `는 코드가 붙인다. 권하는 문장은 그 영상의 핵심 고민에 맞춰 쓰게 하고, 다른 영상에서 승인한 초안의 권유 문장은 되풀이하지 말라고 알려 준다. 규칙 검사에 걸리면 걸린 항목을 알려 주고 최대 3번 다시 쓰게 하며, 3번 모두 걸리면 가장 덜 걸린 초안을 남겨 사람이 고치게 한다. 초안은 글 상자에서 바로 고칠 수 있고(고친 글도 같은 검사), 말투 이름표(공감형·조언형·응원형·정보형)가 붙는다. [다른 초안 생성]은 이미 쓴 근거를 피해 새로 쓰고, [이 초안 승인]은 검사를 모두 통과한 초안만 승인한다(서버가 다시 검사하고 걸리면 거절). 승인하면 흐름 띠가 03으로 넘어간다. 「이전 글과 유사」(V11)는 다른 영상에서 승인한 초안과 비교한다
- 운영 규칙과 기록 (7단계): **영상당 댓글 1개·하루 상한(기본 10개)·기록**을 코드와 DB로 강제한다(`app/ops/`). 게시 자리는 `BEGIN IMMEDIATE` 거래 안에서 「오늘(한국 날짜) 예약+게시 수 세기 → 상한이면 거절 → 넣기」를 한 번에 하고, 같은 영상은 `posts`의 `UNIQUE(target, video_id)`가 막는다(버튼을 연달아 누르거나 두 요청이 동시에 와도 하나만 된다). 승인한 초안만 예약할 수 있다. 실패한 게시는 상한에 세지 않고 다시 시도할 수 있으며 기록에는 남는다. 테스트 페이지(sandbox)와 실제 유튜브(youtube)는 따로 센다. 분석·초안 생성·승인·게시는 지우지 않는 작업 기록(`runs`)에 시간순으로 남는다. 화면: 제목 영역 오늘 통계 4개(처리한 영상 n/상한 · 초안 · 게시 완료 · 성공률, 게시 시도가 없으면 `–`), 아래 작업 기록 표(시간·영상·작업·댓글·상태·프로필, 최근 5줄, 실패는 사유와 함께), 03칸 설정(사용 프로필 — 자동 배정은 가장 오래 안 쓴 프로필 / 작업 방식 — 수동 승인 후 게시(실제 유튜브, 사람이 게시)·테스트 페이지 자동 실행 / 일일 제한 — 설정값 이하로만 / 오늘 작업 n/상한), 01칸 목록의 「댓글 단 영상」 표시
- 브라우저 연결 (8단계): 03칸 큰 버튼 [브라우저에서 영상 열기]가 실제로 동작한다. 승인한 초안이 있고, 그 대상에서 댓글을 안 단 영상이고, 오늘 남은 횟수가 있을 때만 켜진다. 한 번에 작업 하나(`app/browser/jobs.py` 작업 서비스), 진행 단계 6개(대기 → 프로필 실행 → 댓글 입력 → 승인 대기 → 게시 완료 → 확인)를 0.5초마다 다시 그린다. 작업이 끝나면 오늘 통계·작업 기록·01칸 「댓글 단 영상」을 바로 고친다. 위 줄 BROWSER는 실제 상태(크롬 · 프로필 n/3 / 크롬 · 작업 중 / 크롬 없음)
  - **테스트 페이지 자동 실행(sandbox)**: 이 앱 안의 통제된 테스트 페이지(`/sandbox/watch`, 맨 위에 「통제된 테스트 페이지 — 실제 유튜브가 아닙니다」)를 설치된 Google Chrome으로 연다(Playwright, 브라우저를 내려받지 않음). 프로필 폴더로 크롬을 열고 → 승인한 초안을 한 글자씩(글자마다 60~160밀리초 무작위) 입력하고 → **사람이 [게시 승인]을 누를 때까지 기다린다**(5분 넘으면 「승인 시간 초과」로 실패) → 「댓글」을 누르고 → 페이지에 내 댓글이 보이는지 확인한다. 실패하면 사유와 화면 캡처(`error_screenshots/<작업 ID>.png`)가 남고 작업 기록에서 볼 수 있다. 일부러 실패를 내는 스위치 `fail=hide_button|slow|reject`
  - **수동 승인 후 게시(실제 유튜브, assist)**: 크롬을 그 프로필과 영상 주소로 **열기만** 한다(명령 인자 목록, 셸 없음). 대시보드에 [초안 복사]·[게시했어요]·[게시 안 함]이 뜨고, 붙여넣기와 게시는 사람이 직접 한다. [게시했어요]를 누르면 YouTube 키가 있을 때만 Data API로 댓글을 찾아보고, 못 찾거나 키가 없으면 「게시됨(확인 못 함)」으로 남긴다. 10분 안에 답이 없으면 「확인 시간 초과」. **실제 유튜브 화면의 요소를 찾거나 누르거나 입력하는 코드는 없다**(테스트가 확인한다)
  - 프로필 폴더는 저장소 밖 `%LOCALAPPDATA%\JGMarketingAgent\profiles\profile-N`. 그 프로필의 크롬 창이 이미 열려 있으면 「그 프로필의 크롬 창을 닫아 주세요」. 실제 유튜브에 로그인해 두는 준비는 `.\scripts\setup_profile.ps1 -Profile 1`(크롬이 그 프로필로 Google 로그인 화면을 연다. 로그인은 사람이 직접)
  - 프로그램 창을 닫으면 진행 중인 작업을 취소하고 자동 실행 크롬을 닫는다
  - 창 위치 기본값 `60,-1060`은 "주 모니터 위쪽에 2번 모니터"를 전제로 한다. 모니터 배치가 다르면 `config.yaml`의 `browser.window_position`을 고친다(2026-11-16 이 PC는 2번 모니터가 왼쪽 X=-1920이라 확인 실행 때 `-1860,60`을 썼다)
- AI 연결 (4단계): 로컬 Ollama에 「이 모양의 JSON으로 답해라」를 시키고 받는 통로(`app/llm/`). 위 줄 AI 상태가 실제 값을 보인다 — 정상이면 「ollama · 모델 이름 · 로컬」(연두), Ollama가 꺼져 있으면 「ollama · 꺼짐」, 모델이 없으면 「모델 이름 · 모델 없음」(붉은 점, 마우스를 올리면 할 일). 30초마다 다시 확인한다. 생각 출력 기능이 있는 모델(qwen3.x)은 생각을 끄고 부른다. 답이 JSON이 아니거나 모양이 틀리면 한 번 다시 시킨다. LLM은 설정(`llm.active`)으로 고르는 틀이라 나중에 다른 공급자(OpenAI 호환·Claude·로그인된 CLI, 12단계)를 끼울 수 있다. 지금 구현한 공급자는 Ollama 하나다. 설치된 모델 시험과 5단계 초안 비교 결과: [docs/MODEL_EVAL.md](docs/MODEL_EVAL.md)
- 설정: `config.yaml`(규칙)과 `.env`(비밀값)를 앱이 읽는다. 키가 없어도 화면은 뜨고 불러오기 때 안내가 나온다
- 0단계 하네스: 작업 규칙(`AGENTS.md`), 검증 스크립트(`scripts/verify.ps1`), pytest 설정과 테스트 도우미, 비밀값 검사(`scripts/check_secrets.py` + pre-commit 훅)

**아직 안 되는 것**
- 모델 미리 불러 두기 버튼(9단계, API는 있다)
- 실제 데이터 보정(연애 고민 없으면 멈춤·쇼츠 제외, 2026-11-17)은 코드·자동 테스트와 실제 키 검색 1회까지 했다. 보정 뒤 실제 모델(qwen3.8:27b)로 다시 재는 일은 이 PC의 메모리가 모자라(다른 프로그램이 그래픽 메모리·메모리를 차지) 아직 못 했다 — [docs/MODEL_EVAL.md](docs/MODEL_EVAL.md) 「실제 데이터 보정」
- 실제 유튜브 자동 게시는 만들지 않는다(정책). 실제 유튜브는 크롬으로 열기만 하고 사람이 게시한다. 공식 API로 댓글을 다는 기능도 만들지 않았다
- 작업 기록 전체 보기(VIEW ALL)와 SETTINGS 패널(9단계)
- 실제 YouTube 키로 한 번 불러 보는 확인(`live` 테스트)은 아직 하지 않았다. 3단계 02칸 화면, 6단계 초안 글 상자, 5단계 AI 분석·초안 화면, 7단계 통계·작업 기록·03칸 설정, 8단계 03칸 작업 화면도 대표 확인 전이다. 8단계 창이 보이는 실행(2번 모니터)은 개발 PC에서 한 번 해 봤고, 실제 유튜브 열기(assist)는 아직 사람이 해 보지 않았다
- 프로그램 창은 개발 PC에서 띄우고 닫아 봤다. 대표가 직접 더블클릭해 보는 확인은 아직이다
- 실행 파일 한 개(`.exe`)로 묶기는 11단계다. 지금은 Python 가상환경(`.venv`)을 한 번 준비해야 한다

## 과제 원문과 다르게 만드는 부분

원문은 시청자인 척하는 댓글을 실제 유튜브에 자동 게시하라고 요구한다. 이 프로젝트는

- 댓글 맨 앞에 `[광고]`를 붙여 홍보 계정임을 밝히고, 시청자를 사칭하지 않는다.
- 자동 타이핑·게시·확인은 이 앱이 주는 **통제된 테스트 페이지(sandbox)**에서만 한다. 실제 유튜브에서는 프로필과 영상을 열어 주고 **사람이 직접 게시**한다.

이유(표시광고법·공정위 추천·보증 심사지침, 유튜브 약관)와 점수 영향은 [docs/DESIGN.md 2절](docs/DESIGN.md#2-원문과-다르게-만드는-부분-의도적-변경)에 있다.

## 설치와 실행 (Windows 11)

필요: Python 3.12(`py -3.12`), Microsoft Edge WebView2 Runtime(Windows 11에는 기본으로 들어 있다). YouTube API 키(2단계부터), [Ollama](https://ollama.com)와 모델 하나(4단계부터). 기본은 `qwen3.8:27b`(5단계 초안 비교에서 규칙 통과율이 가장 높았다, [docs/MODEL_EVAL.md](docs/MODEL_EVAL.md)). 다른 모델을 쓰려면 `ollama pull <모델>` 후 이름을 `.env`의 `OLLAMA_MODEL`에.

**처음 한 번 준비** (PowerShell, 저장소 폴더)

```powershell
cd "E:\Projects\JG\JG-Marketing-Agent-Stage1"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt     # 개발까지 하려면 requirements-dev.txt
Copy-Item .env.example .env              # 비밀값은 .env에만 (커밋 금지)
```

### 1. 더블클릭으로 프로그램 실행 (평소)

저장소 폴더의 **`JG-Marketing-Agent.cmd`**를 더블클릭한다.

- 자체 창이 화면 가운데에 뜬다(기본 1600×1000, 최소 1100×720). 브라우저 탭·주소창이 없다.
- 창을 닫으면 안쪽 서버도 멈추고 프로그램이 끝난다.
- 이미 떠 있을 때 다시 더블클릭하면 새로 띄우지 않고 "이미 실행 중"이라고 알린 뒤 떠 있는 창을 앞으로 가져온다.
- `.venv`가 없으면 위 준비 방법을 안내하고 멈춘다. WebView2 런타임이나 pywebview가 없으면 설치 방법을 알린다.
- 콘솔 없이 돈다(`.cmd`를 여는 순간 콘솔 창이 잠깐 보였다가 닫힐 수 있다). 서버 기록은 `data/desktop.log`에 남는다(커밋하지 않는 폴더).
- 안쪽 동작: 한 프로세스에서 FastAPI 서버를 스레드로 띄우고(127.0.0.1의 빈 포트), pywebview 창이 그 화면을 담는다(`app/desktop.py`). 명령으로 띄우려면 `.\.venv\Scripts\pythonw.exe -m app.desktop`.

### 2. 개발용: 브라우저로 실행

```powershell
git config core.hooksPath .githooks      # 커밋 전 비밀값 검사 훅 (처음 한 번)
.\scripts\run.ps1                        # http://127.0.0.1:8765 를 브라우저로 연다
```

8단계부터 `--reload`를 붙이지 않는다. 파일이 바뀔 때 서버가 다시 시작되면 진행 중인 크롬 작업(전용 스레드)이 정리되지 않고 남을 수 있다.

## 검증과 테스트

```powershell
.\scripts\verify.ps1                     # ruff check → pytest -q, 실패하면 0이 아닌 종료 코드
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m pytest -m e2e      # 창 없는 크롬으로 테스트 페이지 전 과정(8단계)
$env:RUN_LIVE='1'; .\.venv\Scripts\python.exe -m pytest -m live; Remove-Item Env:RUN_LIVE
.\.venv\Scripts\python.exe scripts\check_secrets.py --all
.\.venv\Scripts\python.exe scripts\ollama_smoke.py           # 설치된 일반 모델마다 한국어 JSON 한 번(시간·성공 표)
```

- 기본 테스트는 인터넷·API 키·Ollama 없이 돈다.
- `live`(진짜 YouTube·Ollama 호출)는 `RUN_LIVE=1`일 때만 돈다.
- `e2e`는 임시 포트로 앱 서버를 띄우고, 설치된 Google Chrome을 창 없이(headless) 임시 프로필로 열어 테스트 페이지 전 과정(한 글자씩 입력·승인 전에는 안 달림·실패 캡처·두 번째 거절·하루 상한·프로필 사용 중)을 돈다. Playwright나 크롬이 없으면 건너뛴다. `verify.ps1`의 `pytest -q`에 들어 있다.

## API

| 주소 | 내용 |
|---|---|
| `GET /api/health` | 서버 확인 (1단계부터 그대로) |
| `GET /api/status` | 시스템 상태: `youtube`(키가 있는지 `key_configured`와 오늘 할당량, 키 값은 싣지 않는다), `ai`(`provider`·`model`·`reachable` 서버에 닿는지·`installed` 모델이 있는지·`local` 이 PC 안인지, 문제가 있으면 `error{kind, message, action}`), `browser`(8단계: `chrome_found`·`playwright_ready`·`profiles[{name, folder, exists}]`·`active_job_id`, PC의 폴더 경로는 싣지 않는다) |
| `POST /api/llm/warmup` | 고른 모델을 미리 불러 둔다(`keep_alive` 동안 메모리에 머문다). 응답 `provider`·`model`·`seconds`. 큰 모델은 몇 분 걸릴 수 있다 |
| `GET /api/videos` | 최신 영상 목록. 입력 없이 부르면 기본 검색어. 선택 입력 `q`, `period`(day·week·month·any, 기본 week), `order`(date·relevance·viewCount), `max_results`(1~50), `exclude_shorts`(비우면 `config.yaml`의 `discover.exclude_shorts` = 기본 참: 50개를 받아 길이 61초 미만·길이 없음을 빼고 원래 순서대로 `max_results`개). 응답에 `exclude_shorts`·`shorts_excluded`(뺀 수)가 붙는다(기존 필드는 그대로). 같은 검색 10분 저장의 키에 `exclude_shorts`도 든다 |
| `POST /api/videos/resolve` | `{"url": "..."}` 유튜브 링크 → 영상 한 개 |
| `GET /api/videos/{video_id}` | 영상 상세(10분 안이면 저장된 값) |
| `POST /api/videos/{video_id}/context` | 영상 맥락을 만들고 요약을 돌려준다: 본문 출처(`transcript`·`title_description`), 자막 출처(`manual`·`none`), 자막 글자 수, 인기 댓글 수, 댓글 막힘 여부, 모델 입력 한도에 맞추느라 줄였는지. 저장된 인기 댓글이 있으면 다시 부르지 않는다(`?refresh=true`면 새로, 1단위) |
| `PUT /api/videos/{video_id}/transcript` | `{"text": "..."}` 붙여 넣은 자막 저장(공백 정리, 최대 20,000자) 후 같은 요약 |
| `DELETE /api/videos/{video_id}/transcript` | 붙여 넣은 자막 지우기 후 같은 요약 |
| `POST /api/validate` | `{"video_id": "...", "text": "..."}` 글 하나를 규칙 V1~V12로 검사한다. 응답: `passed`, `char_count`(표기 포함, NFC 코드 포인트), `min_chars`·`max_chars`, `evidence_quote`(영상 자료와 겹치는 가장 긴 구절), `passed_count`·`total`, `checks`(항목마다 `code`·`name`·`passed`·`message`). 맥락이 없으면 만들어서 쓰고(인기 댓글 1단위), 있으면 YouTube를 다시 부르지 않는다. 글은 2,000자까지 받는다. V11은 다른 영상에서 승인한 초안과 비교한다 |
| `POST /api/analysis/{video_id}` | 영상 맥락을 AI로 분석해 저장하고 돌려준다: `topic`·`concern`·`tone`·`viewer_needs`, `evidence`(근거 문장 `quote`·출처 `source`·`source_label`, 자료에 있는 것만 최대 4개), `dropped_count`(자료에 없거나 광고·협찬·응모 글이라 버린 근거 수), `fallback`(예전 필드, 이제 늘 `false`), `model`, `has_love_concern`(늘 `true`)·`love_reason`(모델이 적은 판단 까닭). 연애 고민을 찾지 못하면 422 `no_love_concern`(초안을 만들지 않는다) |
| `GET /api/analysis/{video_id}` | 저장된 분석(없으면 `null`). AI를 부르지 않는다 |
| `POST /api/drafts` | `{"video_id", "another": false, "avoid_quotes": []}` AI 초안을 만든다(분석이 없으면 먼저 분석). 검사에 걸리면 걸린 항목을 넣어 최대 3번, 다 걸리면 가장 덜 걸린 것을 저장. `another: true`면 이 영상에서 쓴 근거를 피한다. 응답: `id`·`body`(`[광고] ` 포함)·`evidence_quote`·`evidence_source`·`evidence_label`·`tone_label`·`attempts`·`first_passed`·`passed`·`status`(draft·approved·superseded)·`edited_by_human`·`validation`(`POST /api/validate`와 같은 모양) |
| `GET /api/drafts?video_id=` | 초안 목록(새것부터) |
| `PATCH /api/drafts/{id}` | `{"body": "..."}` 사람이 고친 글 저장 후 다시 검사. 승인한 글을 고치면 승인이 풀린다 |
| `POST /api/drafts/{id}/approve` | 다시 검사해 모두 통과하면 승인(같은 영상의 다른 초안은 superseded). 걸리면 409 `draft_not_passed`와 `failures`(걸린 항목마다 `code`·`name`·`message`) |
| `GET /api/profiles?target=` | 프로필 목록(`name` 유튜브1 ↔ `folder` profile-1, `last_used_at`)과 `auto`(자동 배정이 지금 고를 프로필 = 그 대상에서 가장 오래 안 쓴 것). `target`은 sandbox(기본)·youtube. PC의 전체 폴더 경로는 싣지 않는다 |
| `GET /api/records?limit=` | 작업 기록(최신이 위, `limit` 1~200, 기본 20)과 `total`. 줄마다 `at`·`action`(analyze·draft·approve·post)·`action_label`·`video_id`·`video_title`·`video_url`·`profile`·`comment_text`·`target`·`result`(success·failure·info)·`status_label`·`reason`·`has_screenshot` |
| `GET /api/stats/today?target=&daily_limit=` | 오늘(한국 날짜) 통계: `videos`(예약+게시, 상한에 세는 수)·`daily_limit`·`remaining`·`drafts`·`posted`·`failed`·`success_rate`(0~1, 게시 시도가 없으면 `null`). `daily_limit`으로 상한을 낮춰 볼 수 있다(설정값보다 높일 수 없다) |

| `POST /api/jobs` | 8단계 게시 작업 시작 `{"video_id", "draft_id", "profile"(비면 자동 배정), "target": "sandbox"·"assist", "daily_limit", "fail"(sandbox 시험용)}`. 한 번에 하나(진행 중이면 409 `job_busy`), 이미 단 영상·상한·승인 안 된 초안은 시작 전에 거절 |
| `GET /api/jobs/{id}` | 작업 상태: `state`·`state_label`·`step`(0~6)·`waiting_for`(approve·confirm)·`seconds_left`·`message`·`reason`·`verified`·`has_screenshot`·`screenshot_url`·`view_url`·`events`(상태가 바뀔 때마다 한 줄, `job_events` 표에도 남음) |
| `POST /api/jobs/{id}/approve` | sandbox: 입력을 마친 뒤 사람이 게시를 승인(그 전에는 「댓글」을 누르지 않는다) |
| `POST /api/jobs/{id}/confirm` | assist: `{"posted": true}` 게시했어요 / `false` 게시 안 함 |
| `POST /api/jobs/{id}/cancel` | 작업 취소(크롬을 닫고 예약을 실패로 푼다) |
| `GET /api/jobs/{id}/screenshot` | 실패 화면 캡처(PNG) |
| `GET /sandbox/watch?v=&profile=&fail=` | 통제된 테스트 페이지(실제 유튜브가 아님). `GET`·`POST /sandbox/api/comments`가 `sandbox_comments` 표에 댓글을 저장한다 |

영상 목록·영상 항목 응답(`GET /api/videos`, `POST /api/videos/resolve`, `GET /api/videos/{id}`)의 영상마다 `commented: {sandbox, youtube}`(그 대상에 게시 완료했는지)가 붙는다(7단계, 기존 필드는 그대로).

오류는 `{"error": {"kind", "message", "action"}}` 모양이다. AI 오류 종류: `llm_down`(Ollama 꺼짐 → `ollama serve`), `llm_model_missing`(→ `ollama pull <모델>`), `llm_timeout`, `llm_bad_output`(한 번 다시 시켜도 JSON이 아님), `llm_error`, `llm_provider_unknown`(`llm.active`가 없거나 아직 지원하지 않는 종류). 분석 오류: `no_love_concern`(422, 영상 자료에서 연애 고민을 찾지 못함 — 자막을 붙여 넣고 다시 분석하거나 다른 영상을 고른다. `detail`에 모델이 적은 까닭). 초안 오류: `draft_not_found`(404), `draft_not_passed`(409, 검사에 걸려 승인 불가), `draft_superseded`(409, 새 초안이나 승인으로 밀려난 초안). 운영 규칙 오류(7단계, 8단계 게시 실행에서 보인다): `already_commented`(409, 이미 댓글을 단 영상), `daily_limit_reached`(429, 오늘 상한 — 한국 자정에 풀림), `draft_not_approved`(409, 승인하지 않은 초안), `profile_unknown`(422). 작업 오류(8단계): `job_busy`(409), `job_not_found`(404), `job_wrong_state`(409), `chrome_not_found`(503), `playwright_missing`(503), `profile_in_use`(409, 그 프로필의 크롬 창을 닫아 주세요), `screenshot_not_found`(404). 검색은 100단위, 상세·댓글은 1단위를 쓴다(하루 10,000단위). 댓글이 막힌 영상은 오류가 아니라 빈 목록으로 진행한다.

## 설정

| 파일 | 내용 | 커밋 |
|---|---|---|
| `config.yaml` | 프로필(`profiles`, 순서대로 폴더 profile-1…), 기본 작업 방식(`browser.default_target`: sandbox → 테스트 페이지 자동 실행, assist → 수동 승인 후 게시), 브라우저(`browser.headless` 기본 false — 테스트는 true, `browser.window_position` 기본 `60,-1060`, `browser.typing_delay_ms` 기본 `[60, 160]`, `browser.chrome_path` 비면 자동으로 찾음. 프로필 폴더는 환경 변수 `JG_PROFILES_DIR`로 바꿀 수 있음), 댓글 글자 수·브랜드·홍보 표기, 하루 상한, 자막 출처(`transcript.provider: manual`), 모델에 넣을 영상 자료 길이(`llm.context_chars`, 기본 6,000자), 운명원에 대해 쓸 수 있는 사실 문장(`brand.facts`, 기본 「운명원은 연애 사주 상담을 하는 곳이다」 한 줄), 규칙 검사에 더할 표현(`validator.extra_patterns`, 항목 모양 `{code: V8·V9·V10, pattern: 정규식}`, 기본 빈 목록), AI 설정(`llm.active`: `llm.providers`에서 고른 이름, 기본 `ollama` · `timeout_seconds` 180 · `num_ctx` 8192 · `keep_alive` 30m. 옛 키 `llm.provider`도 읽는다. 공급자 항목의 `api_key_env`에는 환경 변수 **이름**만 적고, 그 이름은 자동으로 비밀값·로그 가리기 대상이 된다) 등 규칙 ([DESIGN 8절](docs/DESIGN.md#8-설정)) | 함 |
| `.env` | `YOUTUBE_API_KEY`(2단계부터 사용), `OLLAMA_BASE_URL`(기본 `http://127.0.0.1:11434`), `OLLAMA_MODEL`(기본 `qwen3.8:27b` — 5단계 비교로 정함. 초안을 읽어 보고 바꿔도 된다). 선택: `APP_DB_PATH`(기본 `data/app.sqlite3`) | 금지 |

## 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 뼈대 (GPT 초안) | 완료 |
| 0 | 하네스 | 완료 |
| 2 | YouTube API 연동, 화면 골격 | 진행 중 (코드·자동 테스트 완료, 실제 키 확인·화면 확인 남음) |
| 3 | 영상 맥락 수집 | 진행 중 (코드·자동 테스트 완료, 화면 확인 남음) |
| P | 프로그램으로 실행 (자체 창) | 진행 중 (코드·자동 테스트·개발 PC 창 확인 완료, 대표 더블클릭 확인 남음) |
| 4 | Ollama 연동 (초안 품질 비교는 5단계) | 진행 중 (코드·자동 테스트·실제 모델 시험 완료, Ollama를 끄고 켜며 위 줄 AI 상태를 보는 화면 확인 남음) |
| 5 | 분석과 초안, 모델 비교 | 진행 중 (코드·자동 테스트·실제 모델 비교 완료, 화면 확인과 대표의 초안 읽기 남음) |
| 6 | 규칙 검사 | 진행 중 (코드·자동 테스트 완료, 화면 확인 남음. 실행 순서상 4·5단계보다 먼저 했다) |
| 7 | 운영 규칙과 기록 | 진행 중 (코드·자동 테스트 완료, 승인하면 기록 줄과 통계가 바뀌는지 보는 화면 확인 남음) |
| 8 | 브라우저 연결 | 진행 중 (코드·자동 테스트·e2e·2번 모니터 창 실행 1회 완료, 대표 화면 확인과 실제 유튜브 열기(assist) 확인 남음) |
| 9 | 대시보드 완성 | 미시작 |
| 10 | 가점 | 미시작 |
| 11 | 시연 준비 | 미시작 |

자세한 할 일과 완료 기준: [docs/STAGES.md](docs/STAGES.md)

## 문서

- [AGENTS.md](AGENTS.md) — 작업 규칙(사람·AI 공통)
- [docs/DESIGN.md](docs/DESIGN.md) — 구조와 규칙의 기준
- [docs/PLAYBOOK.md](docs/PLAYBOOK.md) — 완성까지의 단계별 실행 계획(순서, 파일, API, 테스트)
- [docs/STAGES.md](docs/STAGES.md) — 단계별 상태와 완료 기준
- [docs/UI_SPEC.md](docs/UI_SPEC.md) — 화면 기준

## 오픈소스 출처

- **Noto Serif KR** (제목 글꼴) — (c) 2017-2024 Adobe, Google. [SIL Open Font License 1.1](app/static/fonts/OFL.txt). 굵기 400과 필요한 글자만 남긴 파일을 `app/static/fonts/`에 넣었다. 원본과 만든 방법: [app/static/fonts/README.md](app/static/fonts/README.md)
- **pywebview** (자체 창, P단계) — [BSD 3-Clause License](https://github.com/r0x0r/pywebview/blob/master/LICENSE). Windows에서는 Microsoft Edge WebView2 Runtime으로 화면을 그린다. 함께 설치되는 pythonnet(MIT)·bottle(MIT)·proxy_tools(MIT)·clr_loader(MIT)도 쓴다. 이름·설치 방법·지원 환경·라이선스는 2026-11-16에 [PyPI](https://pypi.org/project/pywebview/)와 [공식 문서](https://pywebview.flowrl.com/guide/installation.html)로 확인했다(자세한 내용은 `app/desktop.py` 맨 위).
- **Playwright for Python** (테스트 페이지 자동 실행, 8단계) — [Apache License 2.0](https://github.com/microsoft/playwright-python/blob/main/LICENSE), Microsoft. 설치된 Google Chrome을 `channel="chrome"`으로 쓰고 브라우저는 내려받지 않는다. 동기 API를 전용 스레드 하나에서만 쓴다. 사용법은 2026-11-16에 공식 문서([BrowserType](https://playwright.dev/python/docs/api/class-browsertype) `launch_persistent_context`, [Library](https://playwright.dev/python/docs/library) 스레드 주의, [Browsers](https://playwright.dev/python/docs/browsers) `channel`)로 확인했다(playwright 1.65.2, 자세한 내용은 `app/browser/sandbox_driver.py` 맨 위). 이 앱의 `/sandbox/` 주소만 연다.
- 파이썬 패키지는 `requirements.txt`, `requirements-dev.txt`에 적힌 것을 쓴다(FastAPI, Uvicorn, Jinja2, httpx, python-dotenv, PyYAML, pywebview, Playwright, pytest, ruff).

## 보안

`.env`, API 키, 토큰, 브라우저 프로필 폴더, DB 파일, 과제 원문 PDF는 저장소에 넣지 않는다. pre-commit 훅이 커밋 전에 `scripts/check_secrets.py`로 검사한다.
