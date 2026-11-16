"""댓글 초안 서비스(PLAYBOOK 5단계): 분석 → 근거 고르기 → 본문 쓰기 → 규칙 검사 → 다시 쓰기.

초안 만들기 흐름
1. 근거 구절 하나를 고른다(`avoid_quotes`에 없는 것, 자막 > 댓글 > 설명 > 제목 순).
2. 모델은 **본문만** 쓴다. 홍보 표기 `[광고] `는 코드가 앞에 붙인다(모델이 빼먹을 수 없게).
3. 6단계 `CheckService.check()`(= `validate()`)로 검사한다. 걸리면 실패 문구를 넣어 다시 쓰게 한다
   (모두 3번까지).
4. 세 번 다 걸리면 실패가 가장 적은 것을 저장하고 걸린 항목을 표시한다(사람이 고친다).
5. [다른 초안 생성]은 이미 쓴 근거 구절을 `avoid_quotes`에 넣고 1번부터.

검사에 쓰는 이전 글(V11)은 **다른 영상에서 승인한 초안**이다(같은 영상 초안끼리는 비교하지 않는다).
승인은 지금 글을 다시 검사한 뒤 통과한 것만 받는다. 승인하면 같은 영상의 다른 초안은 모두
`superseded`가 된다(영상당 승인 초안 하나).

LLM은 `LLMClient` 규격만 쓴다(`llm` 인자는 그때그때 공급자를 돌려주는 함수).

7단계: 분석·초안 생성·승인을 작업 기록(`runs`)에 남긴다(`ledger`를 넣었을 때). 해낸 것은 info,
오류로 멈춘 것은 failure와 사유. V11의 이전 글에는 게시한 댓글(다른 영상)도 들어간다.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.analysis import analyzer
from app.analysis.analyzer import Analysis, Evidence
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.validator import Validation, normalize
from app.errors import AppError, ErrorKind
from app.llm import prompts
from app.llm.base import LLMClient
from app.ops.ledger import Ledger
from app.youtube.quota import Clock
from app.youtube.url_parser import is_video_id

MAX_ATTEMPTS = 3
DraftStatus = str  # 'draft' | 'approved' | 'superseded'

_QUOTES = "'\"‘’“”"


@dataclass(frozen=True)
class Draft:
    id: int
    video_id: str
    body: str  # 표기를 포함한 전체 글(이 글을 검사하고 게시한다)
    evidence_quote: str
    evidence_source: str
    tone_label: str
    model: str
    attempts: int  # 모델에게 쓰게 한 횟수(사람이 고치면 그대로)
    validation: Validation
    passed: bool
    status: DraftStatus
    edited_by_human: bool
    created_at: str
    updated_at: str
    approved_at: str | None
    first_passed: bool = False  # 첫 시도에서 통과했는지(모델 비교용)


def clean_body(raw: Any, disclosure: str) -> str:
    """모델 본문 정리: 줄바꿈·연속 공백을 한 칸으로, 앞뒤 따옴표, 모델이 붙인 표기는 뗀다."""
    text = unicodedata.normalize("NFC", str(raw or ""))
    text = " ".join(text.split())
    if len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES and text[0] == text[-1]:
        text = text[1:-1].strip()
    while disclosure and text.startswith(disclosure):
        text = text[len(disclosure) :].lstrip(" :·-")
    return text.strip()


def with_disclosure(body: str, disclosure: str) -> str:
    return f"{disclosure} {body}".strip()


def _validation_to_json(v: Validation) -> str:
    return json.dumps(v.to_dict(), ensure_ascii=False)


def _validation_from_json(raw: str) -> Validation:
    from app.analysis.validator import CheckResult

    data = json.loads(raw)
    return Validation(
        passed=bool(data["passed"]),
        checks=tuple(CheckResult(**c) for c in data["checks"]),
        char_count=int(data["char_count"]),
        evidence_quote=data.get("evidence_quote"),
    )


class DraftService:
    def __init__(
        self,
        context: ContextService,
        checks: CheckService,
        *,
        llm: Callable[[], LLMClient],
        db_path: Path,
        clock: Clock,
        brand_facts: Sequence[str] = (),
        max_attempts: int = MAX_ATTEMPTS,
        ledger: Ledger | None = None,
    ) -> None:
        self.context = context
        self.checks = checks
        self._llm = llm
        self.db_path = db_path
        self.clock = clock
        self.brand_facts = tuple(brand_facts)
        self.max_attempts = max_attempts
        self.ledger = ledger

    @property
    def rules(self):
        return self.checks.rules

    # ------------------------------------------------------------ 분석

    def analyze(self, video_id: str) -> Analysis:
        """맥락이 없으면 만들고(3단계) 분석해 저장한다. 같은 영상은 마지막 분석 하나만 남긴다."""
        self._check_id(video_id)
        try:
            result = self._analyze(video_id)
        except AppError as exc:
            self._record("analyze", "failure", video_id=video_id, reason=exc.message)
            raise
        reason = f"핵심 고민 · {result.concern}" if result.concern else "분석 완료"
        self._record("analyze", "info", video_id=video_id, reason=reason)
        return result

    def _analyze(self, video_id: str) -> Analysis:
        context = self.context.current(video_id)
        llm = self._llm()
        result = analyzer.analyze(
            context,
            llm,
            prompt_text=self.context.prompt_text(context),
            search_text=self.context.search_text(context),
            created_at=self._now(),
        )
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO analyses(video_id, topic, concern, tone, viewer_needs, evidence_json, "
                "dropped_json, fallback, model, created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(video_id) DO UPDATE SET topic=excluded.topic, "
                "concern=excluded.concern, tone=excluded.tone, viewer_needs=excluded.viewer_needs, "
                "evidence_json=excluded.evidence_json, dropped_json=excluded.dropped_json, "
                "fallback=excluded.fallback, model=excluded.model, created_at=excluded.created_at",
                (
                    video_id,
                    result.topic,
                    result.concern,
                    result.tone,
                    result.viewer_needs,
                    json.dumps([e.to_dict() for e in result.evidence], ensure_ascii=False),
                    json.dumps(list(result.dropped), ensure_ascii=False),
                    int(result.fallback),
                    result.model,
                    result.created_at,
                ),
            )
        return result

    def stored_analysis(self, video_id: str) -> Analysis | None:
        self._check_id(video_id)
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT * FROM analyses WHERE video_id = ?", (video_id,)).fetchone()
        if row is None:
            return None
        return Analysis(
            video_id=row["video_id"],
            topic=row["topic"],
            concern=row["concern"],
            tone=row["tone"],
            viewer_needs=row["viewer_needs"],
            evidence=tuple(Evidence(**e) for e in json.loads(row["evidence_json"])),
            dropped=tuple(json.loads(row["dropped_json"])),
            model=row["model"],
            created_at=row["created_at"],
            fallback=bool(row["fallback"]),
        )

    # ------------------------------------------------------------ 초안

    def generate(self, video_id: str, *, avoid_quotes: Sequence[str] = ()) -> Draft:
        """초안 하나를 만들어 저장한다. 같은 영상의 이전 'draft' 초안은 'superseded'가 된다."""
        self._check_id(video_id)
        try:
            draft = self._generate(video_id, avoid_quotes)
        except AppError as exc:
            self._record("draft", "failure", video_id=video_id, reason=exc.message)
            raise
        if draft.passed:
            reason = f"규칙 검사 통과 · {draft.attempts}번째 시도"
        else:
            reason = f"규칙 검사 {len(draft.validation.failures)}개 걸림 · {draft.attempts}번 시도"
        self._record(
            "draft", "info", video_id=video_id, comment_text=draft.body, reason=reason,
            draft_id=draft.id,
        )
        return draft

    def _generate(self, video_id: str, avoid_quotes: Sequence[str]) -> Draft:
        analysis = self.stored_analysis(video_id) or self.analyze(video_id)
        evidence = analyzer.pick_evidence(analysis.evidence, avoid_quotes)
        llm = self._llm()
        rules = self.rules
        min_body, max_body = prompts.body_limits(
            min_chars=rules.min_chars, max_chars=rules.max_chars, disclosure=rules.disclosure
        )
        system = prompts.draft_system(
            brand=rules.brand, disclosure=rules.disclosure, facts=self.brand_facts
        )
        previous = self.previous_texts(video_id)
        avoid_bodies = [d.body for d in self.list(video_id)][:3]
        # 다른 영상에서 승인한 초안의 권유 문장: 되풀이하지 말라고 프롬프트에 넣는다(5단계 점검)
        used_closings = [
            prompts.closing_sentence(t, brand=rules.brand, disclosure=rules.disclosure)
            for t in previous
        ]

        best: tuple[int, str, str, Validation, int] | None = None  # (실패 수, 글, 말투, 검사, 차례)
        failure_lines: list[str] = []
        previous_body = ""
        attempts = 0
        first_passed = False
        for attempt in range(1, self.max_attempts + 1):
            user = prompts.draft_user(
                analysis=analysis.to_prompt(),
                quote=evidence.quote,
                source=evidence.source,
                min_body=min_body,
                max_body=max_body,
                failure_lines=failure_lines,
                previous_body=previous_body,
                avoid_bodies=avoid_bodies,
                used_closings=used_closings,
            )
            try:
                data = llm.generate_json(
                    system=system,
                    user=user,
                    schema=prompts.DRAFT_SCHEMA,
                    temperature=prompts.DRAFT_TEMPERATURE,
                    max_tokens=prompts.DRAFT_MAX_TOKENS,
                )
            except AppError:
                if best is None:
                    raise
                break  # 앞에서 받은 것 중 가장 나은 것을 저장한다
            attempts = attempt
            body = clean_body(data.get("body"), rules.disclosure)
            text = with_disclosure(body, rules.disclosure)
            tone = str(data.get("tone_label") or "")
            if tone not in prompts.TONE_LABELS:
                tone = ""
            validation = self.checks.check(
                video_id, text, previous_texts=previous, evidence_quote=evidence.quote
            )
            fails = len(validation.failures)
            if best is None or fails < best[0]:
                best = (fails, text, tone, validation, attempt)
            if validation.passed:
                first_passed = attempt == 1
                break
            failure_lines = validation.failure_lines()
            previous_body = body

        assert best is not None
        _, text, tone, validation, _ = best
        now = self._now()
        with db.session(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET status='superseded', updated_at=? "
                "WHERE video_id=? AND status='draft'",
                (now, video_id),
            )
            cur = conn.execute(
                "INSERT INTO drafts(video_id, body, evidence_quote, evidence_source, tone_label, "
                "model, attempts, first_passed, validation_json, passed, status, edited_by_human, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,'draft',0,?,?)",
                (
                    video_id,
                    text,
                    evidence.quote,
                    evidence.source,
                    tone,
                    str(getattr(llm, "model", "") or ""),
                    attempts,
                    int(first_passed),
                    _validation_to_json(validation),
                    int(validation.passed),
                    now,
                    now,
                ),
            )
            draft_id = int(cur.lastrowid)
        return self.get(draft_id)

    def list(self, video_id: str) -> list[Draft]:
        """그 영상의 초안들(최신이 위)."""
        self._check_id(video_id)
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE video_id = ? ORDER BY id DESC", (video_id,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, draft_id: int) -> Draft:
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise AppError(ErrorKind.DRAFT_NOT_FOUND, detail=f"초안 {draft_id}")
        return self._row(row)

    def update_text(self, draft_id: int, text: str) -> Draft:
        """사람이 고친 글. 같은 검사를 다시 거친다(근거는 글에서 찾는다 — 화면의 검사와 같다)."""
        draft = self.get(draft_id)
        if draft.status == "superseded":
            raise AppError(ErrorKind.DRAFT_SUPERSEDED, detail=f"초안 {draft_id}")
        clean = unicodedata.normalize("NFC", text or "").strip()
        validation = self._recheck(draft.video_id, clean, None)
        quote = validation.evidence_quote or draft.evidence_quote
        source = self._source_of(draft.video_id, quote) or draft.evidence_source
        changed = clean != draft.body
        now = self._now()
        with db.session(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET body=?, evidence_quote=?, evidence_source=?, validation_json=?, "
                "passed=?, edited_by_human=?, status=?, approved_at=?, updated_at=? WHERE id=?",
                (
                    clean,
                    quote,
                    source,
                    _validation_to_json(validation),
                    int(validation.passed),
                    int(draft.edited_by_human or changed),
                    # 승인한 뒤 글을 바꾸면 다시 승인해야 한다
                    "draft" if changed else draft.status,
                    None if changed else draft.approved_at,
                    now,
                    draft_id,
                ),
            )
        return self.get(draft_id)

    def approve(self, draft_id: int) -> Draft:
        """지금 글을 다시 검사해 통과한 것만 승인한다. 아니면 409와 걸린 항목."""
        draft = self.get(draft_id)
        try:
            approved = self._approve(draft)
        except AppError as exc:
            reason = exc.message
            if exc.kind == ErrorKind.DRAFT_NOT_PASSED:
                reason = f"규칙 검사 {len(exc.extra.get('failures', []))}개 걸림 · 승인 안 됨"
            self._record(
                "approve", "failure", video_id=draft.video_id, comment_text=draft.body,
                reason=reason, draft_id=draft.id,
            )
            raise
        self._record(
            "approve", "info", video_id=approved.video_id, comment_text=approved.body,
            reason="사람이 승인" + (" · 고친 글" if approved.edited_by_human else ""),
            draft_id=approved.id,
        )
        return approved

    def _approve(self, draft: Draft) -> Draft:
        draft_id = draft.id
        if draft.status == "superseded":
            raise AppError(ErrorKind.DRAFT_SUPERSEDED, detail=f"초안 {draft_id}")
        quote = None if draft.edited_by_human else draft.evidence_quote
        validation = self._recheck(draft.video_id, draft.body, quote)
        now = self._now()
        with db.session(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET validation_json=?, passed=?, updated_at=? WHERE id=?",
                (_validation_to_json(validation), int(validation.passed), now, draft_id),
            )
            if not validation.passed:
                conn.commit()
                raise AppError(
                    ErrorKind.DRAFT_NOT_PASSED,
                    detail=f"초안 {draft_id}: 걸린 항목 {len(validation.failures)}개",
                    extra={"failures": [c.to_dict() for c in validation.failures]},
                )
            conn.execute(
                "UPDATE drafts SET status='superseded', approved_at=NULL, updated_at=? "
                "WHERE video_id=? AND id<>? AND status IN ('draft', 'approved')",
                (now, draft.video_id, draft_id),
            )
            conn.execute(
                "UPDATE drafts SET status='approved', approved_at=? WHERE id=?", (now, draft_id)
            )
        return self.get(draft_id)

    def previous_texts(self, video_id: str | None = None) -> list[str]:
        """V11 비교 대상: 승인한 초안과 게시한 댓글(다른 영상 것). 최근 50개씩, 겹치면 하나."""
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT body FROM drafts WHERE status='approved' AND video_id IS NOT ? "
                "ORDER BY approved_at DESC, id DESC LIMIT 50",
                (video_id,),
            ).fetchall()
            posted = conn.execute(
                "SELECT comment_text FROM runs WHERE action='post' AND result='success' "
                "AND video_id IS NOT ? AND comment_text <> '' ORDER BY at DESC, id DESC LIMIT 50",
                (video_id,),
            ).fetchall()
        texts = [r["body"] for r in rows] + [r["comment_text"] for r in posted]
        return list(dict.fromkeys(texts))

    # ------------------------------------------------------------ 내부

    def _record(self, action: str, result: str, **fields: Any) -> None:
        if self.ledger is not None:
            self.ledger.record(action, result, **fields)

    def _recheck(self, video_id: str, text: str, quote: str | None) -> Validation:
        return self.checks.check(
            video_id, text, previous_texts=self.previous_texts(video_id), evidence_quote=quote
        )

    def _source_of(self, video_id: str, quote: str) -> str | None:
        if not quote:
            return None
        context = self.context.current(video_id)
        evidence, _ = analyzer.check_evidence(
            [{"quote": quote, "source": ""}], context, self.context.search_text(context)
        )
        return evidence[0].source if evidence else None

    def _now(self) -> str:
        return self.clock().isoformat()

    @staticmethod
    def _check_id(video_id: str) -> None:
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")

    @staticmethod
    def _row(row) -> Draft:
        return Draft(
            id=int(row["id"]),
            video_id=row["video_id"],
            body=row["body"],
            evidence_quote=row["evidence_quote"],
            evidence_source=row["evidence_source"],
            tone_label=row["tone_label"],
            model=row["model"],
            attempts=int(row["attempts"]),
            validation=_validation_from_json(row["validation_json"]),
            passed=bool(row["passed"]),
            status=row["status"],
            edited_by_human=bool(row["edited_by_human"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            first_passed=bool(row["first_passed"]),
        )


def used_quotes(drafts: Sequence[Draft]) -> list[str]:
    """[다른 초안 생성]이 피할 근거 구절(이미 쓴 것)."""
    out: list[str] = []
    seen: set[str] = set()
    for d in drafts:
        key = normalize(d.evidence_quote)
        if key and key not in seen:
            seen.add(key)
            out.append(d.evidence_quote)
    return out

