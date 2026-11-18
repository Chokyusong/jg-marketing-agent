"""맥락 검수 회귀 사례(2026-11-18 대표): 정해 둔 초안을 **실제 검수 AI**에 돌려 통과/걸림이 기대와
같은지 표로 본다.

    .\\.venv\\Scripts\\python.exe scripts\\review_cases.py --db <앱 DB 사본> ^
        --ai codex-cli --model gpt-6.1-terra --reasoning medium --out-md out\\cases.md

- 사례: `tests/fixtures/story_review_cases.json`(초안 본문 · 영상 ID · 고민 한 줄 · 핵심 말 · 근거
  구절 · 기대 pass/flag). 대표가 읽고 정한 것이다.
- 영상 자료(자막·설명·인기 댓글)는 저장소에 넣지 않는다. `--db`로 준 앱 DB 사본을 **임시 폴더로
  복사해** 읽기만 한다(원본은 건드리지 않는다). 검수 AI가 받는 글은 앱과 같다
  (`review.review_system(story=True)` · `review.review_user(story=True, material=…)`).
- 진짜 AI를 부른다(사례 하나에 한 번). 자동 테스트는 이 스크립트를 가짜 검수로만 돌린다
  (`tests/unit/test_review_cases.py`). 키 값은 어디에도 찍지 않는다.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from compare_drafts import make_settings  # noqa: E402
from eval_drafts import youtube_transport  # noqa: E402

from app.analysis import review as rv  # noqa: E402
from app.api.deps import Services, build_services  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.llm import story_prompts as sp  # noqa: E402
from app.youtube.quota import utc_now  # noqa: E402

CASES = ROOT / "tests" / "fixtures" / "story_review_cases.json"
EXPECT = ("pass", "flag")


def load_cases(path: Path = CASES) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for case in data["cases"]:
        if case.get("expect") not in EXPECT:
            raise ValueError(f"{case.get('case')}: expect는 pass 또는 flag")
    return data


def review_one(services: Services, case: dict[str, Any], *, brand: str,
               ask: Callable[..., Any] = rv.ask) -> dict[str, Any]:
    """사례 하나를 앱과 같은 글로 검수한다. 돌려주는 것: 결과 한 줄(판정·까닭·시간)."""
    vid = case["video_id"]
    ctx = services.context.current(vid)
    title = ctx.video.video.title
    material = sp.material(
        title=title, description=ctx.video.video.description or "",
        transcript=ctx.transcript_text or "", comments=[c.text for c in ctx.comments],
    )
    user = rv.review_user(
        body=case["body"], title=title, concern=case.get("concern", ""),
        key_phrases=case.get("key_phrases", []), evidence=case.get("evidence", ""),
        story=True, thin=not ctx.transcript_text, material=material,
    )
    started = time.monotonic()
    row: dict[str, Any] = {"case": case["case"], "expect": case["expect"], "body": case["body"]}
    try:
        verdict = ask(services.require_llm(), system=rv.review_system(brand=brand, story=True),
                      user=user, story=True)
    except (AppError, ValueError) as exc:
        row.update(got="error", error=str(getattr(exc, "message", exc)))
    else:
        ok, problems = verdict
        checks = getattr(verdict, "checks", {})
        row.update(got="pass" if ok else "flag", problems=list(problems),
                   same_topic=checks.get("same_topic"), flow=checks.get("flow"),
                   natural_ad=checks.get("natural_ad"), link_reason=checks.get("link_reason", ""),
                   break_at=checks.get("break_at", ""))
    row["seconds"] = round(time.monotonic() - started, 1)
    row["match"] = row["got"] == case["expect"]
    return row


def table(rows: list[dict[str, Any]], *, label: str = "") -> str:
    lines = [f"### {label}" if label else "", "",
             "| 사례 | 기대 | 결과 | 맞음 | same_topic | flow | natural_ad | link_reason "
             "| break_at |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [r["case"], r["expect"], r["got"], "○" if r["match"] else "✗",
                 str(r.get("same_topic")), str(r.get("flow")), str(r.get("natural_ad")),
                 (r.get("link_reason") or "").replace("|", "／"),
                 (r.get("break_at") or r.get("error") or "").replace("|", "／")]
        lines.append("| " + " | ".join(cells) + " |")
    hit = sum(r["match"] for r in rows)
    lines += ["", f"기대대로 {hit}/{len(rows)}"]
    return "\n".join(lines).lstrip("\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, required=True, help="앱 DB 사본(읽기만, 임시 폴더로 복사)")
    ap.add_argument("--ai", required=True)
    ap.add_argument("--model", default="")
    ap.add_argument("--reasoning", default="")
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--cases", type=Path, default=CASES)
    ap.add_argument("--label", default="")
    ap.add_argument("--out-md", type=Path, default=None)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args(argv)
    data = load_cases(args.cases)
    tmp = Path(tempfile.mkdtemp(prefix="jg-review-cases-"))
    rows: list[dict[str, Any]] = []
    try:
        db_path = tmp / "cases.sqlite3"
        shutil.copyfile(args.db, db_path)
        settings = make_settings(args.ai, db_path, model=args.model, env_file=args.env_file,
                                 reasoning=args.reasoning)
        services = build_services(settings, transport=youtube_transport([]), clock=utc_now)
        try:
            for case in data["cases"]:
                row = review_one(services, case, brand=data.get("brand", "운명원"))
                rows.append(row)
                print(f"{row['case']}: 기대 {row['expect']} · 결과 {row['got']} "
                      f"({row['seconds']}초){'' if row['match'] else ' ✗'}", flush=True)
        finally:
            services.close()
    finally:
        with contextlib.suppress(OSError):
            shutil.rmtree(tmp)
    md = table(rows, label=args.label)
    print(md)
    if args.out_md:
        args.out_md.write_text(md + "\n", encoding="utf-8")
    if args.out_json:
        args.out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if all(r["match"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
