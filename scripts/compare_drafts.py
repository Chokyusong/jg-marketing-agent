"""초안 전후 비교(C1 다듬기에서 쓴 평가를 정리): 영상 맥락 × 초안 N개를 실제 AI로 만들어 표로.

    .\\.venv\\Scripts\\python.exe scripts\\compare_drafts.py --ai ollama --model qwen3.8:27b ^
        --fixtures EvalCtx0001,EvalCtx0002 --out-md out\\after.md --out-json out\\after.json
    .\\.venv\\Scripts\\python.exe scripts\\compare_drafts.py --ai ollama --db <앱 DB 사본> ^
        --videos m0c7g8q3OY8,EvalCtx0001 --before out\\before.json --out-md out\\compare.md

- 영상 맥락: `--fixtures`(tests/fixtures/contexts 의 가상 영상 이름, 가짜 YouTube로 넣는다)와
  `--videos`(`--db`로 준 DB 사본에 이미 저장된 실제 영상 맥락). 둘 다 쓰면 `--videos` 순서대로
  돈다(`--videos`에 없는 가상 영상은 뒤에 붙는다). YouTube·인터넷은 부르지 않는다.
- DB: `--db`를 주면 그 파일을 **임시 폴더로 복사해** 쓴다(원본은 읽기만, 분석·초안 표는 비운다).
  없으면 빈 임시 DB. 실제 DB 사본은 저장소에 넣지 않는다(결과 파일도 저장소 밖에 두는 것을 권한다).
- AI: `--ai`는 `config.yaml`의 `llm.providers` 이름(앱이 쓰는 `build_llm(settings)` 그대로 —
  `llm.active`를 그 이름으로 바꾼다). `--model`을 주면 그 AI의 모델을 바꾼다. 키가 필요한 AI는
  `llm.providers.<이름>.api_key_env`에 적힌 환경 변수로 읽는다(`--env-file`로 .env를 줄 수도
  있다). 키 값은 어디에도 찍지 않는다.
- 영상마다 처음 통과한 초안을 승인한다(다음 영상이 「이미 쓴 표현」·V11을 받는 실제 흐름).
- 결과: `--out-json`(초안 전문·시도별 글·다시 쓰기 까닭·시간)과 `--out-md`(초안마다 말 높임·들은
  경로·기분·알고 싶은 것과 갈래·요약 고민·댓글·AI 검수·다시 쓴 횟수와 까닭·최종 실패 + 지표:
  첫 시도 통과·첫 검수 통과·까닭별 수·갈래별 수·끝말 같은 것·운명원 소개 그대로 옮긴 것,
  docs/COMMENT_REFACTOR.md 7절). `--before`에 예전 결과 JSON을 주면 같은 영상끼리 나란히 놓는다.
- 2026-11-17: 결과 파일은 임시 폴더를 지우기 **전에** 쓴다. `--out-json`은 영상 하나가 끝날 때마다
  덮어써(`"finished": false`) 중간에 죽어도 그때까지의 결과가 남는다. DB 연결·서비스를 닫고
  나가며, 임시 폴더를 지우지 못하면(Windows에서 파일이 아직 잡혀 있을 때 등) 결과는 그대로 두고
  경고 한 줄만.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_drafts import CONTEXTS_DIR, load_contexts, prepare, youtube_transport  # noqa: E402

from app.analysis import review as rv  # noqa: E402
from app.analysis.drafter import mood_of, toggle_disclosure  # noqa: E402
from app.analysis.validator import quote_in_context  # noqa: E402
from app.api.deps import Services, build_services  # noqa: E402
from app.config import Settings, load_settings  # noqa: E402
from app.errors import AppError  # noqa: E402
from app.youtube.quota import utc_now  # noqa: E402

FAKE_YOUTUBE_KEY = "AIza" + "x" * 35  # 가짜 YouTube에만 쓰는 가짜 키(실행할 때 조립)


# ---------------------------------------------------------------- 설정


def make_settings(
    ai: str, db_path: Path, *, model: str = "", env_file: Path | None = None,
    timeout: float | None = None, environ: dict[str, str] | None = None, reasoning: str = "",
) -> Settings:
    """앱 설정(config.yaml)에서 글 쓰는 AI만 `ai`로 바꾼 설정.

    프로그램에 저장한 설정은 읽지 않는다(`use_user=False`).
    """
    env = dict(os.environ if environ is None else environ)
    env["YOUTUBE_API_KEY"] = FAKE_YOUTUBE_KEY
    base = load_settings(env_path=env_file, db_path=db_path, environ=env, use_user=False)
    llm = replace(base.llm, active=ai)
    provider = llm.providers.get(ai)
    if model:
        if provider is not None and provider.type == "ollama":
            llm = replace(llm, ollama_model=model)
        else:
            llm = replace(llm, models={**llm.models, ai: model})
    if timeout:
        llm = replace(llm, timeout_seconds=timeout)
    if reasoning:  # 추론 수준 비교(2026-11-18)
        llm = replace(llm, reasoning={**llm.reasoning, ai: reasoning})
    return replace(base, llm=llm)


# ---------------------------------------------------------------- 실행


def run(
    services: Services, order: Sequence[str], *, drafts_per_video: int = 2,
    titles: dict[str, str] | None = None, log=print,
    on_video: Callable[[list[dict[str, Any]]], None] | None = None,
    approve: bool = True,
) -> list[dict[str, Any]]:
    """영상마다 분석 1번 + 초안 N개. 처음 통과한 초안은 승인한다.

    `approve=False`(2026-11-17, `--no-approve`): 승인하지 않고 초안만 만든다. 대표가 실제로 쓰듯
    초안을 보기만 하고 게시하지 않을 때 꺼내는 말·끝말이 어떻게 흩어지는지 잰다.

    `on_video`: 영상 하나가 끝날 때마다(오류로 건너뛴 영상도) 그때까지의 목록으로 부른다.
    """
    videos: list[dict[str, Any]] = []
    for vid in order:
        row: dict[str, Any] = {"video_id": vid, "drafts": []}
        videos.append(row)
        try:
            ctx = services.context.current(vid)
            row["title"] = (titles or {}).get(vid) or ctx.video.video.title
            started = time.monotonic()
            analysis = services.drafts.analyze(vid)
        except AppError as exc:
            row["error"] = f"{exc.kind}: {exc.detail}"
            log(f"{vid} 분석 오류 {row['error']}")
            if on_video is not None:
                on_video(videos)
            continue
        row.update(
            analysis_s=round(time.monotonic() - started, 1), concern=analysis.concern,
            key_phrases=list(analysis.key_phrases or ()),
        )
        used: list[str] = []
        approved = False
        for n in range(1, drafts_per_video + 1):
            started = time.monotonic()
            try:
                d = services.drafts.generate(vid, avoid_quotes=tuple(used))
            except AppError as exc:
                row["drafts"].append({"n": n, "error": f"{exc.kind}: {exc.detail}"})
                continue
            used.append(d.evidence_quote)
            row["drafts"].append(draft_record(n, d, services.drafts.last_run,
                                              round(time.monotonic() - started, 1),
                                              disclosure=services.drafts.rules.disclosure))
            if approve and d.passed and not approved:
                try:
                    services.drafts.approve(d.id)
                    approved = True
                except AppError:
                    pass
        log(f"{vid}: 초안 {len(row['drafts'])}개")
        if on_video is not None:
            on_video(videos)
    return videos


def draft_record(
    n: int, d: Any, last_run: dict[str, Any], seconds: float, *, disclosure: str = "",
) -> dict[str, Any]:
    """초안 하나의 기록(2026-11-18 지시서 7절의 보고 칸). 글자 수는 V1처럼 표기를 뺀 본문."""
    review = d.review or {}
    tries = list(last_run.get("attempts") or [])
    rule_retries = [t.get("failures") or [] for t in tries[:-1]] if len(tries) > 1 else []
    return {
        "n": n, "body": d.body, "chars": len(toggle_disclosure(d.body, disclosure, False)),
        "passed": d.passed,
        "first_passed": d.first_passed, "attempts": d.attempts, "seconds": seconds,
        "quote": d.evidence_quote, "source": d.evidence_source,
        "voice": last_run.get("voice", ""), "heard": last_run.get("heard", ""),
        "mood": mood_of(d.tone_label), "tone": d.tone_label,
        "wish": d.wish, "wish_kind": review.get("wish_kind", ""),
        "failures": d.validation.failure_lines(),
        "review": d.review_status, "review_problems": list(review.get("problems") or []),
        "review_first": list(review.get("first") or []),
        "review_before": d.review_before, "review_after": d.review_after,
        "review_kept": review.get("kept"),
        "review_ms": d.review_ms, "rewrite_ms": d.rewrite_ms,
        # 규칙 검사로 다시 쓴 까닭(시도마다 걸린 항목). AI 검수의 까닭은 review_first
        "retry_reasons": rule_retries,
        "run": json.loads(json.dumps(last_run, ensure_ascii=False)),
    }


# ---------------------------------------------------------------- 표


def _esc(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _drafts(videos: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for v in videos for x in v.get("drafts", []) if x.get("body")]


def _cell(x: dict[str, Any] | None) -> str:
    if not x:
        return "—"
    if not x.get("body"):
        return f"오류: {_esc(x.get('error', ''))}"
    mark = "통과" if x.get("passed") else "실패"
    return f"{_esc(x['body'])} ({x['chars']}자 · {mark} · {x.get('attempts', '?')}번째)"


def ending(body: str, disclosure: str = "[광고]") -> str:
    """끝말: 본문의 마지막 어절 둘(문장부호·ㅋㅋ·ㅠㅠ 꼬리는 뺀다)."""
    text = body.strip()
    if disclosure and text.startswith(disclosure):
        text = text[len(disclosure):]
    words = text.rstrip(" .!?…~ㅋㅎㅠㅜ").split()
    return " ".join(words[-2:])


def fact_copied(body: str, facts: Sequence[str]) -> bool:
    """운명원 소개 문장(brand.facts)을 거의 그대로 옮겼는가(85% 이상 비슷한 구간)."""
    return any(f and quote_in_context(f, body) for f in facts)


def _reason_counts(ds: Sequence[dict[str, Any]]) -> Counter[str]:
    reasons: Counter[str] = Counter()
    for x in ds:
        for retry in x.get("retry_reasons", []):
            reasons.update((r.split(":", 1)[0].split() or ["?"])[0] for r in retry)  # 검사 번호
        if x.get("review_first"):
            reasons["AI 검수"] += 1
    return reasons


def _stats(videos: Sequence[dict[str, Any]], facts: Sequence[str] = ()) -> dict[str, str]:
    ds = _drafts(videos)
    n = len(ds)
    if not n:
        return {}
    chars = [x["chars"] for x in ds]
    attempts = Counter(x.get("attempts", 0) for x in ds)
    status = Counter(x.get("review", "") for x in ds)
    ends = Counter(ending(x["body"]) for x in ds)
    out = {
        "규칙 검사 최종 통과": f"{sum(bool(x.get('passed')) for x in ds)}/{n}",
        "첫 시도 규칙 검사 통과": f"{sum(bool(x.get('first_passed')) for x in ds)}/{n}",
        "시도 1·2·3번": " · ".join(str(attempts.get(i, 0)) for i in (1, 2, 3)),
        "글자 수 범위(평균)": f"{min(chars)}~{max(chars)}자({sum(chars) / n:.0f})",
        "초안 1개 평균 시간": f"{sum(x.get('seconds', 0) for x in ds) / n:.1f}초",
        "첫 검수 통과": f"{status[rv.PASSED]}/{n}",
        "검수 고쳐 써서 통과 · 고쳐도 남음 · 못 함":
            f"{status[rv.REWRITTEN]} · {status[rv.FLAGGED]} · {status[rv.ERROR]}",
        "다시 쓴 글 버림(앞 초안 씀)":
            str(sum(1 for x in ds if x.get("review_after") and x.get("review_kept") is False)),
        "끝말이 글자까지 같은 초안": str(sum(c for c in ends.values() if c > 1)),
        "운명원 소개를 거의 그대로 옮김": str(sum(fact_copied(x["body"], facts) for x in ds)),
    }
    kinds = Counter(x.get("wish_kind") or "(검수 안 함)" for x in ds)
    out["알고 싶은 것 갈래"] = ", ".join(f"{k} {c}" for k, c in kinds.most_common())
    voices = Counter(x.get("voice") or "?" for x in ds)
    out["말 높임"] = ", ".join(f"{k} {c}" for k, c in voices.most_common())
    heard = Counter(x.get("heard") or "?" for x in ds)
    out["들은 경로"] = ", ".join(f"{k} {c}" for k, c in heard.most_common())
    reasons = _reason_counts(ds)
    out["다시 쓰게 만든 까닭"] = ", ".join(f"{k} {c}" for k, c in reasons.most_common()) or "없음"
    return out


def detail_lines(videos: Sequence[dict[str, Any]]) -> list[str]:
    """초안마다: 말 높임 · 들은 경로 · 기분 · 알고 싶은 것(갈래) · 영상 · 고민 · 댓글 · 검수 ·
    다시 쓴 횟수와 까닭 · 최종 실패."""
    rows = ["| 영상 | # | 말 높임 · 들은 경로 · 기분 | 알고 싶은 것(갈래) | 요약 고민 | 댓글 | "
            "AI 검수 | 다시 쓴 횟수 · 까닭 | 최종 실패 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for v in videos:
        title = _esc(v.get("title") or v.get("video_id", ""))[:30]
        if v.get("error"):
            rows.append(f"| {title} | — | | | | 분석 오류: {_esc(v['error'])} | | | |")
            continue
        for x in v.get("drafts", []):
            if not x.get("body"):
                rows.append(f"| {title} | {x.get('n')} | | | | 오류: {_esc(x.get('error', ''))}"
                            " | | | |")
                continue
            why = [" / ".join(r) for r in x.get("retry_reasons", [])]
            if x.get("review_first"):
                why.append("AI 검수: " + " / ".join(x["review_first"]))
            rewrites = max(0, int(x.get("attempts", 1) or 1) - 1)
            review = rv.label(x.get("review", "")) or x.get("review", "") or "—"
            if x.get("review_problems"):
                review += " — " + " / ".join(x["review_problems"])
            rows.append(
                f"| {title} | {x.get('n')} | {_esc(x.get('voice', ''))} · "
                f"{_esc(x.get('heard', ''))} · {_esc(x.get('mood', ''))} | "
                f"{_esc(x.get('wish', ''))} ({_esc(x.get('wish_kind', '') or '—')}) | "
                f"{_esc(v.get('concern', ''))} | {_esc(x['body'])} ({x['chars']}자) | "
                f"{_esc(review)} | {rewrites}번 · {_esc('; '.join(why)) or '—'} | "
                f"{_esc(' / '.join(x.get('failures') or [])) or '없음'} |")
    return rows


def markdown_table(
    after: Sequence[dict[str, Any]], *, before: Sequence[dict[str, Any]] | None = None,
    labels: tuple[str, str] = ("전", "후"), brand: str = "운명원", disclosure: str = "[광고]",
    facts: Sequence[str] = (),
) -> str:
    """초안별 상세 표 + 지표(Markdown). `before`가 있으면 같은 영상끼리 나란히 놓은 표를 더한다."""
    del brand, disclosure
    lines = detail_lines(after)
    sides = [before, after] if before is not None else [after]
    names = list(labels) if before is not None else [labels[1]]
    stats = [_stats(s or [], facts) for s in sides]
    keys = list(dict.fromkeys(k for s in stats for k in s))
    lines += ["", "| 지표 | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(_esc(s.get(k, "—")) for s in stats) + " |")
    if before is not None:
        old = {v["video_id"]: v for v in before}
        width = max([len(v.get("drafts", [])) for v in [*after, *before]] or [0])
        lines += ["", f"| 영상 | # | {labels[0]} | {labels[1]} |", "|---|---|---|---|"]
        for v in after:
            title = _esc(v.get("title") or v["video_id"])[:40]
            theirs = old.get(v["video_id"], {}).get("drafts", [])
            for i in range(width):
                mine = v["drafts"][i] if i < len(v.get("drafts", [])) else None
                lines.append(f"| {title if i == 0 else ''} | {i + 1} | "
                             f"{_cell(theirs[i] if i < len(theirs) else None)} | {_cell(mine)} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 진입점


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--ai", required=True, help="config.yaml llm.providers의 이름(예: ollama)")
    p.add_argument("--model", default="", help="그 AI에 쓸 모델(비우면 설정 그대로)")
    p.add_argument("--fixtures", default="", help="가상 영상 이름들(쉼표), 'all'이면 전부")
    p.add_argument("--fixtures-dir", type=Path, default=CONTEXTS_DIR)
    p.add_argument("--videos", default="", help="DB 사본에 저장된 영상 ID들(쉼표, 순서대로 돈다)")
    p.add_argument("--db", type=Path, default=None, help="앱 DB 사본(임시 폴더로 복사해 쓴다)")
    p.add_argument("-d", "--drafts", type=int, default=2, help="영상마다 초안 수")
    p.add_argument("--no-approve", action="store_true",
                   help="처음 통과한 초안도 승인하지 않는다(보기만 하는 실제 쓰임)")
    p.add_argument("--before", type=Path, default=None, help="비교할 예전 결과 JSON")
    p.add_argument("--labels", default="전,후", help="표 열 이름 두 개(쉼표)")
    p.add_argument("--out-json", type=Path, default=None)
    p.add_argument("--out-md", type=Path, default=None)
    p.add_argument("--env-file", type=Path, default=None, help="키를 읽을 .env(값은 찍지 않는다)")
    p.add_argument("--timeout", type=float, default=600.0, help="AI 한 번 기다리는 초")
    p.add_argument("--reasoning", default="", help="Codex 추론 수준(low·medium·high, 비우면 설정)")
    args = p.parse_args(argv)
    if not args.fixtures and not args.videos:
        p.error("--fixtures나 --videos 중 하나는 있어야 합니다")
    if args.videos and args.db is None:
        p.error("--videos는 그 영상 맥락이 저장된 --db(DB 사본)와 함께 씁니다")
    return args


def _split(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def write_json(path: Path | None, out: dict[str, Any]) -> None:
    """결과 JSON을 덮어쓴다(옆 파일에 쓴 뒤 바꿔 넣어, 쓰다가 죽어도 앞 결과가 깨지지 않게)."""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(part, path)


def remove_temp(path: Path) -> None:
    """임시 폴더를 지운다. 못 지워도 결과는 이미 썼으니 경고 한 줄만(Windows WinError 32 등)."""
    try:
        shutil.rmtree(path)
    except OSError as exc:
        print(f"경고: 임시 폴더를 지우지 못했습니다(결과 파일은 이미 썼습니다): {path} "
              f"({type(exc).__name__})", file=sys.stderr)


def _copy_db(src: Path, dst: Path) -> None:
    """DB 사본을 임시 폴더로 복사하고 분석·초안 표를 비운다(연결은 닫고 나온다)."""
    shutil.copy(src, dst)
    # `with sqlite3.connect()`는 커밋만 하고 닫지 않는다 → 닫지 않으면 Windows에서 파일이 잡혀 있다
    with contextlib.closing(sqlite3.connect(dst)) as conn, conn:
        conn.execute("DELETE FROM drafts")
        conn.execute("DELETE FROM analyses")


def _compare(
    args: argparse.Namespace, out: dict[str, Any], fixtures: list[dict[str, Any]],
    order: list[str], labels: tuple[str, str], tmp: Path,
) -> str:
    """임시 폴더 안에서 돌리고, 나가기 전에 결과 파일을 쓴다. 돌려주는 것은 표(Markdown)."""
    db_path = tmp / "compare.sqlite3"
    if args.db is not None:
        _copy_db(args.db, db_path)
    settings = make_settings(args.ai, db_path, model=args.model, env_file=args.env_file,
                             timeout=args.timeout, reasoning=args.reasoning)
    services = build_services(settings, transport=youtube_transport(fixtures), clock=utc_now)

    def save(videos: list[dict[str, Any]]) -> None:
        out["videos"] = videos
        write_json(args.out_json, out)

    try:
        llm = services.require_llm()
        out["model"] = str(getattr(llm, "model", "") or args.model)
        if getattr(llm, "reasoning", ""):  # 2026-11-18 Codex 추론 수준(명령줄로 준 값)
            out["reasoning"] = str(llm.reasoning)
        warmup = getattr(llm, "warmup", None)
        if callable(warmup):
            started = time.monotonic()
            warmup()
            out["load_s"] = round(time.monotonic() - started, 1)
        prepare(services, fixtures)
        titles = {c["video_id"]: c.get("title", "") for c in fixtures}
        out["approve"] = not args.no_approve
        out["videos"] = run(services, order, drafts_per_video=args.drafts, titles=titles,
                            on_video=save, approve=not args.no_approve)
        rules = services.drafts.rules
        out["finished"] = True
        write_json(args.out_json, out)
        before = None
        if args.before:
            before = json.loads(args.before.read_text(encoding="utf-8")).get("videos", [])
        table = markdown_table(out["videos"], before=before, labels=labels, brand=rules.brand,
                               disclosure=rules.disclosure,
                               facts=services.drafts.brand_facts)
        if args.out_md:
            args.out_md.parent.mkdir(parents=True, exist_ok=True)
            args.out_md.write_text(table, encoding="utf-8")
        return table
    finally:
        unload = getattr(services.llm, "unload", None)
        if callable(unload):
            try:
                unload()
            except Exception:  # noqa: BLE001 — 내리지 못해도 결과는 남긴다
                pass
        services.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    fixtures = load_contexts(args.fixtures_dir)
    if args.fixtures != "all":
        wanted = set(_split(args.fixtures))
        fixtures = [c for c in fixtures if c["video_id"] in wanted]
    order = _split(args.videos)
    order += [c["video_id"] for c in fixtures if c["video_id"] not in order]
    names = (_split(args.labels) + ["전", "후"])[:2]
    labels = (names[0], names[1])
    out: dict[str, Any] = {"ai": args.ai, "model": args.model, "finished": False, "videos": []}
    tmp = Path(tempfile.mkdtemp(prefix="jg-compare-"))
    try:
        table = _compare(args, out, fixtures, order, labels, tmp)
    finally:
        remove_temp(tmp)
    sys.stdout.write(table)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    raise SystemExit(main())
