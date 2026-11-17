"""댓글 초안 서비스(PLAYBOOK 5단계): 분석 → 근거 고르기 → 본문 쓰기 → 규칙 검사 → 다시 쓰기.

초안 만들기 흐름
1. 근거 구절 하나를 고른다(`avoid_quotes`에 없는 것, 자막 > 제목 > 댓글 > 설명 순).
   분석이 연애 고민을 찾지 못하면(`no_love_concern`) 초안을 만들지 않고 그 오류로 멈춘다.
2. 모델은 **본문만** 쓴다. 광고 표기 `[광고] `는 코드가 앞에 붙인다(모델이 빼먹을 수 없게).
   R3: 표기는 모든 영상에서 켜고 끌 수 있다(`disclose`, 비우면 설정의 「광고 표기 기본값」).
   초안마다 표기를 붙였는지(`drafts.disclosed`)를 남기고, 검사 V4는 켠 초안에만 표기를 요구한다.
   켬/끔을 바꾸면(`set_disclosure`) 저장된 글에서 표기만 붙이거나 떼고 다시 검사한다
   (모델을 부르지 않는다).
3. 6단계 `CheckService.check()`(= `validate()`)로 검사한다. 걸리면 실패 문구를 넣어 다시 쓰게 한다
   (모두 3번까지).
4. 세 번 다 걸리면 실패가 가장 적은 것을 저장하고 걸린 항목을 표시한다(사람이 고친다).
5. [다른 초안 생성]은 이미 쓴 근거 구절을 `avoid_quotes`에 넣고 1번부터.

검사에 쓰는 이전 글(V11)은 **다른 영상에서 승인한 초안**이다(같은 영상 초안끼리는 비교하지 않는다).
승인은 지금 글을 다시 검사한 뒤 통과한 것만 받는다. 승인하면 같은 영상의 다른 초안은 모두
`superseded`가 된다(영상당 승인 초안 하나).

LLM은 `LLMClient` 규격만 쓴다(`llm` 인자는 그때그때 공급자를 돌려주는 함수).

C1(2026-11-17, 과제 예시처럼 자연스럽게)
- 분석의 핵심 말을 저장하고(`analyses.key_phrases_json`) 초안 프롬프트와 검사(V7)에 넘긴다. 고민
  한 줄도 검사(V13: 길게 베끼지 않음)에 넘긴다. 과제 PDF의 예시 댓글은 말투 기준으로만 넣는다.
- 예전에 저장된 분석(핵심 말 없음, `legacy`)은 화면·검사에서는 제목·해시태그에서 뽑은 핵심 말로
  쓰고, 초안을 만들 때는 먼저 다시 분석한다(요약 꼴 고민 한 줄을 그대로 쓰지 않게).
- 말투 유형은 직전에 승인한 다른 영상 초안과 같은 영상의 앞 초안의 유형을 빼고 고르게 한다.
- 사람이 고친 글도 초안의 근거 구절(V6)·영상의 핵심 말(V7)·고민 한 줄(V13)로 검사한다. 예전에는
  근거를 글에서 찾았는데, 이제 초안이 근거를 글자 그대로 옮기지 않으므로 글자 하나만 고쳐도 V6이
  걸렸다.

C1 다듬기(2026-11-17, 대표 지시 「초안 더 다듬고」)
- 규칙 검사를 통과해도 다듬기 검사(`app/analysis/style.py`: 110자 넘음, 바람에 핵심 말, 붙여 쓴 말,
  같은 영상 앞 초안과 비슷함)에 걸리면 다시 쓸 차례가 남았을 때 한 번 더 쓰게 한다. 마지막 차례면
  통과한 글을 그대로 둔다(다듬기 검사는 승인을 막지 않는다).
- [다른 댓글 만들기]: 같은 영상 앞 초안의 핵심 말·운명원 꺼내는 말을 피하게 한다.
- 다듬기 단계(`polish`): 통과한 초안을 모델에게 한 번 더 보여 말이 안 되는 문장·틀린 조사와
  띄어쓰기·억지로 끼운 말만 고치게 하고 다시 검사한다. 고친 글이 검사에 걸리거나 다듬기 검사의
  문제가 늘면 원래 글을 쓴다. 마지막 만들기의 과정은 `last_run`에 남는다(모델 비교용).

7단계: 분석·초안 생성·승인을 작업 기록(`runs`)에 남긴다(`ledger`를 넣었을 때). 해낸 것은 info,
오류로 멈춘 것은 failure와 사유. V11의 이전 글에는 게시한 댓글(다른 영상)도 들어간다.
"""

from __future__ import annotations

import json
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import db
from app.analysis import analyzer, style
from app.analysis.analyzer import Analysis, Evidence
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.validator import ASSIGNMENT_SAMPLE, Validation, normalize
from app.errors import AppError, ErrorKind
from app.llm import prompts
from app.llm.base import LLMClient
from app.ops.ledger import Ledger
from app.youtube.quota import Clock
from app.youtube.url_parser import is_video_id

MAX_ATTEMPTS = 3
# 다듬기 단계를 쓸지. 끈다: 6회차(qwen3.8:27b, 초안 16개)에서 다듬기는 초안 1개에 5.8초(약 24%)를
# 더 쓰고 16개 중 2개만 바꿨는데 둘 다 끝말 하나(「들었어」→「들었어요」)였고, 어색한 문장은 하나도
# 고치지 못했다. 대신 어색한 꼴을 다듬기 검사(`style.py`)로 잡아 다시 쓰게 한다.
# 자세한 것은 docs/MODEL_EVAL.md 「C1 다듬기」.
POLISH_DRAFTS = False
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
    disclosed: bool = True  # R3: 광고 표기를 붙인 초안인지(끈 초안은 V4가 「표기 끔」으로 통과)


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


def toggle_disclosure(text: str, disclosure: str, on: bool) -> str:
    """글 맨 앞의 광고 표기만 붙이거나 뗀다(나머지 글은 그대로)."""
    rest = text.strip()
    if disclosure and rest.startswith(disclosure):
        rest = rest[len(disclosure) :].lstrip()
    return with_disclosure(rest, disclosure) if on else rest


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
        disclose_default: bool = True,
        polish: bool = POLISH_DRAFTS,
    ) -> None:
        self.context = context
        self.checks = checks
        self._llm = llm
        self.db_path = db_path
        self.clock = clock
        self.brand_facts = tuple(brand_facts)
        self.max_attempts = max_attempts
        self.ledger = ledger
        self.disclose_default = bool(disclose_default)  # R3: 설정의 「광고 표기 기본값」
        self.polish = bool(polish)
        self.last_run: dict[str, Any] = {}  # 마지막 초안 만들기의 과정(시도별 글·다듬기)

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
            reason = exc.message
            if exc.kind is ErrorKind.NO_LOVE_CONCERN:
                # 연애 고민이 없는 자료: 예전 분석이 남아 있으면 지운다(그것으로 초안을 만들지 않게)
                self._forget_analysis(video_id)
                if exc.detail:
                    reason = f"{exc.message} · {exc.detail}"
            self._record("analyze", "failure", video_id=video_id, reason=reason)
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
                "dropped_json, fallback, model, created_at, key_phrases_json, key_phrases_source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(video_id) DO UPDATE SET topic=excluded.topic, "
                "concern=excluded.concern, tone=excluded.tone, viewer_needs=excluded.viewer_needs, "
                "evidence_json=excluded.evidence_json, dropped_json=excluded.dropped_json, "
                "fallback=excluded.fallback, model=excluded.model, created_at=excluded.created_at, "
                "key_phrases_json=excluded.key_phrases_json, "
                "key_phrases_source=excluded.key_phrases_source",
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
                    json.dumps(list(result.key_phrases), ensure_ascii=False),
                    "derived" if result.key_phrases_derived else "model",
                ),
            )
        return result

    def _forget_analysis(self, video_id: str) -> None:
        with db.session(self.db_path) as conn:
            conn.execute("DELETE FROM analyses WHERE video_id = ?", (video_id,))

    def stored_analysis(self, video_id: str) -> Analysis | None:
        self._check_id(video_id)
        with db.session(self.db_path) as conn:
            row = conn.execute("SELECT * FROM analyses WHERE video_id = ?", (video_id,)).fetchone()
        if row is None:
            return None
        phrases = tuple(json.loads(row["key_phrases_json"] or "[]"))
        source = row["key_phrases_source"]
        legacy = source == ""
        if legacy:
            # C1 전에 저장된 분석: 제목·해시태그에서 핵심 말을 뽑아 화면·검사가 깨지지 않게 한다
            context = self.context.current(video_id)
            phrases = tuple(
                analyzer.fallback_key_phrases(context, self.context.search_text(context))
            )
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
            key_phrases=phrases,
            key_phrases_derived=source != "model",
            legacy=legacy,
        )

    # ------------------------------------------------------------ 초안

    def generate(
        self, video_id: str, *, avoid_quotes: Sequence[str] = (), disclose: bool | None = None
    ) -> Draft:
        """초안 하나를 만들어 저장한다. 같은 영상의 이전 'draft' 초안은 'superseded'가 된다.

        `disclose`: 광고 표기를 붙일지(어떤 영상이든). None이면 설정의 「광고 표기 기본값」.
        """
        self._check_id(video_id)
        disclose = self.disclose_default if disclose is None else bool(disclose)
        try:
            draft = self._generate(video_id, avoid_quotes, disclose)
        except AppError as exc:
            self._record("draft", "failure", video_id=video_id, reason=exc.message)
            raise
        if draft.passed:
            reason = f"규칙 검사 통과 · {draft.attempts}번째 시도"
            if self.last_run.get("polish", {}).get("accepted"):
                reason += " · 다듬음"
        else:
            reason = f"규칙 검사 {len(draft.validation.failures)}개 걸림 · {draft.attempts}번 시도"
        self._record(
            "draft", "info", video_id=video_id, comment_text=draft.body, reason=reason,
            draft_id=draft.id, disclosed=draft.disclosed,
        )
        return draft

    def _generate(self, video_id: str, avoid_quotes: Sequence[str], disclose: bool) -> Draft:
        analysis = self.stored_analysis(video_id)
        if analysis is None or analysis.legacy:
            analysis = self.analyze(video_id)  # C1: 예전 분석은 다시 한다(핵심 말·고민의 꼴)
        evidence = analyzer.pick_evidence(analysis.evidence, avoid_quotes)
        llm = self._llm()
        rules = self.rules
        mark = rules.disclosure if disclose else ""  # 앞에 붙일 표기(끄면 빈 글)
        min_body, max_body = prompts.body_limits(
            min_chars=rules.min_chars, max_chars=rules.max_chars, disclosure=mark
        )
        system = prompts.draft_system(
            brand=rules.brand, disclosure=rules.disclosure, facts=self.brand_facts,
            sample=ASSIGNMENT_SAMPLE,
        )
        previous = self.previous_texts(video_id)
        mine = self.list(video_id)
        avoid_bodies = [d.body for d in mine][:3]
        # C1 다듬기: [다른 댓글 만들기]는 앞 초안과 다른 핵심 말로(남은 핵심 말이 있을 때)
        phrases = [k for k in analysis.key_phrases if k]
        used_before = [k for k in phrases if any(k in style.used_phrases(b, phrases)
                                                 for b in avoid_bodies)]
        avoid_phrases = used_before if len(used_before) < len(phrases) else []
        # C1: 말투 유형이 영상마다 이어서 같지 않게(직전 승인 초안), 같은 영상 초안끼리도 다르게
        avoid_tones = [self.last_tone(video_id)] + [d.tone_label for d in mine[:2]]
        tones = prompts.allowed_tones(avoid_tones)
        schema = prompts.draft_schema(tones)
        # 다른 영상에서 승인한 초안의 권유 문장: 되풀이하지 말라고 프롬프트에 넣는다(5단계 점검)
        used_closings = [
            prompts.closing_sentence(t, brand=rules.brand, disclosure=rules.disclosure)
            for t in previous
        ]
        # C1 손질 2회차: 운명원 꺼내는 말·끝말·첫 반응이 한 틀로 굳지 않게 덜 쓴 것을 권한다
        hearsay = prompts.hearsay_choices(rules.brand, previous, avoid=avoid_bodies)
        endings = prompts.ending_choices(previous, avoid=avoid_bodies)
        used_openings = [prompts.opening_sentence(t, disclosure=rules.disclosure) for t in previous]

        # (실패 수, 다듬기 문제 수, 글, 말투, 검사, 차례, 다듬기 문제)
        best: tuple[int, int, str, str, Validation, int, list[str]] | None = None
        run: dict[str, Any] = {"attempts": [], "polish": {}}
        self.last_run = run
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
                key_phrases=analysis.key_phrases,
                tones=tones,
                avoid_tones=[t for t in avoid_tones if t and t not in tones],
                max_chars=rules.max_chars,
                brand=rules.brand,
                hearsay=hearsay,
                endings=endings,
                used_openings=used_openings,
                failure_lines=failure_lines,
                previous_body=previous_body,
                avoid_bodies=avoid_bodies,
                used_closings=used_closings,
                avoid_phrases=avoid_phrases,
            )
            try:
                data = llm.generate_json(
                    system=system,
                    user=user,
                    schema=schema,
                    temperature=prompts.DRAFT_TEMPERATURE,
                    max_tokens=prompts.DRAFT_MAX_TOKENS,
                )
            except AppError:
                if best is None:
                    raise
                break  # 앞에서 받은 것 중 가장 나은 것을 저장한다
            attempts = attempt
            body = clean_body(data.get("body"), rules.disclosure)
            text = with_disclosure(body, mark)
            tone = str(data.get("tone_label") or "")
            if tone not in prompts.TONE_LABELS:
                tone = ""
            validation = self.checks.check(
                video_id, text, previous_texts=previous, evidence_quote=evidence.quote,
                disclose=disclose, key_phrases=analysis.checked_phrases, concern=analysis.concern,
            )
            fails = len(validation.failures)
            issues = self._style(text, mark, analysis.key_phrases, avoid_bodies)
            run["attempts"].append(
                {"body": text, "failures": validation.failure_lines(), "issues": issues}
            )
            if best is None or (fails, len(issues)) < best[:2]:
                best = (fails, len(issues), text, tone, validation, attempt, issues)
            if validation.passed and attempt == 1:
                first_passed = True
            if validation.passed and not issues:
                break
            # 규칙 검사에 걸렸으면 그 문구로, 통과했지만 어색하면 다듬기 검사 문구로 다시 쓴다
            failure_lines = validation.failure_lines() + issues
            previous_body = body

        assert best is not None
        _, _, text, tone, validation, _, issues = best
        if validation.passed and self.polish:
            text, validation = self._polish(
                llm, video_id, text, validation, issues, analysis=analysis, evidence=evidence,
                mark=mark, disclose=disclose, previous=previous, avoid_bodies=avoid_bodies,
                max_body=max_body, run=run,
            )
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
                "created_at, updated_at, disclosed) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'draft',0,?,?,?)",
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
                    int(disclose),
                ),
            )
            draft_id = int(cur.lastrowid)
        return self.get(draft_id)

    def _style(
        self, text: str, mark: str, key_phrases: Sequence[str], earlier: Sequence[str]
    ) -> list[str]:
        return style.style_issues(
            text, brand=self.rules.brand, disclosure=mark, key_phrases=key_phrases,
            earlier=earlier,
        )

    def _polish(
        self, llm: LLMClient, video_id: str, text: str, validation: Validation,
        issues: list[str], *, analysis: Analysis, evidence: Evidence, mark: str, disclose: bool,
        previous: Sequence[str], avoid_bodies: Sequence[str], max_body: int,
        run: dict[str, Any],
    ) -> tuple[str, Validation]:
        """통과한 초안을 한 번 더 다듬는다. 고친 글이 더 나쁘면(검사 실패·문제 늘어남) 원래 글."""
        rules = self.rules
        body = toggle_disclosure(text, mark, False) if mark else text
        info: dict[str, Any] = {"before": text, "issues_before": issues, "accepted": False}
        run["polish"] = info
        try:
            title = self.context.current(video_id).video.video.title
        except AppError:
            title = ""
        started = time.monotonic()
        try:
            data = llm.generate_json(
                system=prompts.polish_system(brand=rules.brand, disclosure=rules.disclosure),
                user=prompts.polish_user(
                    body=body, title=title, concern=analysis.concern,
                    key_phrases=analysis.key_phrases, issues=issues, max_body=max_body,
                ),
                schema=prompts.POLISH_SCHEMA,
                temperature=prompts.POLISH_TEMPERATURE,
                max_tokens=prompts.POLISH_MAX_TOKENS,
            )
        except AppError as exc:
            info.update(seconds=round(time.monotonic() - started, 1), error=exc.message)
            return text, validation
        info["seconds"] = round(time.monotonic() - started, 1)
        new_body = clean_body(data.get("body"), rules.disclosure)
        new_text = with_disclosure(new_body, mark)
        info["after"] = new_text
        if not new_body or new_text == text:
            return text, validation
        checked = self.checks.check(
            video_id, new_text, previous_texts=previous, evidence_quote=evidence.quote,
            disclose=disclose, key_phrases=analysis.checked_phrases, concern=analysis.concern,
        )
        new_issues = self._style(new_text, mark, analysis.key_phrases, avoid_bodies)
        info.update(failures_after=checked.failure_lines(), issues_after=new_issues)
        if not checked.passed or len(new_issues) > len(issues):
            return text, validation
        info["accepted"] = True
        return new_text, checked

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
        """사람이 고친 글. 같은 검사를 다시 거친다(화면의 검사 `check_basis`와 같은 기준).

        C1: 근거(V6)는 초안의 근거 구절, 핵심 말(V7)·고민 한 줄(V13)은 그 영상의 분석으로 본다.
        초안에 근거 구절이 없으면(예전 초안) 예전처럼 글에서 찾는다.
        """
        draft = self.get(draft_id)
        if draft.status == "superseded":
            raise AppError(ErrorKind.DRAFT_SUPERSEDED, detail=f"초안 {draft_id}")
        clean = unicodedata.normalize("NFC", text or "").strip()
        validation = self._recheck(
            draft.video_id, clean, draft.evidence_quote or None, disclose=draft.disclosed
        )
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

    def set_disclosure(self, draft_id: int, on: bool) -> Draft:
        """R3: 광고 표기를 켜거나 끈다. 저장된 글에서 표기만 붙이거나 떼고 다시 검사한다.

        모델을 부르지 않는다. 사람이 고친 표시(`edited_by_human`)와 근거 구절은 그대로 둔다.
        글이 바뀌면 승인은 풀린다(다시 [댓글 달기]를 누르면 그때 승인한다). 표기를 붙여 글자 수가
        넘치면 검사에 걸린 채로 저장된다(화면이 걸린 항목을 보인다).
        """
        draft = self.get(draft_id)
        if draft.status == "superseded":
            raise AppError(ErrorKind.DRAFT_SUPERSEDED, detail=f"초안 {draft_id}")
        on = bool(on)
        text = toggle_disclosure(draft.body, self.rules.disclosure, on)
        if on == draft.disclosed and text == draft.body:
            return draft
        validation = self._recheck(draft.video_id, text, draft.evidence_quote or None, disclose=on)
        changed = text != draft.body
        now = self._now()
        with db.session(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET body=?, disclosed=?, validation_json=?, passed=?, status=?, "
                "approved_at=?, updated_at=? WHERE id=?",
                (
                    text,
                    int(on),
                    _validation_to_json(validation),
                    int(validation.passed),
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
                reason=reason, draft_id=draft.id, disclosed=draft.disclosed,
            )
            raise
        self._record(
            "approve", "info", video_id=approved.video_id, comment_text=approved.body,
            reason="사람이 승인" + (" · 고친 글" if approved.edited_by_human else ""),
            draft_id=approved.id, disclosed=approved.disclosed,
        )
        return approved

    def _approve(self, draft: Draft) -> Draft:
        draft_id = draft.id
        if draft.status == "superseded":
            raise AppError(ErrorKind.DRAFT_SUPERSEDED, detail=f"초안 {draft_id}")
        validation = self._recheck(
            draft.video_id, draft.body, draft.evidence_quote or None, disclose=draft.disclosed
        )
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

    def last_tone(self, video_id: str | None = None) -> str:
        """직전에 승인한 다른 영상 초안의 말투 유형(없으면 빈 글)."""
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT tone_label FROM drafts WHERE status='approved' AND video_id IS NOT ? "
                "AND tone_label <> '' ORDER BY approved_at DESC, id DESC LIMIT 1",
                (video_id,),
            ).fetchone()
        return row["tone_label"] if row else ""

    def check_basis(self, video_id: str) -> tuple[str | None, tuple[str, ...], str]:
        """사람이 쓴 글을 검사할 기준(화면의 실시간 검사, C1): (근거 구절, 핵심 말, 고민 한 줄).

        근거 구절은 그 영상의 지금 초안(밀려나지 않은 것 중 최신)의 것. 분석이 없으면 빈 값 —
        그러면 V6은 글에서 근거를 찾고 V7은 제목·해시태그에서 핵심 말을 뽑는다.
        """
        self._check_id(video_id)
        current = next((d for d in self.list(video_id) if d.status != "superseded"), None)
        quote = current.evidence_quote if current and current.evidence_quote else None
        analysis = self.stored_analysis(video_id)
        if analysis is None:
            return quote, (), ""
        return quote, analysis.checked_phrases or (), analysis.concern

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

    def _recheck(
        self, video_id: str, text: str, quote: str | None, *, disclose: bool = True
    ) -> Validation:
        analysis = self.stored_analysis(video_id)
        return self.checks.check(
            video_id,
            text,
            previous_texts=self.previous_texts(video_id),
            evidence_quote=quote,
            disclose=disclose,
            key_phrases=analysis.checked_phrases if analysis else None,
            concern=analysis.concern if analysis else "",
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
            disclosed=bool(row["disclosed"]),
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

