# 설계 문서 — JG 마케팅 에이전트

- 작성: 2026-11-16 (초기 설계·기획 단계)
- 대상: 제이지그룹 AI PM 과제 TRACK 2 「마케팅 AI 에이전트 개발」
- 이 문서가 구조와 규칙의 기준이다. 단계별 할 일과 완료 기준은 [STAGES.md](STAGES.md)에 있다.
- 과제 원문 PDF는 저장소에 넣지 않는다(회사 자료). 요구사항은 아래 1절에 옮겨 적었다.

## 1. 과제 원문 요구사항 (요약)

**미션.** 지정된 영상의 내용과 맥락에 맞는 댓글을 달고, 읽은 사람이 '운명원'에서 연애 사주를 보고 싶게 한다.

**형태.** 지원자 PC에서 실행하는 대시보드. 화면은 세 칸. 원문: "웹에 올린 페이지는 크롬 프로필을 열 수 없으므로, 프로그램은 내 컴퓨터에서 실행하는 방식으로 만들어 주세요." → 이 프로젝트는 더블클릭으로 뜨는 자체 창 프로그램으로 만든다(PLAYBOOK P단계). 안쪽은 로컬 FastAPI 서버와 웹 화면이다.

| 칸 | 원문 요구 |
|---|---|
| ① 영상 불러오기 | 버튼 한 번에 최신 영상이 썸네일·제목·채널·올린 날짜로 뜬다 |
| ② 영상 선택 | 목록에서 고르면 "영상 속 고민 한 줄"과 "댓글 초안"이 보인다. (가점: 링크 직접 입력) |
| ③ 댓글 달기 | 크롬 프로필이 열리고 댓글 창 → 한 글자씩 타이핑 → 게시 → 내 댓글 확인. 진행 상태 표시, 실패 시 이유와 화면 캡처 |

**댓글 조건.** AI가 자막(없으면 제목·설명)과 인기 댓글을 읽고 연애 고민을 먼저 정리한다. 40~120자, 영상 속 구체적 장면이나 말을 하나 이상 언급, 영상마다 다르게. 금지: 링크, 해시태그, 운명원을 직접 이용한 것처럼 지어낸 후기.

**운영 규칙(코드에서 강제).** 영상당 댓글 1개, 하루 게시 상한(기본 10개), 기록(어느 영상·어느 프로필·무슨 댓글·성공/실패, 시간순).

**설정 예시.**

```yaml
profiles: [유튜브1, 유튜브2, 유튜브3]
comment: { min_chars: 40, max_chars: 120, brand: 운명원 }
limits:  { daily_max_comments: 10 }
```

**가점.** 프로필 3개 선택 또는 자동 배정 · 링크 직접 입력 · 새 영상 초안 즉석 생성 · '연애' 키워드로 뜨기 직전 영상 찾기(조회수 1,000~5,000, 시간당 150 이상, 초안까지만).

**평가(100점).** 실제 게시 25 · 맥락 이해 25 · 운명원 유도 20 · 운영 규칙 15 · 사용성 10 · 제작 의도 5.

**제출.** 시연 영상 2~3분(필수), Git 저장소 Public(선택), 제작 의도.

## 2. 원문대로 하는 것과 더한 것 (R3, 2026-11-17 고침)

처음 설계(2026-11-16)는 실제 유튜브 자동 게시를 테스트 페이지와 내 채널 영상으로 좁혔다. 대표 지시(프로그램화 2차 R3)로 **과제 원문의 흐름대로** 되돌렸다: 어떤 영상이든 ③ [댓글 달기]를 누르면 고른 프로필의 크롬이 열려 한 글자씩 입력하고 게시하고 내 댓글을 확인한다.

**원문대로 하는 것.**

| 원문 | 이 프로젝트 |
|---|---|
| ③ [댓글 달기] → 프로필이 열리고 → 댓글 창 → 한 글자씩 타이핑 → 게시 → 내 댓글 확인 | 그대로(`app/browser/youtube_driver.py`). 어떤 영상이든. [댓글 달기] 한 번으로 끝까지 |
| 진행 상태 표시, 실패 시 이유와 화면 캡처 | 프로필 여는 중 → 입력 중 → 게시 완료 · [댓글 보기]. 실패하면 이유(못 찾은 화면 요소 이름까지) · [화면 캡처 보기] · [다시 시도] |
| 시청자 말투로 운명원을 떠올리게 | 시청자 말투, 이용 의향("저도 한번 보고 싶어요")까지 |
| 프로필 3개 선택·자동 배정, 영상당 1개, 하루 상한, 시간순 기록 | 그대로. 코드와 DB가 강제한다 |
| 세 칸 화면, 맥락 분석, 40~120자, 장면·말 언급, 영상마다 다른 초안, 링크·해시태그·지어낸 후기 금지, 가점 4종 | 그대로 |

**원문에 더한 것.**

| 더한 것 | 이유 |
|---|---|
| **광고 표기 켬/끔**(②칸 「광고 표기 붙이기」, 처음 상태는 설정 「광고 표기 기본값」 = 켬). 켜면 `[광고] `로 시작해야 규칙 검사(V4)를 통과하고, 끄면 V4는 「표기 끔」으로 통과한다. 글자 수는 어느 쪽이든 전체 글로 센다. 작업 기록에 표기를 붙였는지 남긴다 | 광고주가 게시 계정을 운영하면 표시광고법·공정위 「추천·보증 등에 관한 표시·광고 심사지침」상 표기가 필요하다. 그렇지 않은 경우(채널 주인이 자기 영상에, 광고와 관계없는 운영자가)는 운영자가 고른다. 그래서 둘 다 지원하고 기본은 켬(INTENT.md) |
| **사람이 검토하고 누른 댓글만** 게시한다. 규칙 검사(V1~V12)를 통과한 초안이어야 [댓글 달기]가 눌리고, 누르는 순간 그 초안을 승인 처리한다. 서버는 승인한 초안만 받는다 | 지어낸 후기·효능 단정·링크가 사람 눈과 규칙 검사를 거치지 않고 나가지 않게 |
| **게시 직전 확인**(설정, 기본 끔). 켜면 입력 뒤 [게시]를 한 번 더 눌러야 한다 | 조심해서 쓰고 싶은 사람용 |
| **시작 전 확인**: 한 번에 작업 하나, 댓글이 막힌 영상, 프로필 로그인(최근 확인에서 로그인 안 됨이면 「프로필 화면에서 [로그인하기]」), 그 프로필 창이 열려 있지 않은지, 영상당 1개, 오늘 상한 | 실패할 일을 크롬을 열기 전에 막고, 무엇을 하면 되는지 쉬운 말로 알린다 |
| 실행기는 **이번 작업의 영상 주소 하나만** 열고, 페이지가 그 영상·동의·로그인 화면 밖으로 옮겨 가면 멈춘다 | 다른 영상·다른 사이트를 건드리지 않게 |
| 「댓글」을 누른 뒤 확인을 못 하면 실패가 아니라 「게시됨(확인 못 함)」 | 다시 시도해 같은 댓글이 두 번 달리지 않게 |
| **연습 모드**(③ 스위치, 기본 끔): 프로그램 안의 연습 페이지(`/sandbox/watch`)에 같은 흐름으로 단다 | 로그인·키 없이 시연·시험 |

**남는 위험.** 유튜브 약관은 자동화 수단으로 서비스를 조작하는 것을 금지하고, 스팸·기만 행위 정책 위반으로 계정이 제한될 수 있다. 같은 홍보 댓글을 남의 영상에 반복해 달면 스팸으로 처리되거나 채널 주인이 지울 수 있다. 실제 운영은 소량(하루 상한), 관련 영상, 사람이 검토한 댓글로 제한한다. 처음 실제 게시는 대표가 로그인한 뒤 본인 영상이나 시험용 계정으로 확인한다.

## 3. 전체 구조

```text
[대시보드 3열 — 프로그램 창(내장 웹뷰), 바닐라 JS]
   ① 불러오기        ② 고민 한 줄 + 초안       ③ 프로필·승인·진행·기록
        │                    │                          │
        ▼                    ▼                          ▼
[FastAPI 라우터]  /api/videos   /api/analysis   /api/jobs   /api/records   /sandbox
        │                    │                          │
        ▼                    ▼                          ▼
[YouTube 모듈]        [맥락·LLM·검증]             [운영 규칙]   [브라우저 작업]
 Data API v3           자막→제목·설명 대체          영상당 1개     작업 스레드
 링크 해석             고민 정리 → 초안             하루 상한      ├ youtube: 실제 유튜브에 입력·게시·확인
 뜨기 직전 찾기        규칙 검사·재생성             기록           └ sandbox: 연습 페이지에 같은 흐름
        │                    │                          │
        └────────────────────┴───────────┬──────────────┘
                                         ▼
                                  [SQLite 한 파일]
        외부: YouTube Data API(읽기 전용) · Ollama(로컬) · Chrome(프로필 폴더 지정)
```

### 3.1 폴더와 책임

```text
app/
  main.py            앱 생성과 라우터 연결만 (기존 / 와 /api/health 유지)
  config.py          설정 읽기: .env(비밀값) + config.yaml(규칙)
  db.py              SQLite 연결, 테이블 만들기·버전 올리기
  schemas.py         API 입출력 모델 (pydantic)
  errors.py          공통 오류 종류와 사용자에게 보일 문구
  youtube/
    client.py        Data API v3 호출 (httpx) — 검색, 영상 상세, 인기 댓글
    url_parser.py    유튜브 링크 → 영상 ID
    rising.py        "뜨기 직전" 조건 계산
    quota.py         할당량 사용 기록
  transcript/
    base.py          자막 공급자 공통 규격
    manual.py        사용자가 붙여 넣은 자막
    unofficial.py    비공식 자막 조회 (기본 꺼짐, 설정으로 켬)
  llm/
    base.py          LLM 공통 규격 (generate_json), JSON 꺼내기·스키마 확인 공통 코드
    registry.py      설정의 llm.active 이름으로 공급자를 만들어 준다
    ollama.py        Ollama /api/chat 구현
    (12단계) openai_compatible.py, anthropic.py, cli.py
    prompts.py       분석·초안·재작성 프롬프트
  analysis/
    context.py       영상 맥락 묶음 만들기 (자막 → 없으면 제목·설명, 인기 댓글)
    analyzer.py      고민 한 줄 + 근거 문장 뽑기
    drafter.py       초안 생성, 검사 실패 시 재생성
    validator.py     규칙 검사 (LLM 없이 결정적으로)
  ops/
    rules.py         영상당 1개, 하루 상한 — DB 거래 안에서 강제
    ledger.py        실행 기록
    profiles.py      프로필 목록, 순환 배정
  browser/
    worker.py        브라우저 작업 전용 스레드, 작업 상태 기계
    chrome.py        크롬 실행 (프로필 폴더 지정, 창 위치)
    typing.py        한 글자씩 입력
    targets/sandbox.py   통제된 테스트 페이지 자동화
    targets/assist.py    실제 유튜브: 영상 열기만
                     (처음 계획. 실제로는 jobs.py · sandbox_driver.py · youtube_driver.py ·
                      youtube_check.py로 만들었고, R3에서 assist를 없애고 실제 게시로 바꿨다 — 6절)
    screenshots.py   실패 화면 저장
  api/               라우터 (videos, analysis, jobs, records, sandbox)
  templates/ static/ 화면
tests/
  unit/ integration/ e2e/ fixtures/
config.yaml          비밀이 아닌 규칙 (과제 설정 예시와 같은 모양)
.env                 비밀값만 (커밋 금지)
```

### 3.2 모듈 경계 규칙

- 라우터는 얇게: 입력 검증 → 서비스 호출 → 응답. 판단 로직을 라우터에 두지 않는다.
- 외부 호출(YouTube, Ollama, Chrome)은 각각 한 모듈 뒤에 숨기고, 테스트에서는 가짜로 바꾼다.
- `validator.py`와 `ops/rules.py`는 네트워크·LLM 없이 돌아간다. 평가 15점(운영 규칙)과 금지 조건이 여기 달려 있어 가장 두껍게 테스트한다.

## 4. 데이터 (SQLite)

| 테이블 | 내용 | 핵심 제약 |
|---|---|---|
| `videos` | 영상 ID, 제목, 채널, 올린 시각, 썸네일, 조회수, 가져온 시각, 출처(검색·링크·뜨기직전) | `video_id` 기본키 |
| `video_context` | 자막 출처(자막·수동·없음), 자막 본문, 설명, 인기 댓글 | 영상당 1행 |
| `drafts` | 고민 한 줄, 근거 문장과 출처, 초안 본문, 모델, 검사 결과, 상태(초안·승인·반려) | |
| `posts` | 영상 ID, 대상(sandbox·youtube), 프로필, 초안 ID, 상태(예약·게시·실패), 한국 날짜 | `UNIQUE(target, video_id)` |
| `runs` | 시각, 영상, 프로필, 댓글 본문, 대상, 성공/실패, 사유, 캡처 경로 | 지우지 않는 기록 |
| `job_events` | 작업 ID, 시각, 상태, 메시지 | 진행 상태 표시용 |
| `quota_usage` | 날짜, 사용 단위 | |
| `sandbox_comments` | 테스트 페이지에 달린 댓글 | |

**영상당 1개와 하루 상한을 강제하는 방법.** 게시를 시작하기 전에 `BEGIN IMMEDIATE` 거래 안에서 다음을 한 번에 한다.

1. 오늘(한국 시각 날짜) `posts`에서 상태가 예약 또는 게시인 행 수를 센다. 상한 이상이면 거절.
2. `posts`에 예약 행을 넣는다. `UNIQUE(target, video_id)`에 걸리면 "이미 댓글을 단 영상"으로 거절.
3. 게시가 확인되면 게시로, 실패하면 실패로 바꾼다. 실패는 상한에 세지 않지만 `runs`에는 남는다. 실패한 영상은 다시 시도할 수 있게 실패 행을 예약으로 되돌리는 경로를 둔다.

앱 코드의 if 문이 아니라 DB 제약으로 막기 때문에 버튼을 연달아 눌러도 두 번 달리지 않는다. sandbox 예행과 실제 게시는 `target`으로 나눠 센다.

## 5. 영상 맥락과 초안

### 5.1 맥락 수집 순서

0. 영상 찾기(01칸): 검색 결과에서 **쇼츠(설정 `discover.shorts_under_seconds` 미만, 기본 181초 = 3분 이하·길이 정보 없음)를 뺀다**(`discover.exclude_shorts`, 기본 참, 화면 「쇼츠 제외」). 검색으로 50개를 받아 상세를 보고 원래 순서대로 `max_results`개만 보인다(검색 1회 100단위 그대로). 실제 키로 돌려 보니 최신순 상위가 거의 쇼츠(댓글 0~3개)였다(2026-11-16 실제 데이터 보정).
1. 자막(R4, 2026-11-17): **붙여 넣은 자막 > 자동으로 읽은 자막 > 없음.** 붙여 넣은 자막이 있으면 그것. 없고 「자막 자동으로 읽기」(`transcript.provider: auto`, 기본)가 켜져 있으면 `app/transcript/auto.py`가 `youtube-transcript-api`로 읽는다 — 한국어 올린 자막 → 한국어 자동 생성 → 다른 언어 순, 줄마다 「1:23 …」 시간 표시, 2만 자가 넘으면 앞·뒤 절반씩(가운데 「…(중략)…」), 10초 제한. 읽은 자막은 `video_context`(`transcript_source='auto'`, 언어·자동 생성 여부)에 저장하고 다시 부르지 않는다. 못 읽으면(none·disabled·unavailable·blocked·timeout·network·empty·error) 예외 없이 기록과 `transcript_note`에 남기고 2번으로 간다. 잠깐 막힌 경우(blocked·timeout·network·error)만 30분 뒤나 [다시 읽기] 때 다시 해 본다. 자동 생성 자막이면 AI에 넘기는 글 머리에 「받아쓰기 틀림이 있을 수 있다」를 붙인다.
2. 자막이 없으면 제목과 설명을 본문으로 쓴다(과제 원문이 허용한 대체). 이때 AI에 넘기는 글 머리에 「설명란·댓글에는 광고·협찬·이벤트 응모 글이 섞여 있을 수 있다」는 안내를 붙인다.
3. 인기 댓글: `commentThreads.list(order=relevance)` 상위 20개. 댓글이 막힌 영상이면 빈 목록으로 진행.

> 공식 Data API로는 남의 영상 자막을 내려받을 수 없다(영상 소유자 권한 필요). R4(2026-11-17, PLAYBOOK 「프로그램화 2차」)에서 비공식 경로인 `youtube-transcript-api`를 **기본으로 켰다** — 사람이 매번 붙여 넣지 않아도 영상 내용으로 고민을 읽게. 유튜브가 막거나 바꾸면 조용히 제목·설명으로 대신하고, 「자막 직접 넣기」는 대체 수단으로 남긴다. 어떤 출처를 썼는지(자동으로 읽은 자막 n자(한국어, 자동 생성) / 붙여 넣은 자막 / 못 읽은 이유) 화면과 기록에 표시한다. 설정 「자막 자동으로 읽기」를 끄면 예전처럼 붙여 넣기만 쓴다.

### 5.2 2단계 생성

1. **분석** (낮은 온도): `{ has_love_concern, reason, concern: "고민 한 줄", evidence: [{ quote, source }] }`. `quote`는 맥락 본문에 실제로 있는 문장이어야 한다. 목적은 **영상의 연애 고민**을 찾는 것이고, 설명란·댓글의 광고·협찬·상품 소개·이벤트 응모·구독 유도 글은 무시한다(근거로도 받지 않는다).
   - **연애 고민의 범위(과제 PDF 기준)**: 누군가의 사연이 없어도 영상이 연애·관계를 다루면(연애 심리 분석·강의·팁·토크, 궁합·인연 포함) 연애 고민이 있는 것으로 보고, 시청자가 품을 고민으로 한 줄 정리한다. 과제 예시(남자심리 분석 영상 → 「남자심리는 알다가도 모르겠다」)와 같은 방식이다. 연애 밖 고민(취업·재물 등)으로는 넓히지 않는다 — 과제가 운명원을 「연애 사주」를 잘 보는 곳으로 정했다(2026-11-17).
   - **연애 고민이 없으면 멈춘다**: `has_love_concern`이 거짓이거나, 다시 시켜도 대조 뒤 남은 근거가 0개면 초안을 만들지 않고 `no_love_concern`(「이 영상 자료에서 연애 고민을 찾지 못했습니다」, 다음 행동: 자막을 붙여 넣고 다시 분석하거나 다른 영상 고르기)으로 끝낸다. 02칸에 그 문구가 뜨고 「자막 붙여넣기」가 열린다. 예전의 「근거가 없으면 제목을 근거로」는 없앴다(실제 협찬 영상에서 분석이 상품을 주제로 읽고 초안이 남의 상품을 권했다, 2026-11-16).
   - 초안 근거 고르는 순서: 자막 > 제목 > (연애 고민을 말하는) 댓글 > 설명.
2. **초안** (높은 온도): `{ body, used_quote }`. 분석 결과와 브랜드 사실 목록만 보고 쓴다. 권하는 대상은 운명원 하나뿐이고, 영상 자료에 나오는 다른 상품·브랜드·채널 이름은 권하거나 언급하지 않는다.

둘 다 Ollama `/api/chat`에 JSON 스키마(`format`)를 주고 `stream: false`로 받는다. 생각 과정을 내보내는 모델은 생각 출력을 끈다.

### 5.2.1 LLM 공급자 (바꿔 끼울 수 있게)

지금 쓰는 것은 Ollama 하나다. 하지만 분석·초안 코드는 "어느 LLM인지" 모르게 만들고, 설정만 바꿔 다른 LLM을 물릴 수 있게 한다(대표 지시, 2026-11-16).

```text
analyzer / drafter
      │  generate_json(system, user, schema, …)   ← 이 규격 하나만 안다
      ▼
[LLM 등록부]  config.yaml의 llm.active 이름으로 공급자를 고른다
      ├ ollama             로컬 서버            인증 없음                    ← 4단계에서 구현
      ├ openai_compatible  OpenAI 호환 API      .env의 API 키                ← 12단계
      │                    (OpenAI · xAI Grok · Gemini 호환 주소 · OpenRouter 등 주소만 바꿔 씀)
      ├ anthropic          Claude API           .env의 API 키                ← 12단계
      └ cli                로그인된 CLI 실행     CLI 자신의 로그인을 그대로 씀  ← 12단계
                           (Codex · Claude Code · Gemini CLI)
```

**인증 세 가지**

| 방식 | 무엇 | 이 앱이 다루는 비밀값 |
|---|---|---|
| 없음 | 로컬 Ollama | 없음 |
| API 키 | 각 회사 API | `.env`에 키. 이름은 설정의 `api_key_env`로 지정. 로그 가리기 대상 |
| CLI 로그인 재사용 | 이미 로그인해 둔 CLI를 이 앱이 대신 실행(구독 계정을 그대로 씀) | 없음. 토큰은 CLI가 갖고 있고 이 앱은 읽지 않는다 |

- "헤르메스처럼 로그인된 계정으로 물리기"는 **CLI를 대신 실행하는 방식**으로 한다. CLI가 저장해 둔 로그인 토큰 파일을 이 앱이 읽어서 API를 직접 부르는 방식은 쓰지 않는다. 약관 위반 소지가 있고, 공개 저장소 프로젝트가 남의 토큰 파일을 건드리게 되기 때문이다.
- **CLI 방식의 안전 조건.** 영상 자막과 댓글은 남이 쓴 글이다. 파일·명령 도구를 가진 CLI에 그대로 넣으면 그 글 속의 지시를 따를 위험이 있다. 그래서 CLI는 (1) 빈 임시 폴더에서 (2) 도구 사용을 끄거나 읽기 전용으로 (3) 한 번 답하고 끝나는 모드로 (4) 시간 제한을 걸어 실행한다. 프롬프트는 명령줄 인자가 아니라 표준 입력으로 넘긴다.
- **JSON 출력.** 스키마 강제를 지원하는 공급자는 그 기능을 쓰고, 아닌 공급자는 프롬프트에 스키마를 넣은 뒤 받은 글에서 JSON을 꺼내 스키마와 맞는지 코드로 확인한다. 안 맞으면 한 번 다시 시킨다. 이 확인은 공통 코드에 둔다.
- **화면 표시.** 위 줄 AI 상태에 지금 공급자와 모델, 그리고 "로컬"인지 "외부"인지를 보인다. 외부 공급자를 쓰면 영상 제목·설명·자막·댓글이 그 회사로 전송된다는 것을 설정 화면에 적는다.
- 기본값은 계속 Ollama다. 외부 공급자는 비용이 들 수 있다.

**구현(R5, 2026-11-17)** — 모듈 머리말에 확인한 날짜와 출처를 적었다.

| 종류 | 모듈 | 요청 | 모델 목록([모델 불러오기]·[연결 확인]) |
|---|---|---|---|
| `openai_compatible` | `app/llm/openai_compatible.py` | `POST {base_url}/chat/completions`, `Authorization: Bearer` | `GET {base_url}/models`(글 생성 없음) |
| `anthropic` | `app/llm/anthropic.py` | `POST /v1/messages`, `x-api-key`, `anthropic-version: 2026-10-21` | `GET /v1/models` |
| `cli` | `app/llm/cli.py` | 아래 실행 조건 | 없음(직접 적는다. 비우면 그 프로그램의 기본 모델) |

- 모델 이름은 코드·`config.yaml`에 박지 않는다. 각 회사의 목록에서 고르거나 직접 적는다(`settings.json`의 `llm.models`).
- JSON: 모든 공급자가 프롬프트에 스키마를 넣고 `base.py`의 공통 확인(꺼내기·스키마·한 번 다시)을 쓴다. OpenAI·Grok은 `response_format: json_object`를 함께 보내고, 모델이 400으로 거절하면 빼고 한 번 더 보낸다. 각 회사의 "엄격 스키마" 기능은 이 앱 스키마와 조건이 맞는지 확인하지 않아 쓰지 않는다. `temperature`는 보내지 않는다(Claude API 2026-10-21은 400, OpenAI 추론 모델도 받지 않는다).
- 오류: 401·403 → `llm_auth`, 429(Claude 529 포함) → `llm_rate_limited`, 404 → `llm_model_missing`, 시간 초과 → `llm_timeout`, 연결 실패 → `llm_down`. 문구는 그 AI 이름으로(「OpenAI가 이 API 키를 받아 주지 않았습니다」 등).
- `health()`는 바깥에 묻지 않는다(아래 줄이 30초마다 묻는다). API 키 AI는 키·주소·모델이 있는지만, 로그인된 프로그램은 설치 여부와 `--version`만 본다. 미리 불러오기·「모델 불러오는 중」·첫 분석의 긴 시간 제한·추천 모델 안내는 Ollama만.
- **로그인된 프로그램 실행 조건**(`app/llm/cli.py`, 이 PC의 `--help`와 공식 문서로 확인):
  - Codex(0.152.1): `codex exec --sandbox read-only --skip-git-repo-check --ephemeral --ignore-user-config --ignore-rules --color never -C <빈 임시 폴더> --disable shell_tool,unified_exec,browser_use,computer_use,apps,plugins,multi_agent,image_generation(하나씩) [-m 모델] -`. 프롬프트는 표준 입력(`-`), 답은 stdout의 마지막 메시지.
  - Claude Code(2.1.312): `claude -p <고정 안내> --output-format json --tools "" --safe-mode --strict-mcp-config --no-session-persistence --disable-slash-commands --permission-mode dontAsk --permission-prompts none --no-chrome --system-prompt <고정 글> [--model 모델]`. 영상 자료는 표준 입력, 답은 JSON의 `result`. `--bare`는 구독 로그인을 쓰지 않아 쓰지 않는다.
  - 공통: 빈 임시 폴더(끝나면 지움), 셸 없이 인자 목록(`shell=False`), Windows 콘솔 창 없음(`CREATE_NO_WINDOW`), 시간 제한(`llm.timeout_seconds`), 이 앱의 키 환경 변수는 자식에게 넘기지 않음. 그 프로그램의 로그인·설정 파일은 읽거나 복사하지 않는다. 로그인 여부는 [연결 확인]에서 그 프로그램의 `codex login status`·`claude auth status`로 묻는다.
  - Gemini CLI: 이 PC에 설치돼 있지 않아 `--help`로 조건을 확인하지 못했다 → 물리지 않는다(목록에 「설치 안 됨」/「아직 연결 안 함」, 고를 수 없음).
  - 모델 이름은 `-`로 시작할 수 없다(명령 인자로 들어가므로 `--sandbox` 같은 값을 막는다).

설정 모양(`config.yaml`, 비밀값 없음):

```yaml
llm:
  active: ollama
  providers:
    ollama:  {type: ollama, label: Ollama}           # 주소·모델은 .env의 OLLAMA_BASE_URL, OLLAMA_MODEL
    openai:  {type: openai_compatible, label: ChatGPT(OpenAI), sends_to: OpenAI,
              base_url: "https://api.openai.com/v1", api_key_env: OPENAI_API_KEY,
              json_mode: true, max_tokens_field: max_completion_tokens}
    claude:  {type: anthropic, label: Claude(Anthropic), sends_to: Anthropic,
              base_url: "https://api.anthropic.com", api_key_env: ANTHROPIC_API_KEY}
    gemini:  {type: openai_compatible, label: Gemini(Google), sends_to: Google,
              base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
              api_key_env: GEMINI_API_KEY, json_mode: false, max_tokens_field: ""}
    grok:    {type: openai_compatible, label: Grok(xAI), sends_to: xAI, base_url: "https://api.x.ai/v1",
              api_key_env: XAI_API_KEY, json_mode: true, max_tokens_field: max_completion_tokens}
    custom:  {type: openai_compatible, label: 직접 입력, base_url: "", editable_url: true,
              key_optional: true, api_key_env: CUSTOM_LLM_API_KEY, max_tokens_field: max_tokens}
    codex-cli:  {type: cli, label: Codex, program: codex}
    claude-cli: {type: cli, label: Claude Code, program: claude}
    gemini-cli: {type: cli, label: Gemini 프로그램, program: gemini}   # 화면에 「CLI」를 쓰지 않는다
```

주소·모델 이름·실행 옵션은 자주 바뀐다. 바꿀 때 각 회사 문서와 `--help`로 다시 확인하고, 문서에 없는 값을 지어 넣지 않는다.

### 5.3 댓글 형식

```text
[광고] <본문>
```

- 표기 문구는 `config.yaml`의 `comment.disclosure`. 맨 앞에 둔다.
- **글자 수는 표기를 포함한 전체 길이**로 40~120자를 센다(원문 조건을 더 엄격하게 지키는 쪽).
- 말투(2026-11-17 대표 결정, 과제 PDF 기준): **영상을 본 시청자의 말투.** 영상 속 말에 반응·공감하고 「요즘 운명원 얘기 많이 보이던데 저도 연애 사주 한번 보고 싶어요」처럼 **의향**까지만 쓴다. 써 본 척하는 지어낸 후기(과제 PDF가 금지), 지어낸 애인 이야기, 효능 단정은 쓰지 않는다. 운명원은 `brand.facts`와 가벼운 평판(「잘 본다던데」)까지만. (예전: 홍보 담당자 말투, 「보고 싶다」·「잘 본다던데」 금지)

### 5.4 규칙 검사 (`validator.py`, LLM 없이)

V12는 2026-11-16 5단계 점검에서 더했다. 실제 모델(qwen3.8:27b) 초안에 한자 한 글자가 섞여 나왔는데 V1~V11이 모두 통과시켰기 때문이다.

| 번호 | 검사 | 실패 예 |
|---|---|---|
| V1 | 전체 길이 40~120자, 줄바꿈 없음 | 35자 |
| V2 | 링크 없음 | `http`, `www.`, `도메인.com` |
| V3 | 해시태그 없음 | `#연애` |
| V4 | 광고 표기를 켰으면 맨 앞에 있음(끄면 「표기 끔」으로 통과, R3) | 켰는데 표기 누락 |
| V5 | 브랜드 이름이 들어 있음 | "운명원" 없음 |
| V6 | 근거 문장이 맥락 본문에 실제로 있음(공백·문장부호 무시, 유사도 기준) | 지어낸 장면 |
| V7 | 초안이 근거 문장의 핵심 낱말을 담고 있음 | 영상과 무관한 일반 문장 |
| V8 | 직접 이용 후기 표현 없음(써 본 척) | "봤는데 소름", "받아봤어요", "다녀왔", "예약했어요" |
| V9 | 지어낸 연애 사연 없음(내 애인·전 애인 이야기). 「저도 한번 보고 싶다」 같은 시청자 의향·공감은 통과(2026-11-17) | "제 남친도 그래요", "우리 오빠도" |
| V10 | 확인할 수 없는 효능·최상급 표현 없음(브랜드 사실 목록에 있는 것만 허용). 가벼운 평판(「잘 본다던데」, 「많이 보이던데」)은 통과, 맞힌다는 말은 남의 말로 옮겨도 실패(2026-11-17) | "100% 맞음", "제일 용한", "잘 맞는대요" |
| V11 | 이전 초안들과 지나치게 비슷하지 않음 | 영상만 바뀐 같은 문장 |
| V12 | 한글·영문·숫자·기본 문장부호만 씀(한자, 일본어 글자, 이모지 등 없음) | "마음이揪입니다" |

검사에 걸리면 실패 사유를 프롬프트에 넣어 최대 3번 다시 만든다. 그래도 걸리면 걸린 항목을 화면에 빨갛게 표시하고 사람이 고치게 한다. **검사를 통과하지 못한 초안은 승인 버튼이 눌리지 않는다.** 사람이 고친 글도 같은 검사를 다시 거친다.

### 5.5 브랜드 사실 목록

`config.yaml`의 `brand.facts`에 적힌 문장만 운명원에 대한 사실로 쓴다(예: "연애 사주 상담을 하는 곳"). 목록에 없는 효능·실적·후기는 쓰지 않는다. 과제 원문의 "잘 봐주는 곳으로 유명"은 확인할 수 없으므로 기본 목록에 넣지 않는다.

## 6. 브라우저 연결

### 6.1 두 가지 게시 방식 (R3)

| | 실제 게시 (`youtube`, 기본) | 연습 모드 (`sandbox`) |
|---|---|---|
| 고르는 법 | ③ 「연습 모드」 끔(기본. 설정 `browser.default_target: youtube`) | ③ 「연습 모드」 켬 |
| 주소 | `https://www.youtube.com/watch?v=<이번 작업의 영상 ID>` 하나만 | 이 앱이 주는 `/sandbox/watch?v=<영상ID>` |
| 영상 | 어떤 영상이든 | 어떤 영상이든 |
| 프로필 열기 · 댓글 창 누르기 · 한 글자씩 입력 | 자동(댓글 상자가 보일 때까지 마우스 휠로 내림) | 자동 |
| 게시 | 입력을 마치면 바로 「댓글」(게시 직전 확인을 켜면 [게시]를 받은 뒤) | 같음 |
| 게시 확인 | 페이지에서 내 댓글을 찾고, 못 찾으면 Data API. 둘 다 못 찾으면 「게시됨(확인 못 함)」 | 페이지에서 찾는다. 못 찾으면 실패 |
| 시작 전 확인 | 작업 하나 · 댓글 막힌 영상 · 자동 입력 도구와 크롬 · 프로필 로그인 · 프로필 창 · 승인한 초안 · 영상당 1개 · 오늘 상한 | 댓글 막힘·로그인 확인만 빼고 같음 |
| 광고 표기 | 켬/끔(②칸, 처음 상태는 설정 기본값) | 같음 |

- 옛 대상 이름 `assist`(크롬만 열고 사람이 붙여넣기)와 `youtube_auto`(내 채널 영상 자동 게시)는 API와 설정에서 계속 받고, 모두 실제 게시로 처리한다. 「크롬만 열어 주고 사람이 붙여넣기」 방식과 그 단추([댓글 복사]·[게시했어요])는 없앴다. 옛 API `POST /api/jobs/{id}/confirm`은 남겨 두되 받을 작업이 없어 늘 거절한다. `own_video_ids` 설정 키는 읽어도 무시한다.
- `sandbox` 페이지는 한국어 문구("댓글 추가...", "댓글", "취소")를 쓰는 단순한 자체 화면이다. 유튜브 화면을 베끼지 않는다. 일부러 실패를 내는 스위치(게시 버튼 숨김, 응답 지연)를 두어 실패 처리와 화면 캡처를 시험한다.
- 실제 유튜브 화면을 자동으로 조작하는 코드는 `app/browser/youtube_driver.py` 하나뿐이다. 실행기를 만들 때 정한 **이번 작업의 영상 하나**의 주소만 열고(아니면 열기 전에 거절), 페이지가 그 영상·동의·로그인 화면 밖으로 옮겨 가면 멈춘다.
- 로그인: 프로필 화면의 [로그인 확인](R2)이 1시간 안에 「로그인 안 됨」으로 본 프로필은 시작 전에 막고 「프로필 화면에서 [로그인하기]」로 안내한다(자동 배정은 그 프로필을 건너뛴다). 확인한 적이 없거나 오래됐으면 실행기가 영상 페이지에서 직접 본다(오른쪽 위 내 사진이 없고 「로그인」이 보이면 입력 전에 멈추고, 그 프로필을 「로그인 안 됨」으로 고쳐 둔다).
- 댓글 막힘: 맥락을 모을 때 YouTube가 「댓글 막힘」을 알려 준 영상은 시작 전에 거절하고, 페이지에서 「댓글 사용 중지」 안내가 보여도 입력 전에 멈춘다.
- **화면 요소.** 요소 이름은 `SELECTORS` 한곳에 모았다. 화면 글자(한국어 문구)가 아니라 언어와 상관없는 요소 이름(`#simplebox-placeholder`, `ytd-commentbox #submit-button` 등)으로 찾는다. 못 찾으면 실패 사유에 「찾지 못한 요소: 「댓글」 게시 단추(요소 이름 …)」처럼 어느 요소인지 적고 화면 캡처를 남긴다. `scripts/check_youtube_page.py <주소|ID> [--profile 유튜브1] [--show]`는 영상 페이지를 열어 요소가 잡히는지 **읽기만** 해서 표로 보여 준다(입력·누르기 없음. 「댓글 추가...」를 눌러야 생기는 글 칸과 게시 단추는 「눌러야 보임 — 실제 게시 때 확인」). 2026-11-17 로그인하지 않은 임시 프로필(창 없이)로 공개 영상 하나를 읽어, 로그인 안 된 상태에서 보이는 요소(「로그인」 단추·댓글 영역·댓글 입력 자리·달린 댓글)가 `SELECTORS`와 맞는 것을 확인했다. 로그인해야 보이는 요소(내 사진·글 칸·게시 단추)는 대표가 로그인한 뒤 첫 게시에서 확인한다.
- 「댓글」을 누른 뒤에는 확인을 못 해도 실패로 되돌리지 않는다(실패로 풀면 다시 시도해 같은 댓글이 두 번 달린다). 자동 테스트는 같은 요소 이름을 쓴 가짜 페이지(`tests/fixtures/fake_youtube_watch.html`)를 가로채기로 끼워 넣어 돈다(실제 YouTube에 접속하지 않는다. `tests/conftest.py`가 가짜 페이지를 끼우지 않은 실제 실행기와 실제 로그인 확인을 막는다).

### 6.2 작업 상태

```text
대기 → 프로필 여는 중 → 입력 중 → [게시 직전 확인을 켰을 때만] 게시 대기 → 게시 중 → 확인 중 → 게시 완료
                                                                                └→ 실패(사유 + 화면 캡처)
```

[댓글 달기]를 누르면 화면이 지금 초안을 승인하고(규칙 검사 통과 필수) 작업을 시작한다. 게시 직전 확인(기본 끔)을 켰을 때만 입력 뒤 「게시 대기」에서 [게시]를 기다린다(5분 안에 안 누르면 실패).

상태가 바뀔 때마다 `job_events`에 적고, 대시보드는 0.5초마다 물어 와서 보여 준다. 작업은 한 번에 하나만 돈다.

### 6.3 기술 선택

- **Playwright 동기 API를 전용 스레드에서** 돌린다. Windows에서 uvicorn 이벤트 루프와 Playwright 비동기 API가 충돌하는 문제를 피한다.
- 크롬은 `launch_persistent_context(user_data_dir=..., channel="chrome")`로 연다. 프로필 폴더는 저장소 밖(`%LOCALAPPDATA%\JGMarketingAgent\profiles\profile-1` 등)에 둔다. 폴더 이름은 영문, 화면에 보이는 이름만 한글(유튜브1)이다.
- 구글 로그인은 자동화 창에서 막히는 경우가 많다. `scripts/setup_profile.ps1`이 일반 크롬을 같은 폴더로 열어 사람이 한 번 로그인해 둔다. `sandbox`에는 로그인이 필요 없다.
- **창 위치.** 시험·녹화용 창은 주 모니터에 띄우지 않는다. 자동 테스트는 창 없이(headless) 돌리고, 시연처럼 창이 보여야 할 때는 `config.yaml`의 `browser.window_position`(기본 `60,-1060`, 위쪽 2번 모니터)을 쓴다. 9단계부터 크롬을 띄우기 전에 실제 모니터 배치를 읽어(`app/browser/screens.py`) 그 위치가 어느 모니터에도 없으면 주 모니터 `60,60`에 띄우고 작업 기록에 남긴다(모니터 배치가 다른 PC에서 창이 화면 밖에 떠 안 보이는 일을 막는다).
- 실패하면 `error_screenshots/<작업ID>.png`를 남기고 사유를 `runs`에 적는다.

## 7. YouTube Data API

| 용도 | 호출 | 단위 |
|---|---|---:|
| 최신 영상 목록 | `search.list(q, type=video, order=date, regionCode=KR, relevanceLanguage=ko)` | 100 |
| 영상 상세·조회수 | `videos.list(part=snippet,statistics,contentDetails)` | 1 |
| 인기 댓글 | `commentThreads.list(order=relevance)` | 1 |
| 게시 확인(실제 게시에서 페이지로 못 찾았을 때) | `commentThreads.list(order=time, searchTerms)` | 1 |

- 하루 10,000단위. 검색이 100단위라 하루 약 100번이 한계다. 같은 검색은 10분 동안 SQLite에 저장한 결과를 쓴다. 사용량을 `quota_usage`에 적고 화면에 보인다.
- 키는 `.env`의 `YOUTUBE_API_KEY`. 로그와 오류 문구에 키가 찍히지 않게 주소의 `key=`를 가린다.
- 오류 분류: 키 없음 · 키 거부 · 할당량 초과 · 댓글 막힘 · 영상 없음 · 네트워크. 각각 사용자에게 보일 한국어 문구와 다음 행동을 정한다.
- **뜨기 직전 (R4에서 만듦, `app/youtube/rising.py`, `GET /api/videos/rising`).** 조회수 1,000~5,000이면서 시간당 150 이상이려면 올린 지 약 33시간(5,000 ÷ 150) 안이어야 한다. 그래서 `publishedAfter = 지금 − 34시간`, 검색어 `rising.query`(기본 「연애」), 최신순 50개(100단위)로 좁힌 뒤 `videos.list`(1단위)로 조회수를 받아 `조회수 ÷ 경과 시간`을 계산한다(경과 6분 미만은 0.1시간, 조회수를 받은 때 기준). 경계값은 포함, 숫자는 설정(`rising.min_views`·`max_views`·`min_views_per_hour`), 시간당 조회수가 큰 순서. 쇼츠 빼기는 ①의 체크를 따른다. 같은 요청은 10분 저장(`search_cache`). 고른 영상은 `videos.source='rising'`으로 남기고, 게시 작업은 그 출처의 영상을 거절한다(`rising_draft_only`, 409, 실제 게시·연습 모드 모두) — **초안까지만.** 같은 영상을 검색이나 링크로 다시 불러오면 출처가 바뀌어 평소처럼 게시할 수 있다(마지막에 불러온 목록이 출처).

## 8. 설정

`config.yaml` (커밋함, 비밀값 없음):

```yaml
profiles: [유튜브1, 유튜브2, 유튜브3]
comment:
  min_chars: 40
  max_chars: 120
  brand: 운명원
  disclosure: "[광고]"
  disclose_default: true  # 광고 표기 기본값(켬). ②칸 「광고 표기 붙이기」의 처음 상태(모든 영상, R3)
brand:
  facts:
    - 운명원은 연애 사주 상담을 하는 곳이다
limits:
  daily_max_comments: 10
posting:
  confirm_before_post: false  # 게시 직전 확인(기본 끔: [댓글 달기] 한 번으로 게시까지, R3)
discover:
  query: 연애 고민
  max_results: 12
  shorts_under_seconds: 181   # R2: 이보다 짧은 영상을 쇼츠로 본다(유튜브 쇼츠는 3분까지)
rising:
  query: 연애
  min_views: 1000
  max_views: 5000
  min_views_per_hour: 150
transcript:
  provider: manual        # manual | unofficial
browser:
  default_target: youtube # youtube(실제 게시, 기본) | sandbox(연습 모드). 옛 assist·youtube_auto도 youtube
  window_position: "60,-1060"
  typing_delay_ms: [60, 160]
llm:
  active: ollama          # 4단계에 provider → active로 바꿨다(옛 키도 읽는다). 모양은 5.2.1
  timeout_seconds: 180
  num_ctx: 8192
  keep_alive: "30m"
  context_chars: 6000
  providers:
    ollama: {type: ollama, label: Ollama}
    # R5: openai · claude · gemini · grok · custom · codex-cli · claude-cli · gemini-cli(5.2.1)
```

`.env` (커밋 금지, **개발용 선택**): `YOUTUBE_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`. 외부 AI 키는 `llm.providers.*.api_key_env`에 적은 이름으로(`OPENAI_API_KEY`·`ANTHROPIC_API_KEY`·`GEMINI_API_KEY`·`XAI_API_KEY`·`CUSTOM_LLM_API_KEY`, R5). R2부터 사용자는 `.env`와 `config.yaml`을 열지 않는다(아래 8.1).

### 8.1 프로그램 안에서 설정 (R2, 2026-11-17)

- **읽는 순서**: 사용자 설정 → 환경 변수·`.env`(개발용, 없어도 됨) → `config.yaml`(기본값).
  사용자 설정은 `%LOCALAPPDATA%\JGMarketingAgent\settings.json`(`{"version": 1, "values": {칸 이름: 값}}`).
  테스트는 `load_settings(user_dir=…)`나 환경 변수 `JG_USER_DIR`로 임시 폴더를 쓴다(`app/user_settings.py`).
- **바꿀 수 있는 칸**(`app/user_settings.FIELDS`, 칸 이름 = `config.yaml` 경로):
  - 유튜브 연결: API 키(따로 저장, 아래).
  - AI 모델: `llm.model`.
  - 댓글 규칙: `comment.min_chars`(10~500)·`comment.max_chars`(20~1000, 최소 < 최대, 홍보 표기 + 10자 이상), `comment.brand`, `brand.facts`(10줄까지), `comment.disclosure`, `comment.disclose_default`.
  - 게시: `limits.daily_max_comments`(1~50), `posting.confirm_before_post`, `browser.typing_speed`(느리게 120~260ms · 보통 60~160ms · 빠르게 25~70ms), `browser.window_screen`.
  - 영상 찾기: `discover.query`·`discover.max_results`(1~50)·`discover.exclude_shorts`·`discover.shorts_under_seconds`(10~3600, 기본 181).
- **저장**(`PUT /api/settings`, 바꾼 칸만):
  - 칸마다 검사해 틀리면 422 `settings_invalid`와 `fields`(칸 이름 → 한국어 이유). 하나라도 틀리면 아무것도 저장하지 않는다.
  - 기본값과 같은 값은 파일에 두지 않는다(나중에 `config.yaml` 기본값이 바뀌면 따라간다).
  - 저장하면 서비스 묶음을 새 설정으로 다시 만들어 **바로 적용**한다(`ServiceHolder.update_settings`). 프로그램을 다시 켤 필요가 없다.
  - 게시 작업이 돌고 있으면 409 `settings_busy`(「지금 게시 중입니다. 끝난 뒤 다시 저장해 주세요」).
  - 로그인 창 목록(`LoginWindows`)은 서비스를 다시 만들어도 남는다.
- **[기본값으로]**(`POST /api/settings/reset`)는 `settings.json`을 지운다. 저장한 API 키는 남긴다.
- **글 쓰는 AI**(R5, UI_SPEC 6.1):
  - 칸: `llm.active`(고른 AI 이름), `llm.models`(AI 이름 → 모델), `llm.base_urls`(「직접 입력」 주소). `llm.models`·`llm.base_urls`는 보낸 이름만 바꾸고 빈 글이면 그 이름을 지운다.
  - `llm.active`는 준비된 AI만 받는다: 목록에 있음 · 지원하는 종류 · (API 키 AI) 키 있음 · (「직접 입력」) 주소 있음 · 모델 있음 · (프로그램) 확인한 프로그램이고 설치됨. 아니면 422와 이유(「API 키를 먼저 넣어 주세요」 등).
  - 저장하면 바로 적용(다음 분석·초안이 새 AI로). 게시 중이면 409.
  - API: `GET /api/llm/providers`(목록·준비 상태, 바깥에 묻지 않음), `POST /api/llm/providers/{이름}/test`([연결 확인]: API 키 AI는 모델 목록 — 글을 만들지 않아 요금이 들지 않는 호출, 프로그램은 그 프로그램의 로그인 상태 명령), `GET /api/llm/models?provider=<이름>`(인자가 없으면 전과 같이 Ollama).
  - **AI API 키**: `PUT`·`DELETE /api/settings/llm-key/{이름}`. AI마다 따로 DPAPI로 암호화해 `llm_keys/<이름>.bin`에 둔다(유튜브 키 파일과 그 동작은 그대로). 읽는 순서는 프로그램에 저장한 키 > `.env`(`api_key_env`) > 없음. 응답에는 있는지와 출처만. 저장한 키는 비밀값 목록에 들어가 오류 문구에서 가리고, 로그는 모든 줄에서 가린다(`app/errors.remember_log_secrets`).
- **모델(Ollama)**: 프로그램에서 고른 모델(`llm.model`) > `.env`의 `OLLAMA_MODEL` > 코드 기본값. 다른 AI의 모델은 `llm.models`.
  모델 목록은 `GET /api/llm/models`(Ollama `/api/tags`). 일반 모델이 위, 코드용·임베딩용은 아래에 표시만 다르게.
- **YouTube API 키**:
  - Windows DPAPI(현재 사용자, ctypes)로 암호화해 `youtube_key.bin`에 둔다. 평문은 파일·응답·화면·로그 어디에도 없다.
  - 프로그램에 저장한 키 > `.env`의 키. 응답에는 `key_configured`와 출처(`program` 프로그램에 저장 / `dev_file` 개발용 설정 파일)만 싣는다.
  - 저장한 키도 로그 가리기 대상이다.
  - Windows가 아니면 저장을 거절하고(503 `secret_store_unavailable`) `.env`를 안내한다.
  - [연결 확인]은 1단위짜리 호출(`i18nLanguages`)로 결과를 쉬운 말로 알린다(연결됨 · 키 없음 · 키 거부 · 할당량 · 인터넷 · 알 수 없음).
- **크롬 창 위치**: 좌표를 치지 않는다. 설정 화면에서 모니터를 고르면(`GET /api/screens`) 그 모니터 왼쪽 위에서 `+60,+60`을 `browser.window_position`에 저장한다.
- `comment.disclose_default`·`posting.confirm_before_post`는 R2에서는 저장·읽기만 한다(화면에 「곧 적용」). 게시 동작에는 R3에서 쓴다.

### 8.2 프로필 로그인 (R2, 2026-11-17)

- **[로그인하기]**(`POST /api/profiles/{name}/login`):
  - 그 프로필 폴더로 보통 크롬 창을 구글 로그인 주소로 연다. 인자 목록으로 열고 셸을 쓰지 않으며, 자동화 표시 인자가 없다(`app/browser/login.py`).
  - 로그인은 사람이 그 창에서 한다. 프로그램은 아이디·비밀번호를 받거나 저장하거나 치지 않는다.
  - 창을 닫으면 한 번 저절로 [로그인 확인]을 돈다.
- **[로그인 확인]**(`POST /api/profiles/{name}/check`):
  - 창 없이 유튜브를 열어 로그인 표시와 채널 이름만 읽는다(`youtube_driver.SELECTORS`, 누르기·입력 없음).
  - Playwright는 기존 작업 스레드에서만 돈다. 게시 중이면 409 `profile_check_busy`, 프로필 크롬이 열려 있으면 409 `profile_in_use`.
  - 결과는 DB `profile_logins` 표에 남아 프로필 화면·아래 줄·③ 프로필 고르기에 보인다.
- **[유튜브 열기]**(`POST /api/profiles/{name}/open`)는 그 프로필로 유튜브 첫 화면을 연다(로그아웃은 그 창에서 사람이 한다).

기존 `.env.example`의 `DAILY_MAX_ACTIONS`는 과제 용어와 맞춰 `config.yaml`의 `limits.daily_max_comments`로 옮긴다.

## 9. 테스트 전략

| 종류 | 표시 | 내용 | 기본 실행 |
|---|---|---|---|
| 단위 | (없음) | 링크 해석, 규칙 검사 V1~V12, 영상당 1개·하루 상한(임시 DB, 동시 요청), 뜨기 직전 계산, 맥락 대체 순서, 프로필 순환 | 예 |
| 통합 | (없음) | YouTube·Ollama를 `httpx.MockTransport`와 저장해 둔 응답으로 대체, 라우터는 가짜 서비스 주입 | 예 |
| 화면 자동화 | `e2e` | 창 없는 크롬으로 연습 페이지와 **가짜 유튜브 페이지**(실제 유튜브 주소 요청을 가로채 지어낸 페이지를 돌려줌): 타이핑 → 게시 → 확인, 실패 시 캡처 | 예 (Playwright 설치 시) |
| 실제 호출 | `live` | 진짜 YouTube API 1회, 진짜 Ollama 1회 | 아니오 (`RUN_LIVE=1`일 때만) |

- 자동 테스트는 인터넷, API 키, Ollama 없이 통과해야 한다.
- 초안 품질은 통과/실패로 재기 어렵다. `scripts/eval_drafts.py`가 표본 영상 맥락으로 초안을 만들어 규칙 통과율과 결과물을 표로 보여 준다. 모델 고르기에 쓴다.

## 10. 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 로컬 소형 모델의 한국어 품질 | 맥락 이해 25점 + 유도 20점 | 설치된 모델로 비교 평가 후 결정. LLM 규격을 분리해 다른 모델로 바꿀 수 있게 함 |
| 12GB 그래픽 메모리에 17~23GB 모델 | 첫 응답이 느림, 시연 중 멈춤 | 시연 전 미리 불러 두기(`keep_alive`), 시간 제한 넉넉히, 진행 표시 |
| 자막을 못 구함 | 장면·말 언급이 약해짐 | 수동 붙여넣기 칸, 설명·인기 댓글 대체, 출처 표시 |
| API 할당량 초과 | 시연 중 목록이 안 뜸 | 10분 저장, 사용량 표시, 시연용 저장 데이터 |
| Windows에서 Playwright 충돌 | 브라우저가 안 열림 | 동기 API + 전용 스레드 |
| 구글 로그인 차단 | 프로필 준비 실패 | 일반 크롬으로 수동 로그인하는 준비 스크립트 |
| 한글 프로필 폴더 이름 | 경로 오류 | 폴더 이름은 `profile-1` 같은 영문, 화면 이름만 한글 |
| 실제 유튜브 자동 입력이 감지됨 | 계정 제한, 댓글 삭제 | 하루 상한·영상당 1개·사람이 검토한 댓글만, 처음 게시는 본인 영상이나 시험용 계정으로(R3) |
| 유튜브 화면이 바뀜 | 요소를 못 찾아 실패 | 요소 이름은 `SELECTORS` 한곳, 실패 사유에 요소 이름, `scripts/check_youtube_page.py`로 읽기만 해서 점검 |
| 비밀값 유출(공개 저장소) | 키 도용 | `.env` 커밋 금지, 커밋 전 비밀값 검사, 로그에서 키 가림 |

## 11. 아직 정하지 않은 것 (대표 결정 필요)

1. **자막 출처.** R4(2026-11-17)에서 비공식 자동 읽기(`youtube-transcript-api`, 약관상 회색 지대)를 기본으로 켰다(PLAYBOOK 「프로그램화 2차」). 대표가 끄고 싶으면 설정 「자막 자동으로 읽기」를 끈다(붙여 넣기만 남는다).
2. **실제 유튜브 게시 방법.** 사람이 직접 붙여넣고 게시(기본)만 둘지, 승인 뒤 공식 API(`commentThreads.insert`, 구글 로그인 동의 필요)로 올리는 길을 추가할지.
3. **LLM 모델.** 4단계 비교 평가 결과로 정한다. 로컬 모델 품질이 부족하면 외부 모델을 쓸지.
4. **폴더 이름.** 지금 `JG-Marketing-Agent-Stage1`. 공개 저장소 이름은 `jg-marketing-agent`로 한다. 로컬 폴더 이름은 그대로 둔다.
