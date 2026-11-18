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

AI 검수 한 번(2026-11-18, `review` · `app/analysis/review.py`): 규칙 검사를 통과한 초안을 AI가 한 번
더 읽는다(문법·뜻·이어짐·댓글 말투). 거짓이면 그 문제로 한 번만 다시 쓰게 하고(다시 쓴 글도 규칙·
다듬기 검사) 다시 검수한다. 결과는 `drafts.review_json`. 게시(승인)는 막지 않고, 검수 호출이
실패하면 초안을 그대로 두고 「검수 못 함」으로 남긴다. 설정 `comment.ai_review`(기본 켬).
"""

from __future__ import annotations

import json
import random
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app import db
from app.analysis import analyzer, story, style
from app.analysis import review as rv
from app.analysis.analyzer import Analysis, Evidence
from app.analysis.checking import CheckService
from app.analysis.context import ContextService
from app.analysis.validator import ASSIGNMENT_SAMPLE, Validation, normalize
from app.errors import AppError, ErrorKind
from app.llm import prompts
from app.llm import story_prompts as sp
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
# 다듬기 검사 S11(잇는 문장·까닭 둘 다 없음, 2026-11-18)을 모델 초안에 쓸지. 자동 테스트는
# `tests/conftest.py`가 끈다 — 그 전에 짠 가짜 초안들은 잇는 문장 없이 썼고 응답을 하나씩만
# 준비해서, 켜 두면 다시 쓰기 차례가 하나씩 밀린다. S11 자체의 시험은 켜고 본다.
BRIDGE_CHECK = True
# 다듬기 검사 S15(정해 준 운명원 조각과 다름·④ 통째 되풀이, 2026-11-18)를 모델 초안에 쓸지.
# S11과 같은 까닭으로 자동 테스트는 `tests/conftest.py`가 끈다(그 전에 짠 가짜 초안은 정해 준
# 조각을 모른다). 프롬프트의 조각 배정은 늘 켜져 있다. S15 자체의 시험은 켜고 본다.
PIECE_CHECK = True
# 다듬기 검사 S18~S20(알고 싶은 것 없음·잇는 문장과 같은 말·남의 마음 짐작, 2026-11-18 D)를 모델
# 초안에 쓸지. 같은 까닭으로 자동 테스트는 `tests/conftest.py`가 끈다. ⑤ 꼴 배정은 늘 켜져 있다
STORY_CHECK = True
# 길이 셈(2026-11-18 기획 담당): 운명원 대목 상한(`prompts.BRAND_CAP`)으로 조각을 정하고, 남는
# 글자 수를 ①·②에 숫자로 주고(모자라면 잇는 문장을 빼고), 다듬기 검사 S1 문턱을 112자로 두고,
# 마지막에 길이(V1)만 걸리면 잇는 문장을 덜어 본다. 그 전에 짠 가짜 초안·프롬프트 시험이 예전
# 배정을 보므로 자동 테스트는 `tests/conftest.py`가 끈다(켜는 것은 `length_plan_on`)
LENGTH_PLAN = True
# 이야기처럼 쓰기(2026-11-18 대표 결정): 설정 `comment.writer`와 상관없이 이 방식으로 쓴다(None이면
# 설정대로). 그 전에 짠 시험은 조각 맞추기로 돈다 — `tests/conftest.py`가 "pieces"로 두고, 이야기
# 방식 시험은 `story_writer`로 None(설정·생성자 값)을 쓴다
FORCE_WRITER: str | None = None
# 꺼내는 말·끝말을 돌려 쓸 때 보는 「보인 초안」 수(최근 것부터, 2026-11-17)
SHOWN_TEXTS = 30
DraftStatus = str  # 'draft' | 'approved' | 'superseded'

_QUOTES = "'\"‘’“”"
# 2026-11-18(기획 담당): 「현실적이네ㅋㅋ.」「답답하다 ㅠㅠ.」 — 사람은 자모 표기 뒤에 마침표를
# 찍지 않는다. 모델 글에서만 자모 바로 뒤의 마침표 하나를 지운다(말줄임 「...」은 그대로)
_JAMO_PERIOD = re.compile(r"(?<=[ㄱ-ㅎㅏ-ㅣ])\.(?!\.)")


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
    # AI 검수 한 번(2026-11-18): {"status": passed|rewritten|flagged|error|off|pending, "problems":
    # [...], "first": [...]} — 아직 안 했거나 규칙 검사에 걸린 초안·사람이 고친 글은 빈 dict
    review: dict[str, Any] | None = None
    # 2026-11-18 검수 기록: 다시 쓰기를 했으면 고치기 전 글·다시 쓴 글(버렸어도)·든 시간(ms)
    review_before: str = ""
    review_after: str = ""
    review_ms: int = 0
    rewrite_ms: int = 0

    @property
    def review_status(self) -> str:
        return str((self.review or {}).get("status") or "")


def clean_body(raw: Any, disclosure: str) -> str:
    """모델 본문 정리: 줄바꿈·연속 공백을 한 칸으로, 앞뒤 따옴표, 모델이 붙인 표기는 뗀다.

    「ㅋㅋ.」「ㅠㅠ.」처럼 자모 바로 뒤의 마침표 하나도 지운다(사람이 고친 글에는 쓰지 않는다)."""
    text = unicodedata.normalize("NFC", str(raw or ""))
    text = " ".join(text.split())
    if len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES and text[0] == text[-1]:
        text = text[1:-1].strip()
    while disclosure and text.startswith(disclosure):
        text = text[len(disclosure) :].lstrip(" :·-")
    text = _JAMO_PERIOD.sub("", text)
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


def _review_from_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


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
        rng: random.Random | None = None,
        ai_review: bool = True,
        writer: str = story.WRITER_STORY,
    ) -> None:
        self.context = context
        # 꺼내는 말·끝말을 권할 때 횟수가 같으면 무작위로(2026-11-17). 시험은 씨앗을 넣는다
        self.rng = rng if rng is not None else random.Random()
        self.checks = checks
        self._llm = llm
        self.db_path = db_path
        self.clock = clock
        self.brand_facts = tuple(brand_facts)
        self.max_attempts = max_attempts
        self.ledger = ledger
        self.disclose_default = bool(disclose_default)  # R3: 설정의 「광고 표기 기본값」
        self.polish = bool(polish)
        self.ai_review = bool(ai_review)  # 설정 comment.ai_review: 규칙 검사 뒤 AI 검수 한 번
        self.last_run: dict[str, Any] = {}  # 마지막 초안 만들기의 과정(시도별 글·다듬기)
        self._context_text = ""  # 지금 초안을 만드는 영상의 자료 글(다듬기 검사 S5)
        self._last_shown = ""  # 바로 앞에 보인 초안(다듬기 검사 S8)
        self._used_reasons: list[str] = []  # 앞서 보인 초안들의 ⑤ 까닭(다듬기 검사 S10)
        self._used_bridges: list[str] = []  # 앞서 보인 초안들의 잇는 문장(다듬기 검사 S12)
        self._pieces: prompts.Pieces | None = None  # 이번 초안의 운명원 대목 조각(S15)
        self._used_leads: list[str] = []  # 앞서 보인 초안들의 ④ 꺼내는 말(S15)
        self._want_bridge: bool | None = None  # 이번 초안에 잇는 문장을 넣을지(S16·S17)
        self._reason_kind: str | None = None  # 이번 초안 ⑤의 꼴(알고 싶은 것 등, S18)
        # 설정 comment.writer(2026-11-18): story(이야기처럼, 기본) | pieces(조각 맞추기, 예전)
        self._writer = writer if writer in story.WRITERS else story.WRITER_STORY
        self._shown: list[str] = []  # 앞서 보인 초안(이야기 방식 S4·「이미 쓴 글」)

    @property
    def writer(self) -> str:
        return FORCE_WRITER or self._writer

    @property
    def is_story(self) -> bool:
        return self.writer == story.WRITER_STORY

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
        self, video_id: str, *, avoid_quotes: Sequence[str] = (), disclose: bool | None = None,
        review: bool | None = None,
    ) -> Draft:
        """초안 하나를 만들어 저장한다. 같은 영상의 이전 'draft' 초안은 'superseded'가 된다.

        `disclose`: 광고 표기를 붙일지(어떤 영상이든). None이면 설정의 「광고 표기 기본값」.
        `review`: 규칙 검사를 통과하면 바로 AI 검수까지 할지. None이면 한다(설정이 켜져 있을
        때). False면 검수를 미뤄 두고(「pending」) 화면이 「다듬는 중」을 보이며 `review()`를 따로
        부른다.
        """
        self._check_id(video_id)
        disclose = self.disclose_default if disclose is None else bool(disclose)
        try:
            draft = self._generate(video_id, avoid_quotes, disclose)
        except AppError as exc:
            self._record("draft", "failure", video_id=video_id, reason=exc.message)
            raise
        if draft.passed:
            if not self.ai_review:
                draft = self._save_review(draft, {"status": rv.OFF})
            elif review is False:
                draft = self._save_review(draft, {"status": "pending"})
            else:
                draft = self.review(draft.id)
        if draft.passed:
            reason = f"규칙 검사 통과 · {draft.attempts}번째 시도"
            if self.last_run.get("polish", {}).get("accepted"):
                reason += " · 다듬음"
            label = rv.label(draft.review_status)
            if label:
                reason += f" · {label}"
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
        kit = self._prepare(video_id, analysis, disclose)
        # 2026-11-18 자료가 얇은 영상: 자막이 없으면 근거도 인기 댓글을 먼저(제목 낱말 되풀이 대신)
        evidence = analyzer.pick_evidence(
            analysis.evidence, avoid_quotes, prefer_comments=kit.thin
        )
        llm, rules, mark = kit.llm, kit.rules, kit.mark
        system, schema, max_body = kit.system, kit.schema, kit.max_body
        previous, avoid_bodies = kit.previous, kit.avoid_bodies

        # (실패 수, 다듬기 문제 수, 글, 말투, 검사, 차례, 다듬기 문제)
        best: tuple[int, int, str, str, Validation, int, list[str]] | None = None
        run: dict[str, Any] = {"attempts": [], "polish": {}}
        self.last_run = run
        failure_lines: list[str] = []
        previous_body = ""
        attempts = 0
        first_passed = False
        # 차례마다 덜어 낼 것(이야기 방식에서 길이로 세 번 다 걸리면 여운 → 전 차례로 한 번씩 더)
        steps = [0] * self.max_attempts
        long_fails = 0
        step = 0
        while step < len(steps):
            attempt = step + 1
            drop = steps[step]
            user = self._draft_prompt(
                kit, analysis, evidence, failure_lines, previous_body, drop=drop
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
                story=self.is_story,
            )
            fails = len(validation.failures)
            issues = self._style(text, mark, analysis.key_phrases, avoid_bodies)
            run["attempts"].append(
                {"body": text, "failures": validation.failure_lines(), "issues": issues,
                 **({"drop": drop} if drop else {})}
            )
            too_long = len(text) > rules.max_chars and any(
                c.code == "V1" for c in validation.failures)
            long_fails += too_long
            if best is None or (fails, len(issues)) < best[:2]:
                best = (fails, len(issues), text, tone, validation, attempt, issues)
            if validation.passed and attempt == 1:
                first_passed = True
            if validation.passed and not issues:
                break
            # 규칙 검사에 걸렸으면 그 문구로, 통과했지만 어색하면 다듬기 검사 문구로 다시 쓴다
            failure_lines = validation.failure_lines() + issues
            previous_body = body
            step += 1
            # 이야기 방식(2026-11-18): 지금까지 모두 길이로 걸렸으면 여운부터, 다음은 전을 빼고
            # 한 번 더 쓴다(덜어 낼 것이 남았을 때만)
            if (self.is_story and step == len(steps) and too_long and long_fails == step
                    and len(steps) < self.max_attempts + len(sp.DROP_LINES) - 1):
                steps.append(len(steps) - self.max_attempts + 1)

        assert best is not None
        _, _, text, tone, validation, _, issues = best
        if LENGTH_PLAN and not validation.passed and not self.is_story:
            # 길이(V1)만 걸렸으면 잇는 문장을 덜어 본다 — 모델을 다시 부르지 않는다(2026-11-18)
            trimmed = self._trim_bridge(text, validation)
            if trimmed:
                checked = self.checks.check(
                    video_id, trimmed, previous_texts=previous, evidence_quote=evidence.quote,
                    disclose=disclose, key_phrases=analysis.checked_phrases,
                    concern=analysis.concern, story=self.is_story,
                )
                if checked.passed:
                    run["trimmed"] = {"before": text, "after": trimmed}
                    text, validation = trimmed, checked
                    issues = self._style(text, mark, analysis.key_phrases, avoid_bodies)
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

    def _prepare(
        self, video_id: str, analysis: Analysis, disclose: bool, exclude: Draft | None = None
    ) -> SimpleNamespace:
        """초안 프롬프트에 넣을 것을 모은다(초안 만들기와 AI 검수 뒤 다시 쓰기가 함께 쓴다).

        `exclude`: AI 검수로 다시 쓰는 그 초안. 「같은 영상 앞 초안」·「보인 초안」에서 뺀다(자기
        글을 피하라고 하지 않게). 다듬기 검사가 볼 이 영상의 것(`_used_reasons` 등)도 여기서 정한다.
        """
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
        mine = [d for d in self.list(video_id) if exclude is None or d.id != exclude.id]
        avoid_bodies = [d.body for d in mine][:3]
        if self.is_story:
            return self._prepare_story(
                video_id, analysis, exclude, llm=llm, rules=rules, mark=mark, min_body=min_body,
                max_body=max_body, previous=previous, avoid_bodies=avoid_bodies,
            )
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
        # C1 손질 2회차: 운명원 꺼내는 말·끝말·첫 반응이 한 틀로 굳지 않게 덜 쓴 것을 권한다.
        # 2026-11-17(대표): 「이미 쓴 글」은 승인한 초안이 아니라 사람에게 보인 초안 전부로 센다
        # (초안을 보기만 하고 게시하지 않으면 기록이 늘지 않아 같은 말만 권했다).
        # V11 같은 규칙 검사의 기준(`previous`, 게시한 글)은 그대로 둔다
        shown = [t for t in self.shown_texts() if exclude is None or t != exclude.body]
        hearsay = prompts.hearsay_choices(
            rules.brand, shown, n=3, avoid=avoid_bodies, rng=self.rng)
        endings = prompts.ending_choices(shown, n=3, avoid=avoid_bodies, rng=self.rng)
        used_openings = [prompts.opening_sentence(t, disclosure=rules.disclosure) for t in shown]

        thin = False  # 자막이 없는 영상(제목·설명·인기 댓글만, 2026-11-18)
        try:  # S5(영상 숫자를 내 것으로)·S13(해시태그 낱말)을 볼 영상 자료 글
            current = self.context.current(video_id)
            context_text = self.context.search_text(current)
            thin = not current.transcript_text
        except AppError:
            context_text = ""
        self._context_text = context_text
        # ⑤의 까닭(2026-11-18): 같은 영상 초안 가운데 적어도 하나는 이 영상 고민에서 온 까닭을
        # 넣게 한다. 앞 초안에 이미 있으면 까닭 없는 본보기 꼴도 된다고 한다(전부 강제하지 않음)
        want_reason = not any(prompts.intent_reason(b, rules.brand) for b in avoid_bodies)
        # ② 잇는 문장 넣기(2026-11-18 기획 담당 C): 코드가 정한다 — 약 3개 중 2개, 같은 영상 초안
        # 끼리는 넣은 것·안 넣은 것을 섞는다. 안 넣으면 까닭으로 잇는다. AI 검수 뒤 다시 쓸 때는
        # 그 초안 그대로
        if exclude is not None:
            want_bridge = bool(prompts.bridge_sentence(exclude.body, rules.brand))
        else:
            want_bridge = prompts.assign_bridge(rules.brand, shown, avoid_bodies)
        if not want_bridge:
            want_reason = True
        self._want_bridge = want_bridge
        # ⑤의 꼴(2026-11-18 기획 담당 D-1): 셋 중 둘은 「저도 + 사주로 알고 싶은 것 + 보러 가겠다는
        # 말」, 나머지는 상태 까닭·까닭 없음(잇는 문장이 없으면 까닭은 꼭). 다시 쓸 때는 그 초안
        # 그대로
        # STORY_CHECK을 끈 예전 테스트는 예전 배정(까닭 넣기/빼기)만 본다
        if not STORY_CHECK:
            kind = None
        elif exclude is not None:
            kind = prompts.reason_kind(exclude.body, rules.brand)
            kept = prompts.pieces_of(exclude.body, rules.brand)
            if kept is not None and kept.action in prompts.WISH_ACTIONS:
                kind = prompts.REASON_WISH
        else:
            kind = prompts.assign_reason(rules.brand, shown, avoid_bodies, bridge=want_bridge)
        if kind == prompts.REASON_NONE and (not want_bridge or want_reason):
            kind = prompts.REASON_STATE
        if kind is not None:
            want_reason = kind != prompts.REASON_NONE
        self._reason_kind = kind
        # 2026-11-18: 앞서 보인 초안(다른 영상 포함, 꺼내는 말을 세는 범위와 같게)의 까닭은 피한다
        self._used_reasons = list(dict.fromkeys(
            r for r in (prompts.intent_reason(t, rules.brand) for t in [*avoid_bodies, *shown]) if r
        ))
        # ② 잇는 문장(2026-11-18): 앞서 보인 초안(다른 영상 포함)에 쓴 잇는 문장은 피한다
        self._used_bridges = list(dict.fromkeys(
            b for b in (prompts.bridge_sentence(t, rules.brand) for t in [*avoid_bodies, *shown])
            if b
        ))
        # 2026-11-18 조각 배정: 운명원 대목의 때·연애 사주·세기 말·평판·들은 꼴·끝말을 코드가
        # 덜 쓴 것부터 정해 준다. AI 검수 뒤 다시 쓸 때는 앞 초안의 조각 그대로(같은 배정)
        keep = prompts.pieces_of(exclude.body, rules.brand) if exclude is not None else None
        cap = None
        if LENGTH_PLAN:  # 잇는 문장이 있으면 짧은 꼴, 없으면 긴 꼴도(2026-11-18 길이 셈)
            cap = prompts.BRAND_CAP if want_bridge else prompts.BRAND_CAP_LONG
        pieces = prompts.assign_pieces(
            rules.brand, shown, avoid=avoid_bodies, rng=self.rng, keep=keep,
            wish=kind == prompts.REASON_WISH, cap=cap, reason_kind=kind)
        self._pieces = pieces
        plan = None
        if LENGTH_PLAN:
            mark_len = len(mark) + 1 if mark else 0
            plan = prompts.length_plan(pieces, rules.brand, mark_len=mark_len,
                                       reason_kind=kind, bridge=want_bridge)
            if want_bridge and not plan.bridge:  # ①과 잇는 문장에 남는 글자가 모자라다
                want_bridge = False
                self._want_bridge = False
                if kind == prompts.REASON_NONE:
                    kind = prompts.REASON_STATE
                    self._reason_kind = kind
                want_reason = True
                plan = prompts.length_plan(pieces, rules.brand, mark_len=mark_len,
                                           reason_kind=kind, bridge=False)
        self._used_leads = [x for x in (prompts.lead_part(t, rules.brand)
                                        for t in [*avoid_bodies, *shown]) if x]
        # S8: 바로 앞에 보인 초안과 같은 본보기를 그대로 옮기지 않게
        self._last_shown = shown[0] if shown else ""
        return SimpleNamespace(
            llm=llm, rules=rules, mark=mark, min_body=min_body, max_body=max_body, system=system,
            previous=previous, avoid_bodies=avoid_bodies, avoid_phrases=avoid_phrases,
            avoid_tones=avoid_tones, tones=tones, schema=schema, used_closings=used_closings,
            hearsay=hearsay, endings=endings, used_openings=used_openings, want_reason=want_reason,
            thin=thin, pieces=pieces, want_bridge=want_bridge, reason_kind=kind, plan=plan,
        )

    def _prepare_story(
        self, video_id: str, analysis: Analysis, exclude: Draft | None, **base: Any
    ) -> SimpleNamespace:
        """이야기 방식(2026-11-18)의 준비: 「이미 쓴 글」과 영상 자료만. 조각·말투·잇는 문장·까닭·
        글쓴이 처지는 정하지 않는다(처지도 AI가 영상을 보고 정한다)."""
        rules = base["rules"]
        shown = [t for t in self.shown_texts() if exclude is None or t != exclude.body]
        thin, title, context_text = False, "", ""
        try:
            current = self.context.current(video_id)
            context_text = self.context.search_text(current)
            thin = not current.transcript_text
            title = current.video.video.title
        except AppError:
            pass
        self._context_text = context_text
        self._shown = shown
        self._last_shown = shown[0] if shown else ""
        system = sp.story_system(
            brand=rules.brand, disclosure=rules.disclosure, facts=self.brand_facts,
            sample=ASSIGNMENT_SAMPLE,
        )
        return SimpleNamespace(
            **base, system=system, schema=prompts.draft_schema(prompts.TONE_LABELS),
            shown=shown, thin=thin, title=title,
        )

    def _trim_bridge(self, text: str, validation: Validation) -> str:
        """길이(V1)만 넘친 글에서 잇는 문장을 뺀 글(뺄 것이 없거나 다른 검사에도 걸렸으면 빈 글)."""
        if any(c.code != "V1" for c in validation.failures) or len(text) <= self.rules.max_chars:
            return ""
        bridge = prompts.bridge_sentence(text, self.rules.brand)
        if not bridge:
            return ""
        return re.sub(r"\s{2,}", " ", text.replace(bridge, "", 1)).strip()

    def _draft_prompt(
        self, kit: SimpleNamespace, analysis: Analysis, evidence: Evidence,
        failure_lines: Sequence[str], previous_body: str, *, drop: int = 0,
    ) -> str:
        if self.is_story:
            rules = kit.rules
            plain = [toggle_disclosure(t, rules.disclosure, False) for t in kit.shown
                     if t not in kit.avoid_bodies]
            return sp.story_user(
                analysis=analysis.to_prompt(), title=kit.title, quote=evidence.quote,
                source=evidence.source, key_phrases=analysis.key_phrases,
                mark_len=len(kit.mark) + 1 if kit.mark else 0, max_body=kit.max_body,
                brand=rules.brand, shown=plain,
                avoid_bodies=[toggle_disclosure(b, rules.disclosure, False)
                              for b in kit.avoid_bodies],
                failure_lines=failure_lines, previous_body=previous_body, drop=drop,
                thin=kit.thin,
            )
        return prompts.draft_user(
            analysis=analysis.to_prompt(),
            quote=evidence.quote,
            source=evidence.source,
            min_body=kit.min_body,
            max_body=kit.max_body,
            key_phrases=analysis.key_phrases,
            tones=kit.tones,
            avoid_tones=[t for t in kit.avoid_tones if t and t not in kit.tones],
            max_chars=kit.rules.max_chars,
            brand=kit.rules.brand,
            hearsay=kit.hearsay,
            endings=kit.endings,
            used_openings=kit.used_openings,
            failure_lines=failure_lines,
            previous_body=previous_body,
            avoid_bodies=kit.avoid_bodies,
            used_closings=kit.used_closings,
            avoid_phrases=kit.avoid_phrases,
            last_model=prompts.copied_model(self._last_shown) if self._last_shown else -1,
            reason=kit.want_reason,
            used_reasons=self._used_reasons,
            bridge=kit.want_bridge,
            used_bridges=self._used_bridges,
            thin=kit.thin,
            pieces=kit.pieces,
            reason_kind=kit.reason_kind,
            plan=kit.plan,
        )

    def _style(
        self, text: str, mark: str, key_phrases: Sequence[str], earlier: Sequence[str]
    ) -> list[str]:
        if self.is_story:  # 이야기 방식: S1·S4·S5·S9·S13만(짜임 검사는 보지 않는다)
            return story.story_issues(
                text, brand=self.rules.brand, disclosure=self.rules.disclosure,
                max_total=prompts.SOFT_MAX_DRAFT, earlier=earlier,
                shown=[t for t in self._shown if t not in earlier], context=self._context_text,
            )
        return style.style_issues(
            text, brand=self.rules.brand, disclosure=mark, key_phrases=key_phrases,
            earlier=earlier, context=self._context_text,
            last_shown=self._last_shown, used_reasons=self._used_reasons,
            need_bridge=BRIDGE_CHECK,
            used_bridges=[*self._used_bridges, *prompts.EXAMPLE_BRIDGES],
            pieces=self._pieces if PIECE_CHECK else None, used_leads=self._used_leads,
            bridge_wanted=self._want_bridge if BRIDGE_CHECK else None,
            reason_wanted=self._reason_kind if STORY_CHECK else None,
            max_total=prompts.SOFT_MAX_DRAFT if LENGTH_PLAN else style.SOFT_MAX_TOTAL,
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
            story=self.is_story,
        )
        new_issues = self._style(new_text, mark, analysis.key_phrases, avoid_bodies)
        info.update(failures_after=checked.failure_lines(), issues_after=new_issues)
        if not checked.passed or len(new_issues) > len(issues):
            return text, validation
        info["accepted"] = True
        return new_text, checked

    # ------------------------------------------------------------ AI 검수 한 번(2026-11-18)

    def review(self, draft_id: int) -> Draft:
        """규칙 검사를 통과한 모델 초안을 AI가 한 번 더 읽는다(`app/analysis/review.py`).

        검수할 것이 없으면(설정을 끔·이미 함·규칙 검사에 걸림·사람이 고침·승인됨) 그대로 돌려준다.
        거짓이면 그 문제로 **한 번만** 다시 쓰게 하고, 다시 쓴 글이 규칙 검사를 통과하고 다듬기
        검사 문제가 늘지 않을 때만 그 글로 바꿔 다시 검수한다. 어떤 경우에도 예외를 내지 않는다
        (검수 때문에 초안 만들기가 실패하지 않게). 과정은 `last_run["review"]`에 남는다.
        """
        draft = self.get(draft_id)
        if not self.ai_review:
            return draft if draft.review_status else self._save_review(draft, {"status": rv.OFF})
        if (draft.status != "draft" or not draft.passed or draft.edited_by_human
                or draft.review_status not in ("", "pending")):
            return draft
        started = time.monotonic()
        info: dict[str, Any] = {"review_ms": 0, "rewrite_ms": 0}
        self.last_run["review"] = info
        try:
            result, text, validation = self._review(draft, info)
        except Exception as exc:  # noqa: BLE001 — 검수는 초안 만들기를 절대 막지 않는다
            info["error"] = f"{type(exc).__name__}: {exc}"
            result, text, validation = {"status": rv.ERROR, "problems": []}, None, None
        result["seconds"] = info["seconds"] = round(time.monotonic() - started, 1)
        info["status"] = result["status"]
        rewrite = info.get("rewrite") or {}
        if rewrite:
            result["kept"] = text is not None
        if self.is_story:
            # 맥락 일치 검증(2026-11-18): 네 판단과 벗어난 문장을 초안마다 남긴다(남은 글의 것)
            last = info.get("second") if text is not None else info.get("first")
            checks = dict((last or {}).get("checks") or {})
            result.update(story=True, checks=checks, drift=str(checks.get("drift") or ""))
            if "first" in info and "second" in info:
                result["first_checks"] = dict(info["first"].get("checks") or {})
        return self._save_review(
            draft, result, text=text, validation=validation,
            before=draft.body if rewrite else "", after=str(rewrite.get("body") or ""),
            review_ms=int(info["review_ms"]), rewrite_ms=int(info["rewrite_ms"]),
        )

    def _review(
        self, draft: Draft, info: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None, Validation | None]:
        """(검수 결과, 바꿀 글 또는 None, 그 글의 검사 또는 None)."""
        rules = self.rules
        mark = rules.disclosure if draft.disclosed else ""
        analysis = self.stored_analysis(draft.video_id)
        concern = analysis.concern if analysis else ""
        phrases = list(analysis.key_phrases) if analysis else []
        try:
            title = self.context.current(draft.video_id).video.video.title
        except AppError:
            title = ""
        is_story = self.is_story
        thin: bool | None = None
        if is_story:
            try:
                thin = not self.context.current(draft.video_id).transcript_text
            except AppError:
                thin = None
        system = rv.review_system(brand=rules.brand, story=is_story)
        llm = self._llm()

        def ask(text: str) -> tuple[bool, list[str]] | None:
            body = toggle_disclosure(text, rules.disclosure, False)
            started = time.monotonic()
            # 이야기 방식일 때만 story를 넘긴다(예전 꼴의 가짜 ask도 그대로 받게)
            extra = {"story": True} if is_story else {}
            try:
                return rv.ask(llm, system=system, **extra, user=rv.review_user(
                    body=body, title=title, concern=concern, key_phrases=phrases,
                    evidence=draft.evidence_quote, story=is_story,
                    source=prompts.SOURCE_LABELS.get(draft.evidence_source, "")
                    if is_story else "",
                    topic=analysis.topic if analysis and is_story else "", thin=thin))
            except (AppError, ValueError) as exc:
                info.setdefault("errors", []).append(str(getattr(exc, "message", exc)))
                return None
            finally:
                info["review_ms"] += int((time.monotonic() - started) * 1000)

        first = ask(draft.body)
        if first is None:
            return {"status": rv.ERROR, "problems": []}, None, None
        ok, problems = first
        info["first"] = {"ok": ok, "problems": problems, **_checks_of(first)}
        if ok:
            return {"status": rv.PASSED, "problems": []}, None, None
        flagged = {"status": rv.FLAGGED, "problems": problems, "first": problems}
        if analysis is None:
            return flagged, None, None
        # 한 번만 다시 쓴다: 같은 근거 구절, 같은 프롬프트에 검수 문제를 「걸린 항목」으로
        evidence = Evidence(quote=draft.evidence_quote, source=draft.evidence_source)
        kit = self._prepare(draft.video_id, analysis, draft.disclosed, exclude=draft)
        before = self._style(draft.body, mark, analysis.key_phrases, kit.avoid_bodies)
        previous_body = toggle_disclosure(draft.body, rules.disclosure, False)
        user = self._draft_prompt(
            kit, analysis, evidence, rv.retry_lines(problems, story=is_story), previous_body
        )
        started = time.monotonic()
        try:
            data = kit.llm.generate_json(
                system=kit.system, user=user, schema=kit.schema,
                temperature=prompts.DRAFT_TEMPERATURE, max_tokens=prompts.DRAFT_MAX_TOKENS,
            )
        except AppError as exc:
            info["rewrite_error"] = exc.message
            return flagged, None, None  # 다시 쓰기 실패·시간 초과: 앞 초안 그대로
        finally:
            info["rewrite_ms"] += int((time.monotonic() - started) * 1000)
        body = clean_body(data.get("body") if isinstance(data, dict) else None, rules.disclosure)
        text = with_disclosure(body, mark)
        validation = self.checks.check(
            draft.video_id, text, previous_texts=kit.previous, evidence_quote=evidence.quote,
            disclose=draft.disclosed, key_phrases=analysis.checked_phrases,
            concern=analysis.concern, story=self.is_story,
        )
        issues = self._style(text, mark, analysis.key_phrases, kit.avoid_bodies)
        info["rewrite"] = {"body": text, "failures": validation.failure_lines(),
                           "issues": issues, "issues_before": before}
        if not body or text == draft.body or not validation.passed or len(issues) > len(before):
            return flagged, None, None  # 다시 쓴 글이 더 나쁘면 원래 글을 둔다
        second = ask(text)
        if second is None:
            # 두 번째 검수 실패·시간 초과: 검수를 통과했는지 모르는 글로 바꾸지 않는다 — 앞 초안
            return {"status": rv.ERROR, "problems": [], "first": problems}, None, None
        ok2, problems2 = second
        info["second"] = {"ok": ok2, "problems": problems2, **_checks_of(second)}
        if ok2:
            return {"status": rv.REWRITTEN, "problems": [], "first": problems}, text, validation
        return {"status": rv.FLAGGED, "problems": problems2, "first": problems}, text, validation

    def _save_review(
        self, draft: Draft, result: dict[str, Any], *, text: str | None = None,
        validation: Validation | None = None, before: str = "", after: str = "",
        review_ms: int = 0, rewrite_ms: int = 0,
    ) -> Draft:
        """검수 결과를 남긴다. `text`가 있으면 다시 쓴 글로 바꾼다(모델에게 쓰게 한 횟수 +1).

        규칙 검사를 통과한 초안이 통과 못 한 글로 바뀌지 않게 여기서 한 번 더 막는다(다시 쓴 글이
        통과하지 못했으면 바꾸지 않고 `kept`를 거짓으로)."""
        now = self._now()
        if text is not None and (validation is None or not validation.passed):
            text, validation = None, None
            if "kept" in result:
                result = {**result, "kept": False}
        raw = json.dumps(result, ensure_ascii=False)
        trace = (before, after, int(review_ms), int(rewrite_ms))
        with db.session(self.db_path) as conn:
            if text is not None and validation is not None:
                conn.execute(
                    "UPDATE drafts SET body=?, validation_json=?, passed=?, attempts=attempts+1, "
                    "review_json=?, review_before=?, review_after=?, review_ms=?, rewrite_ms=?, "
                    "updated_at=? WHERE id=?",
                    (text, _validation_to_json(validation), int(validation.passed), raw, *trace,
                     now, draft.id),
                )
            else:
                conn.execute(
                    "UPDATE drafts SET review_json=?, review_before=?, review_after=?, "
                    "review_ms=?, rewrite_ms=?, updated_at=? WHERE id=?",
                    (raw, *trace, now, draft.id),
                )
        return self.get(draft.id)

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
                "passed=?, edited_by_human=?, status=?, approved_at=?, updated_at=?, "
                # 사람이 글을 바꾸면 AI 검수 결과는 그 글의 것이 아니다(지운다)
                "review_json=CASE WHEN ? THEN '' ELSE review_json END WHERE id=?",
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
                    int(changed),
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

    def shown_texts(self, limit: int = SHOWN_TEXTS) -> list[str]:
        """사람에게 보인 초안 전부(승인 여부·영상과 상관없이, 최신이 앞, 최근 `limit`개).

        꺼내는 말·끝말·첫 반응을 돌려 쓰는 데만 쓴다(2026-11-17). 규칙 검사(V11)의 기준은
        `previous_texts`(승인·게시한 글) 그대로다."""
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT body FROM drafts WHERE status IN ('draft', 'superseded', 'approved') "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return list(dict.fromkeys(r["body"] for r in rows))

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
            story=self.is_story,
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
            review=_review_from_json(row["review_json"]) if "review_json" in row.keys() else {},
            **_review_trace(row),
        )


def _review_trace(row) -> dict[str, Any]:
    keys = row.keys()
    if "review_before" not in keys:
        return {}
    return {"review_before": row["review_before"], "review_after": row["review_after"],
            "review_ms": int(row["review_ms"]), "rewrite_ms": int(row["rewrite_ms"])}


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


def _checks_of(verdict: Any) -> dict[str, Any]:
    """맥락 일치 검증의 네 판단(이야기 방식 답에만 있다)."""
    checks = getattr(verdict, "checks", None)
    return {"checks": dict(checks)} if checks else {}
