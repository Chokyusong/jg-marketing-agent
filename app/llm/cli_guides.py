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
- Gemini(명령줄 프로그램) — https://github.com/google-gemini/gemini-cli 와
  developers.googleblog.com 공지(2026-05-19): 2026-06-18부터 개인 무료 계정(Google AI
  Pro/Ultra·개인용 Code Assist)으로는 쓸 수 없다. 로그인 상태를 묻는 명령도 문서에 없다
  (https://geminicli.com/docs/get-started/authentication/). 뒤를 잇는 Antigravity CLI
  (`agy`, https://antigravity.google/docs/cli/headless/)는 표준 입력을
  `--input-format stream-json`에서만 받고, 공식 저장소에 「-p가 파일 쓰기를 자동 승인」
  이슈가 있다. 이 앱의 안전 조건(프롬프트는 표준 입력, 쓰기·명령 도구 끔)을 확인하지
  못했다 → **둘 다 물리지 않는다.**

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
        "Antigravity 앱과는 다른 프로그램입니다. 같은 구글 계정으로 로그인합니다.",
        "구글이 2026년 6월 18일부터 개인 무료 계정으로는 이 프로그램을 쓸 수 없게 "
        "했습니다(공식 공지, 2026-11-17 확인).",
        "뒤를 잇는 프로그램은 영상 자료를 안전하게 넘기는 방법(파일 쓰기·명령 실행 끔)을 "
        "공식 문서로 확인하지 못해 연결하지 않았습니다.",
        "구글 AI를 쓰려면 「Gemini(Google)」를 고르고 Google AI Studio에서 받은 API 키를 "
        "넣으세요(무료 등급이 있습니다).",
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
# Ollama: 공식 다운로드 페이지. 크기와 시간은 이 PC에서 잰 값(docs/MODEL_EVAL.md, RTX 4070
# SUPER 그래픽 메모리 12GB): qwen3.8:27b 17.7GB, 불러오기 30초쯤, 첫 답 30초쯤
OLLAMA_PAGE = "https://ollama.com/download/windows"
OLLAMA_INSTALL = "irm https://ollama.com/install.ps1 | iex"
OLLAMA_NOTE = (
    "추천 모델 qwen3.8:27b는 내려받는 크기가 약 18GB입니다. 그래픽 메모리 12GB PC에서 "
    "불러오는 데 30초쯤, 초안 하나에 25~35초 걸렸습니다. 그래픽 카드가 작으면 더 느립니다."
)
