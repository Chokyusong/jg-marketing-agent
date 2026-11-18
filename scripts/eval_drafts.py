"""모델 비교(5단계): 가상 영상 맥락마다 초안을 만들어 규칙 통과율·시간·초안 원문을 표로 보여 준다.

    .\\.venv\\Scripts\\python.exe scripts\\eval_drafts.py
    .\\.venv\\Scripts\\python.exe scripts\\eval_drafts.py --models qwen2.5:7b --contexts 3 -d 2

- 맥락: `tests/fixtures/contexts/*.json`(직접 쓴 가상 영상 6개: 연애 주제 5개 + 협찬 위주 1개).
  가짜 YouTube 응답으로 바꿔
  앱의 실제 흐름(`DraftService`: 맥락 → 분석 → 근거 고르기 → 본문 → 규칙 검사 → 최대 3번)에 넣는다.
  YouTube·인터넷은 부르지 않는다. 임시 DB를 쓴다(앱 DB를 건드리지 않는다).
- 영상마다 초안 N개: 첫 초안 다음부터는 [다른 초안 생성]처럼 이미 쓴 근거를 피한다.
- 모델을 하나씩 올리고 내린다(그래픽 메모리 12GB에 큰 모델 둘이 같이 올라가지 않게).
  불러오기와 불러온 직후 첫 답은 따로 잰다(시연 전에 불러 두기로 숨길 수 있는 시간).
- 표: 첫 시도 통과율, 3번 안 통과율, 초안 하나 평균 시간, 초안 원문.
- `--approve-first`: 영상마다 처음 통과한 초안을 승인한다(사람이 영상마다 하나씩 승인하는 흐름).
  그러면 다음 영상의 초안은 그 권유 문장을 「이미 쓴 표현」으로 받고 V11 비교도 한다.
- 권유 문장 다양성: 브랜드가 든 마지막 문장(`closing_sentence`)이 서로 다른 개수,
  「흐름이 궁금하다면」 같은 굳은 틀이 든 개수, V12(한자·일본어·이모지)에 걸린 초안 수를 센다.
- 실제 데이터 보정: 맥락의 `foreign_products`(남의 상품 이름)가 초안에 들어갔는지 센다
  (「남의 상품 권함」). 분석이 「연애 고민을 찾지 못했습니다」(`no_love_concern`)로 멈춘 것은
  오류가 아니라 「멈춤」으로 따로 센다.
  표 아래에 맥락마다 결과(핵심 고민 또는 연애 고민 없음 · 통과 수 · 남의 상품 권함)를 붙인다.
- Ollama 공급자만 시험하는 스크립트라 `app.llm.ollama`를 직접 쓴다(앱 코드는 등록부만 쓴다).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api.deps import Services, build_services  # noqa: E402
from app.config import Settings, load_settings  # noqa: E402
from app.errors import AppError, ErrorKind  # noqa: E402
from app.youtube.quota import utc_now  # noqa: E402

CONTEXTS_DIR = ROOT / "tests" / "fixtures" / "contexts"
DEFAULT_MODELS = ("qwen2.5:7b", "qwen3.8:27b", "qwen3.6:latest")
# 5단계 첫 비교에서 qwen3.8:27b 초안 15개 대부분이 되풀이한 권유 틀(5단계 점검)
STOCK_CLOSINGS = ("흐름이 궁금", "흐름을 짚어", "흐름을 확인", "흐름을 살펴")


def closing_sentence(body: str, *, brand: str, disclosure: str = "") -> str:
    """브랜드가 든 마지막 문장(없으면 마지막 문장). 2026-11-18 댓글 리팩토링으로 프롬프트 모듈에서
    옮겨 왔다(이 스크립트의 집계에만 쓴다)."""
    text = body.strip()
    if disclosure and text.startswith(disclosure):
        text = text[len(disclosure):].strip()
    parts = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", text) if x.strip()]
    with_brand = [x for x in parts if brand in x]
    return (with_brand or parts or [""])[-1]


# ---------------------------------------------------------------- 가상 맥락 → 가짜 YouTube


def load_contexts(directory: Path = CONTEXTS_DIR, limit: int | None = None) -> list[dict[str, Any]]:
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]
    return items[:limit] if limit else items


def _video_item(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "youtube#video",
        "id": ctx["video_id"],
        "snippet": {
            "publishedAt": ctx.get("published_at", "2026-11-10T00:00:00Z"),
            "channelId": "UCevalchannel0000000000000",
            "title": ctx["title"],
            "description": ctx.get("description", ""),
            "thumbnails": {},
            "channelTitle": ctx.get("channel_title", ""),
        },
        "contentDetails": {"duration": "PT8M0S"},
        "statistics": {"viewCount": "3000", "likeCount": "100", "commentCount": "40"},
    }


def _comment_items(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for i, text in enumerate(ctx.get("comments", []), start=1):
        out.append({
            "kind": "youtube#commentThread",
            "id": f"t{i}",
            "snippet": {
                "videoId": ctx["video_id"],
                "topLevelComment": {
                    "kind": "youtube#comment",
                    "id": f"t{i}",
                    "snippet": {
                        "textDisplay": text,
                        "textOriginal": text,
                        "likeCount": 100 - i,
                        "publishedAt": "2026-11-10T01:00:00Z",
                    },
                },
            },
        })
    return out


def youtube_transport(contexts: Sequence[dict[str, Any]]) -> httpx.MockTransport:
    """영상 상세·인기 댓글만 답하는 가짜 YouTube(그 밖의 주소는 실패)."""
    by_id = {c["video_id"]: c for c in contexts}

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/videos"):
            ids = request.url.params.get("id", "").split(",")
            items = [_video_item(by_id[i]) for i in ids if i in by_id]
            return httpx.Response(200, json={"kind": "youtube#videoListResponse", "items": items})
        if path.endswith("/commentThreads"):
            ctx = by_id.get(request.url.params.get("videoId", ""))
            items = _comment_items(ctx) if ctx else []
            return httpx.Response(200, json={"kind": "youtube#commentThreadListResponse",
                                             "items": items})
        return httpx.Response(404, json={"error": {"code": 404, "message": "eval: 없는 주소"}})

    return httpx.MockTransport(handle)


def eval_settings(model: str, db_path: Path, *, timeout: float | None = None) -> Settings:
    environ = {
        "YOUTUBE_API_KEY": "AIza" + "x" * 35,  # 가짜 YouTube에만 쓰는 가짜 키(실행할 때 조립)
        "OLLAMA_MODEL": model,
    }
    base = load_settings(env_path=None, db_path=db_path, environ=environ)
    if timeout:
        from dataclasses import replace

        base = replace(base, llm=replace(base.llm, timeout_seconds=timeout))
    return base


def prepare(services: Services, contexts: Sequence[dict[str, Any]]) -> None:
    """맥락마다 자막을 붙여 넣는다(3단계 수동 자막과 같은 길)."""
    for ctx in contexts:
        if ctx.get("transcript"):
            services.context.set_manual_transcript(ctx["video_id"], ctx["transcript"])
        else:
            services.context.build(ctx["video_id"])


# ---------------------------------------------------------------- 실행


@dataclass
class DraftRow:
    video_id: str
    title: str
    n: int
    body: str = ""
    quote: str = ""
    source: str = ""
    tone: str = ""
    attempts: int = 0
    first_passed: bool = False
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""
    approved: bool = False
    v12_failed: bool = False  # 최종 글이 V12에 걸렸는지
    no_concern: bool = False  # 분석이 「연애 고민 없음」으로 멈춰 초안을 만들지 않았는지
    foreign_product: str = ""  # 초안에 들어간 남의 상품 이름(실제 데이터 보정)


@dataclass
class ModelResult:
    model: str
    load_s: float | None = None
    warm_first_s: float | None = None  # 불러온 직후 첫 분석(가장 느린 한 번)
    analyses: list[dict[str, Any]] = field(default_factory=list)
    drafts: list[DraftRow] = field(default_factory=list)
    error: str = ""

    @property
    def total(self) -> int:
        return len(self.drafts)

    def rate(self, key: str) -> float:
        if not self.drafts:
            return 0.0
        return sum(bool(getattr(d, key)) for d in self.drafts) / len(self.drafts)

    @property
    def avg_s(self) -> float:
        done = [d.seconds for d in self.drafts if not d.error]
        return sum(done) / len(done) if done else 0.0

    @property
    def avg_attempts(self) -> float:
        done = [d.attempts for d in self.drafts if not d.error]
        return sum(done) / len(done) if done else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "drafts": self.total,
            "first_pass_rate": round(self.rate("first_passed"), 3),
            "pass_rate": round(self.rate("passed"), 3),
            "avg_draft_s": round(self.avg_s, 1),
            "avg_attempts": round(self.avg_attempts, 2),
            "load_s": self.load_s,
            "warm_first_s": self.warm_first_s,
            "dropped_evidence": sum(a.get("dropped", 0) for a in self.analyses),
            "no_concern_stops": sum(bool(a.get("no_concern")) for a in self.analyses),
            "foreign_product_drafts": sum(bool(d.foreign_product) for d in self.drafts),
            **self.closing_stats(),
            "error": self.error,
        }


    def closings(self) -> list[str]:
        return [
            closing_sentence(d.body, brand="운명원", disclosure="[광고]")
            for d in self.drafts if d.body
        ]

    def closing_stats(self) -> dict[str, int]:
        closings = self.closings()
        return {
            "distinct_closings": len(set(closings)),
            "stock_closings": sum(any(w in c for w in STOCK_CLOSINGS) for c in closings),
            "v12_failed": sum(d.v12_failed for d in self.drafts),
            "approved": sum(d.approved for d in self.drafts),
        }


def timed(fn: Callable[[], Any]) -> tuple[Any, float]:
    started = time.monotonic()
    value = fn()
    return value, round(time.monotonic() - started, 1)


def run_contexts(
    services: Services,
    contexts: Sequence[dict[str, Any]],
    *,
    drafts_per_context: int,
    result: ModelResult,
    log: Callable[[str], None] = print,
    approve_first: bool = False,
) -> None:
    """맥락마다 분석 1번 + 초안 N개. 분석 실패는 그 맥락만 건너뛴다.

    `approve_first`면 맥락마다 처음 통과한 초안을 승인한다(다음 맥락의 「이미 쓴 권유 문장」·V11).
    """
    drafter = services.drafts
    for ctx in contexts:
        vid = ctx["video_id"]
        foreign = [str(x) for x in ctx.get("foreign_products") or [] if x]
        try:
            analysis, secs = timed(lambda vid=vid: drafter.analyze(vid))
        except AppError as exc:
            if exc.kind is ErrorKind.NO_LOVE_CONCERN:  # 멈춤(기대한 동작일 수 있다) — 오류와 따로
                result.analyses.append({"video_id": vid, "no_concern": True,
                                        "reason": exc.detail})
                for n in range(1, drafts_per_context + 1):
                    result.drafts.append(DraftRow(vid, ctx["title"], n, no_concern=True,
                                                  error="연애 고민 없음 · 멈춤"))
                log(f"  {vid} 연애 고민 없음으로 멈춤: {exc.detail}")
                continue
            result.analyses.append({"video_id": vid, "error": f"{exc.kind}: {exc.detail}"})
            for n in range(1, drafts_per_context + 1):
                result.drafts.append(DraftRow(vid, ctx["title"], n, error=f"분석 실패 {exc.kind}"))
            log(f"  {vid} 분석 실패: {exc.kind}")
            continue
        if result.warm_first_s is None:
            result.warm_first_s = secs
        result.analyses.append({
            "video_id": vid,
            "seconds": secs,
            "topic": analysis.topic,
            "concern": analysis.concern,
            "tone": analysis.tone,
            "viewer_needs": analysis.viewer_needs,
            "evidence": [e.to_dict() for e in analysis.evidence],
            "dropped": len(analysis.dropped),
            "dropped_quotes": list(analysis.dropped),
            "fallback": analysis.fallback,
        })
        log(f"  {vid} 분석 {secs:.1f}s · 근거 {len(analysis.evidence)}개"
            f" · 버림 {len(analysis.dropped)}")
        used: list[str] = []
        approved_one = False
        for n in range(1, drafts_per_context + 1):
            row = DraftRow(vid, ctx["title"], n)
            try:
                draft, row.seconds = timed(
                    lambda vid=vid, used=tuple(used): drafter.generate(vid, avoid_quotes=used)
                )
            except AppError as exc:
                row.error = f"{exc.kind}: {exc.detail}"
                row.no_concern = exc.kind is ErrorKind.NO_LOVE_CONCERN
                result.drafts.append(row)
                log(f"    초안 {n} 실패: {exc.kind}")
                continue
            used.append(draft.evidence_quote)
            row.body = draft.body
            row.quote = draft.evidence_quote
            row.source = draft.evidence_source
            row.tone = draft.tone_label
            row.attempts = draft.attempts
            row.first_passed = draft.first_passed
            row.passed = draft.passed
            row.failures = draft.validation.failure_lines()
            row.v12_failed = any(c.code == "V12" for c in draft.validation.failures)
            row.foreign_product = next((x for x in foreign if x in draft.body), "")
            result.drafts.append(row)
            mark = "통과" if draft.passed else "실패"
            if row.foreign_product:
                mark += f" · 남의 상품 권함({row.foreign_product})"
            log(f"    초안 {n} {mark} · {draft.attempts}번 · {row.seconds:.1f}s · {draft.body}")
            # 다음 초안을 만들면 승인 안 한 초안은 밀려나므로(superseded) 통과하자마자 승인한다
            if approve_first and draft.passed and not approved_one:
                try:
                    drafter.approve(draft.id)
                    row.approved = approved_one = True
                    log(f"    승인: 초안 {n}")
                except AppError as exc:  # 승인 때 다시 검사한다
                    log(f"    승인 못 함: {exc.kind}")


def unload_all(base_url: str) -> None:
    try:
        res = httpx.get(f"{base_url}/api/ps", timeout=10)
        for m in res.json().get("models") or []:
            httpx.post(
                f"{base_url}/api/chat",
                json={"model": m["name"], "messages": [], "stream": False, "keep_alive": 0},
                timeout=120,
            )
    except httpx.HTTPError:
        pass


def run_model(
    model: str,
    contexts: Sequence[dict[str, Any]],
    *,
    drafts_per_context: int,
    timeout: float | None,
    log: Callable[[str], None] = print,
    approve_first: bool = False,
) -> ModelResult:
    result = ModelResult(model=model)
    with tempfile.TemporaryDirectory() as tmp:
        settings = eval_settings(model, Path(tmp) / "eval.sqlite3", timeout=timeout)
        services = build_services(settings, transport=youtube_transport(contexts), clock=utc_now)
        try:
            unload_all(settings.llm.ollama_base_url)
            llm = services.require_llm()
            result.load_s = round(llm.warmup(), 1)
            log(f"- {model}: 불러오기 {result.load_s:.1f}s")
            prepare(services, contexts)
            run_contexts(
                services, contexts, drafts_per_context=drafts_per_context, result=result, log=log,
                approve_first=approve_first,
            )
        except AppError as exc:
            result.error = f"{exc.kind}: {exc.detail or exc.message}"
            log(f"  {model} 중단: {result.error}")
        finally:
            llm = services.llm
            if llm is not None and hasattr(llm, "unload"):
                try:
                    llm.unload()
                except AppError:
                    pass
            services.close()
    return result


# ---------------------------------------------------------------- 표


def pick_model(results: Sequence[ModelResult]) -> ModelResult | None:
    """D3 기본 규칙: 3번 안 통과율 → 첫 시도 통과율 → 빠른 쪽(초안 평균 시간)."""
    usable = [r for r in results if r.total and not r.error]
    if not usable:
        return None
    return sorted(usable, key=lambda r: (-r.rate("passed"), -r.rate("first_passed"), r.avg_s))[0]


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _fmt(x: float | None) -> str:
    return "–" if x is None else f"{x:.1f}"


def markdown(results: Sequence[ModelResult], *, contexts: int, drafts: int) -> str:
    lines = [
        f"맥락 {contexts}개 × 모델마다 초안 {drafts}개(= {contexts * drafts}개). "
        "통과 = 규칙 검사 V1~V12 모두 통과. 시간 단위 초.",
        "",
        "| 모델 | 초안 | 첫 시도 통과율 | 3번 안 통과율 | 평균 시도 | 초안 평균 시간 | 불러오기 "
        "| 불러온 뒤 첫 분석 | 버린 근거 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        s = r.summary()
        lines.append(
            f"| `{r.model}` | {r.total} | {_pct(r.rate('first_passed'))} "
            f"| {_pct(r.rate('passed'))} "
            f"| {s['avg_attempts']:.2f} | {_fmt(r.avg_s)} | {_fmt(r.load_s)} "
            f"| {_fmt(r.warm_first_s)} | {s['dropped_evidence']} |"
            + (f" 중단: {r.error}" if r.error else "")
        )
    lines += [
        "",
        "| 모델 | 권유 문장 서로 다른 것 | 굳은 틀(흐름이 궁금…) | V12 걸림 | 승인 |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        c = r.closing_stats()
        lines.append(
            f"| `{r.model}` | {c['distinct_closings']}/{r.total} | {c['stock_closings']} "
            f"| {c['v12_failed']} | {c['approved']} |"
        )
    lines += [
        "",
        "맥락마다(실제 데이터 보정): 분석의 핵심 고민 또는 「연애 고민 없음」으로 멈춤, "
        "통과한 초안 수, "
        "남의 상품(맥락의 `foreign_products`)이 든 초안 수.",
        "",
        "| 모델 | 영상 | 분석 | 통과 | 남의 상품 권함 |",
        "|---|---|---|---:|---:|",
    ]
    for r in results:
        by_vid = {a["video_id"]: a for a in r.analyses}
        for vid in dict.fromkeys(d.video_id for d in r.drafts):
            rows = [d for d in r.drafts if d.video_id == vid]
            a = by_vid.get(vid, {})
            if a.get("no_concern"):
                what = "연애 고민 없음 · 멈춤"
            elif a.get("error"):
                what = f"오류 {a['error']}"
            else:
                what = str(a.get("concern") or "").replace("|", "/")
            passed = sum(d.passed for d in rows)
            foreign = sum(bool(d.foreign_product) for d in rows)
            lines.append(f"| `{r.model}` | {vid} | {what} | {passed}/{len(rows)} | {foreign} |")
    for r in results:
        lines += ["", f"#### `{r.model}` 초안 원문", "",
                  "| 영상 | # | 결과 | 시도 | 초안 (근거 · 출처) |", "|---|---:|---|---:|---|"]
        for d in r.drafts:
            if d.error:
                lines.append(f"| {d.video_id} | {d.n} | 오류 | – | {d.error} |")
                continue
            codes = ", ".join(f.split(" ", 1)[0] for f in d.failures)
            mark = "통과" if d.passed else f"실패: {codes}"
            if d.approved:
                mark += " · 승인"
            if d.foreign_product:
                mark += f" · 남의 상품 권함({d.foreign_product})"
            body = d.body.replace("|", "/")
            lines.append(
                f"| {d.video_id} | {d.n} | {mark} | {d.attempts} | {body} "
                f"<br>(근거 '{d.quote.replace('|', '/')}' · {d.source}) |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="*", default=list(DEFAULT_MODELS))
    parser.add_argument("--contexts", type=int, default=None,
                        help="쓸 가상 맥락 수(앞에서부터, 비우면 전부)")
    parser.add_argument("-d", "--drafts", type=int, default=3, help="맥락마다 초안 수")
    parser.add_argument("--timeout", type=float, default=300.0, help="요청 하나의 시간 제한(초)")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument(
        "--approve-first", action="store_true",
        help="영상마다 처음 통과한 초안을 승인(다음 영상이 그 권유 문장을 피하게)",
    )
    args = parser.parse_args(argv)

    contexts = load_contexts(limit=args.contexts)
    models = ", ".join(args.models)
    print(f"맥락 {len(contexts)}개 × 초안 {args.drafts}개 · 모델 {models}", flush=True)
    results = []
    started = time.monotonic()
    for model in args.models:
        results.append(
            run_model(
                model, contexts, drafts_per_context=args.drafts, timeout=args.timeout,
                log=lambda s: print(s, flush=True), approve_first=args.approve_first,
            )
        )
    elapsed = time.monotonic() - started
    table = markdown(results, contexts=len(contexts), drafts=args.drafts)
    best = pick_model(results)
    print()
    print(table)
    print()
    print(f"전체 {elapsed / 60:.1f}분. 기본 규칙으로 고른 모델: {best.model if best else '없음'}")
    if args.md_out:
        args.md_out.write_text(table + "\n", encoding="utf-8")
    if args.json_out:
        data = {
            "elapsed_s": round(elapsed, 1),
            "picked": best.model if best else None,
            "results": [
                {**r.summary(), "analyses": r.analyses, "drafts": [asdict(d) for d in r.drafts]}
                for r in results
            ],
        }
        args.json_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
