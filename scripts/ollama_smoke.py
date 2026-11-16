"""설치된 일반 모델마다 한국어 JSON을 한 번씩 시켜 성공 여부와 걸린 시간을 표로 보여 준다(4단계).

    .\\.venv\\Scripts\\python.exe scripts\\ollama_smoke.py
    .\\.venv\\Scripts\\python.exe scripts\\ollama_smoke.py --timeout 300 --models qwen2.5:7b

- 대상: `/api/tags`의 모델 중 코드용(이름에 `-code`)과 글을 못 쓰는 모델(capabilities에
  completion 없음)을 뺀 것. `--models`로 직접 고를 수 있다.
- 모델마다: 불러오기(`warmup`) → 같은 질문 두 번(첫 답 · 두 번째 답). 끝나면 모델을 내린다
  (`keep_alive: 0`) — 12GB 그래픽 메모리에 큰 모델 둘이 같이 올라가지 않게.
- 시간 제한은 요청 하나마다 `--timeout`초(기본 300). 시간 초과도 결과로 적는다.
- 품질 비교(초안 규칙 통과율)는 5단계 `scripts/eval_drafts.py`가 한다.
  여기서는 "JSON 통로가 되는가"만 본다.
- Ollama 공급자만 시험하는 스크립트라 `app.llm.ollama`를 직접 쓴다(앱 코드는 등록부만 쓴다).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.llm.ollama import OllamaClient  # noqa: E402

CONTEXT = (
    "영상 제목: 연락이 줄어든 애인, 마음이 식은 걸까요?\n"
    "자막: 요즘 애인이 답장을 하루에 한 번만 해요. "
    "예전에는 자기 전에 꼭 전화했는데 이제는 바쁘다는 말만 해요. "
    "제가 너무 집착하는 건지, 아니면 정말 마음이 식은 건지 모르겠어요.\n"
    "인기 댓글: 저도 똑같은 상황이라 너무 공감돼요 / 바쁠 때는 연락이 줄 수 있어요"
)
SYSTEM = (
    "너는 유튜브 영상의 맥락을 정리하는 한국어 도우미다. 주어진 자료에 있는 내용만 쓴다. "
    "반드시 JSON 객체 하나로만 답한다."
)
USER = (
    "다음 영상 자료를 읽고 시청자의 고민을 한 문장으로 정리하고, 그 근거가 되는 문장을 자료에서 "
    "그대로 하나 골라라.\n\n" + CONTEXT
)
SCHEMA = {
    "type": "object",
    "properties": {
        "concern": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["concern", "quote"],
}
HANGUL = re.compile(r"[가-힣]")


@dataclass
class Result:
    model: str
    size_gb: float
    thinking: bool  # 생각 기능이 있어 think:false를 실었는가
    load_s: float | None = None
    first_s: float | None = None
    second_s: float | None = None
    ok: bool = False
    korean: bool = False
    quote_in_context: bool = False
    concern: str = ""
    error: str = ""
    notes: list[str] = field(default_factory=list)


def is_general(model: dict) -> bool:
    name = str(model.get("name") or "")
    caps = model.get("capabilities")
    if "-code" in name:
        return False
    return caps is None or "completion" in caps


def list_models(base_url: str) -> list[dict]:
    res = httpx.get(f"{base_url}/api/tags", timeout=10)
    res.raise_for_status()
    return res.json().get("models") or []


def unload_all(base_url: str) -> None:
    """돌고 있는 모델을 내려 같은 조건(차가운 상태)에서 시작한다."""
    res = httpx.get(f"{base_url}/api/ps", timeout=10)
    for m in res.json().get("models") or []:
        httpx.post(
            f"{base_url}/api/chat",
            json={"model": m["name"], "messages": [], "stream": False, "keep_alive": 0},
            timeout=60,
        )


def timed(fn):
    started = time.monotonic()
    value = fn()
    return value, round(time.monotonic() - started, 1)


def run_model(name: str, size: int, *, base_url: str, timeout: float, num_ctx: int) -> Result:
    client = OllamaClient(
        model=name, base_url=base_url, timeout_seconds=timeout, num_ctx=num_ctx, keep_alive="5m"
    )
    result = Result(model=name, size_gb=round(size / 1e9, 1), thinking=False)
    try:
        result.thinking = client.think_option() is False
        _, result.load_s = timed(client.warmup)
        data, result.first_s = timed(
            lambda: client.generate_json(
                system=SYSTEM, user=USER, schema=SCHEMA, temperature=0.2, max_tokens=300
            )
        )
        _, result.second_s = timed(
            lambda: client.generate_json(
                system=SYSTEM, user=USER, schema=SCHEMA, temperature=0.2, max_tokens=300
            )
        )
        result.ok = True
        result.concern = str(data.get("concern", ""))
        result.korean = bool(HANGUL.search(result.concern))
        quote = str(data.get("quote", "")).strip()
        result.quote_in_context = bool(quote) and quote in CONTEXT
    except AppError as exc:
        result.error = f"{exc.kind}: {exc.message}"
    finally:
        try:
            client.unload()
        except AppError:
            result.notes.append("내리기 실패")
        client.close()
    return result


def fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.1f}"


def markdown(results: list[Result], *, timeout: float) -> str:
    lines = [
        f"시간 제한: 요청마다 {timeout:.0f}초. 시간 단위: 초. "
        "불러오기 = 차가운 상태에서 모델을 메모리에 올리는 시간.",
        "",
        "| 모델 | 크기 | 생각 끄기 | 불러오기 | 첫 답 | 두 번째 답 | JSON | 한국어 "
        "| 근거가 자료에 있음 | 결과 / 고민 한 줄 |",
        "|---|---:|---|---:|---:|---:|---|---|---|---|",
    ]
    for r in results:
        mark = lambda b: "예" if b else "아니오"  # noqa: E731
        tail = r.concern if r.ok else r.error
        lines.append(
            f"| `{r.model}` | {r.size_gb}GB | {'think:false' if r.thinking else '해당 없음'} | "
            f"{fmt(r.load_s)} | {fmt(r.first_s)} | {fmt(r.second_s)} | {mark(r.ok)} | "
            f"{mark(r.korean) if r.ok else '–'} | {mark(r.quote_in_context) if r.ok else '–'} | "
            f"{tail.replace('|', '/')} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=settings.llm.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=300.0, help="요청 하나의 시간 제한(초)")
    parser.add_argument("--num-ctx", type=int, default=settings.llm.num_ctx)
    parser.add_argument(
        "--models", nargs="*", help="직접 고른 모델 이름(없으면 설치된 일반 모델 전부)"
    )
    parser.add_argument("--json-out", type=Path, help="결과를 JSON으로도 저장할 경로")
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        installed = list_models(base)
    except httpx.HTTPError as exc:
        name = type(exc).__name__
        print(f"Ollama에 연결하지 못했습니다({name}). `ollama serve`를 확인해 주세요.")
        return 2
    sizes = {m["name"]: int(m.get("size") or 0) for m in installed}
    targets = args.models or [m["name"] for m in installed if is_general(m)]
    skipped = [m["name"] for m in installed if m["name"] not in targets]
    print(f"Ollama {base} · 대상 {len(targets)}개: {', '.join(targets)}")
    if skipped:
        print(f"뺀 모델: {', '.join(skipped)}")
    unload_all(base)

    results = []
    for name in targets:
        print(f"- {name} ...", flush=True)
        result = run_model(
            name, sizes.get(name, 0), base_url=base, timeout=args.timeout, num_ctx=args.num_ctx
        )
        status = "성공" if result.ok else f"실패 ({result.error})"
        times = f"불러오기 {fmt(result.load_s)}s · 첫 답 {fmt(result.first_s)}s"
        print(f"  {status} · {times}", flush=True)
        results.append(result)

    print()
    print(markdown(results, timeout=args.timeout))
    if args.json_out:
        args.json_out.write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
