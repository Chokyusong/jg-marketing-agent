"""R5 진짜 확인(RUN_LIVE=1일 때만): 로그인된 프로그램(Codex · Claude Code)을 이 앱과 같은 방식으로
한 번 실행해 JSON 답이 오는지 본다.

- 영상 자료가 아니라 짧은 시험 문장만 보낸다. 대표의 구독 계정을 쓰므로 횟수를 최소로(JSON이
  어긋나면 공통 규칙대로 한 번 더 — 프로그램당 최대 2번).
- 실행 조건은 앱과 같다(빈 임시 폴더 · 도구 끔/읽기 전용 · 비대화 · 표준 입력 · 셸 없음 · 창 없음 ·
  시간 제한). 그 프로그램의 로그인 파일은 읽지 않는다.
- 설치되지 않았으면 건너뛴다. 로그인돼 있지 않으면 그 오류(llm_auth)를 그대로 보여 주고 실패한다.
"""

from __future__ import annotations

import shutil
import time

import pytest

from app.errors import AppError
from app.llm import cli

pytestmark = pytest.mark.live

SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "mood": {"type": "string"}},
    "required": ["summary", "mood"],
}
SYSTEM = "짧은 시험 요청입니다. 정해진 모양으로만 답합니다."
USER = (
    "다음 문장을 열 글자 안쪽으로 요약하고, 분위기를 한 낱말로 적으세요: "
    "'오늘은 하늘이 맑아서 산책하기 좋다.'"
)


@pytest.mark.parametrize(("program", "label"), [("codex", "Codex"), ("claude", "Claude Code")])
def test_cli_answers_json(program, label):
    if shutil.which(program) is None:
        pytest.skip(f"{label}이(가) 이 PC에 설치돼 있지 않음")
    calls: list[cli.RunRequest] = []

    def runner(req: cli.RunRequest) -> cli.RunResult:
        calls.append(req)
        return cli.subprocess_runner(req)

    client = cli.CLIClient(
        provider=f"{program}-cli",
        label=label,
        program=program,
        timeout_seconds=240,
        hidden_env=(
            "YOUTUBE_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "XAI_API_KEY",
            "CUSTOM_LLM_API_KEY",
        ),
        runner=runner,
        which=shutil.which,  # 진짜 실행(자동 테스트의 막음을 이 테스트만 푼다)
    )
    started = time.monotonic()
    try:
        out = client.generate_json(system=SYSTEM, user=USER, schema=SCHEMA)
    except AppError as exc:
        pytest.fail(f"{label}: {exc.kind} · {exc.message} · {exc.detail}")
    finally:
        runs = [c for c in calls if c.args[1:] != ["--version"]]
        print(f"\n{label}: 실행 {len(runs)}번 · {time.monotonic() - started:.1f}초")
    print(f"{label} 답: {out}")
    assert isinstance(out["summary"], str) and out["summary"]
    assert isinstance(out["mood"], str) and out["mood"]
    assert 1 <= len(runs) <= 2
    for req in runs:
        assert USER not in " ".join(req.args) and USER in req.input_text
