"""[설치 방법 보기]의 공식 설치 안내와 첫 실행 안내(2026-11-17, 아무 PC에서나 AI 연결).

이 앱은 설치하지 않는다. 공식 문서에 적힌 설치 명령과 공식 페이지 주소를 보여 주고,
사람이 복사해 직접 실행한다. 모두 2026-11-17에 공식 문서로 확인했다.
문서에 없는 것은 쓰지 않는다.

- Claude Code — https://code.claude.com/docs/en/setup : Windows 기본(권장) 설치는
  PowerShell `irm https://claude.ai/install.ps1 | iex`. 무료 claude.ai 요금제에는
  Claude Code가 들어 있지 않다. 로그인은 `claude auth login`
  (https://code.claude.com/docs/en/cli-reference).
- Codex — https://learn.chatgpt.com/docs/codex/cli.md : Windows 설치는 PowerShell
  `irm https://chatgpt.com/codex/install.ps1 | iex`(설치 프로그램이 사용자 PATH에
  `%LOCALAPPDATA%\\Programs\\OpenAI\\Codex\\bin`을 더한다). 로그인은 `codex login`
  (https://learn.chatgpt.com/docs/auth.md).
- Gemini(명령줄 프로그램) — developers.googleblog.com 공지(2026-05-19,
  /en/an-important-update-transitioning-gemini-cli-to-antigravity-cli/): 2026-06-18부터
  개인 무료 계정(Google AI Pro/Ultra·개인용 Code Assist)으로는 쓸 수 없다. 기업 라이선스와
  유료 API 키로는 계속 쓸 수 있다. 로그인 상태를 묻는 명령은 문서에 없다
  (https://geminicli.com/docs/get-started/authentication/).
  안전 조건 네 가지(2026-11-17 공식 문서, 기획 세션 기준):
  ① 비대화 한 번 실행 — 확인: `-p` "Forces non-interactive mode"
     (https://geminicli.com/docs/cli/cli-reference/, 2026-05-01).
  ② 프롬프트를 표준 입력으로 — 확인: `-p` "Appended to stdin input if provided"(같은 쪽).
  ③ 도구 끔 또는 승인 없이 쓰기 불가 — **확인 못 함.** 쓰기·셸 도구는 `ask_user`이고
     "In non-interactive mode, this is treated as `deny`"
     (https://geminicli.com/docs/reference/policy-engine/, 2026-04-30). 그러나 계획 모드
     쪽(https://geminicli.com/docs/cli/plan-mode/, 2026-06-18)은 계획 모드가 기본으로 켜져
     있고, 「start a plan for…」 같은 말에 모델이 enter_plan_mode를 부르며, 비대화 실행에서는
     enter_plan_mode·exit_plan_mode를 확인 없이 승인하고 계획 모드를 나가면 YOLO(모두 자동
     승인)로 바뀐다고 적는다. 영상 자막 속 글이 이 길을 열 수 있다. 모든 도구를 막는
     `--admin-policy`는 받는 값(파일·폴더)이 문서에 없고, 시스템 정책 파일이 있으면 무시된다.
     도구를 모두 끄는 인자도 문서에 없다.
  ④ 시간 제한 — 이 앱이 프로세스에 건다(문서와 상관없음).
  → ③ 때문에 물리지 않는다(목록에는 두되 고를 수 없게, 칸에 까닭).
- Antigravity CLI(`agy`, https://antigravity.google/docs/cli/headless/): 표준 입력을
  `--input-format stream-json`에서만 받고(그때 `-p`는 버려짐), 승인 안 된 도구는
  「soft-denied」로 이어 가며, 공식 저장소 이슈 #45(v1.0.0)에 「-p가 파일 쓰기를 자동 승인」
  (https://github.com/google-antigravity/antigravity-cli/issues/45), 로그인 상태 명령 없음
  → 물리지 않는다. 목록에도 넣지 않고 Gemini 칸 안내에 한 줄로 적는다.

데스크톱 앱이 명령줄 프로그램을 함께 설치하는지(같은 날 공식 문서):
- Claude 데스크톱 앱의 Code 탭은 「자체 Claude Code를 돌린다」
  (https://code.claude.com/docs/en/desktop). 그 앱이 `claude`를 PATH에 넣는다는 말은
  문서에 없다 → 확인 못 함(따로 설치한다고 안내한다).
- Codex 앱과 명령줄 프로그램은 「설치 환경이 다르다」(learn.chatgpt.com). 앱이 `codex`를
  PATH에 넣는다는 말은 문서에 없다 → 확인 못 함(따로 설치한다고 안내한다).
"""

from __future__ import annotations

from dataclasses import dataclass

CHECKED = "2026-11-17"


@dataclass(frozen=True)
class InstallGuide:
    command: str  # 복사해 붙여 넣을 공식 설치 명령(PowerShell)
    page: str  # 공식 설치 안내 페이지
    shell: str  # 어디에 붙여 넣는지
    notes: tuple[str, ...] = ()  # 화면에 보일 짧은 안내
    checked: str = CHECKED


GUIDES: dict[str, InstallGuide] = {
    "claude": InstallGuide(
        command="irm https://claude.ai/install.ps1 | iex",
        page="https://code.claude.com/docs/en/setup",
        shell="PowerShell",
        notes=(
            "Claude 유료 요금제(Pro 이상)나 Anthropic Console 계정이 필요합니다. "
            "무료 요금제에는 들어 있지 않습니다.",
            "Claude 데스크톱 앱을 쓰고 있어도 이 프로그램은 따로 설치합니다"
            "(앱이 함께 설치한다는 안내는 공식 문서에 없습니다).",
        ),
    ),
    "codex": InstallGuide(
        command=(
            'powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1'
            ' | iex"'
        ),
        page="https://learn.chatgpt.com/docs/codex/cli.md",
        shell="PowerShell",
        notes=(
            "ChatGPT 계정으로 로그인합니다(요금제에 따라 쓸 수 있는 양이 다릅니다).",
            "Codex 데스크톱 앱을 쓰고 있어도 이 프로그램은 따로 설치합니다"
            "(공식 문서는 앱과 설치 환경이 다르다고 적고 있습니다).",
        ),
    ),
}

# 물리지 않는 프로그램을 화면에 설명하는 말(목록에는 보이되 고를 수 없다)
NOT_WIRED: dict[str, tuple[str, ...]] = {
    "gemini": (
        "구글이 2026년 6월부터 개인 무료 계정의 이용을 끝냈습니다. 기업 계정이나 유료 키가 "
        "있어야 합니다. 없으면 「API 키로 → Gemini」를 쓰세요.",
        "공식 공지: 2026년 5월 19일 발표, 2026년 6월 18일부터 적용(2026-11-17 확인).",
        "연결하지 않은 까닭: 이 프로그램은 명령 없이 돌릴 때 「계획 모드」를 스스로 켰다 끄면 "
        "승인 없이 파일을 고치고 명령을 실행하는 상태로 바뀐다고 공식 문서에 적혀 있습니다. "
        "남이 쓴 영상 자막을 넘기면 그 글이 시키는 대로 할 수 있어 연결하지 않았습니다"
        "(문서 기준 판단 · 실제 실행 확인 전).",
        "Antigravity 앱과는 다른 프로그램입니다. 같은 구글 계정으로 로그인합니다.",
        "Antigravity는 글을 쓰는 중에 파일을 고칠 수 있어, 남이 쓴 영상 자막을 안전하게 넘길 "
        "방법을 확인하지 못했습니다.",
    ),
}
NOT_WIRED_PAGE: dict[str, str] = {
    "gemini": (
        "https://developers.googleblog.com/en/"
        "an-important-update-transitioning-gemini-cli-to-antigravity-cli/"
    ),
}

# 첫 실행 안내(시작 준비 상자와 설정 「AI 모델」 맨 위). 이 순서가 권하는 순서다.
# 「무료」는 공식 가격 페이지에 무료 등급이 적힌 곳만 쓴다(Gemini API —
# https://aistudio.google.com/docs/pricing 「Free of charge」).
FIRST_RUN_KEY_NAME = "gemini"
FIRST_RUN_KEY_PAGE = "https://aistudio.google.com/apikey"
FIRST_RUN_KEY_CHECKED = CHECKED  # 무료 등급을 공식 가격 페이지에서 확인한 날
# Ollama: 공식 다운로드 페이지. 크기와 시간은 이 PC에서 잰 값(docs/MODEL_EVAL.md, RTX 4070
# SUPER 그래픽 메모리 12GB): qwen3.8:27b 17.7GB, 불러오기 30초쯤, 첫 답 30초쯤
OLLAMA_PAGE = "https://ollama.com/download/windows"
OLLAMA_INSTALL = "irm https://ollama.com/install.ps1 | iex"
OLLAMA_NOTE = (
    "추천 모델 qwen3.8:27b는 내려받는 크기가 약 18GB입니다. 그래픽 메모리 12GB PC에서 "
    "불러오는 데 30초쯤, 초안 하나에 25~35초 걸렸습니다. 그래픽 카드가 작으면 더 느립니다."
)
