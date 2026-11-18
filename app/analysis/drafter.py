"""댓글 초안 서비스(PLAYBOOK 5단계, docs/COMMENT_REFACTOR.md 6절).

분석 → 쓰기 → 규칙 검사 → AI 검수.

초안 만들기 흐름(2026-11-18 대표 최종 지시서)
1. 코드가 말 높임(`prompts.VOICES`)·운명원을 들은 경로(`prompts.HEARD_FROM`)를 무작위로 뽑고,
   [짚을 내용]을 고른다 — 분석기 근거를 자막 → 제목·설명 → 인기 댓글 순으로(댓글은 자막·제목·
   설명에서 고민을 찾지 못했을 때만). 분석이 연애 고민을 찾지 못하면(`no_love_concern`) 멈춘다.
2. AI가 `mood`·`body`·`wish`·`used_quote`를 쓴다. 광고 표기 `[광고] `는 코드가 앞에 붙인다
   (R3: 켬/끔은 모든 영상에서, `disclose`가 비면 설정의 「광고 표기 기본값」).
3. 규칙 검사(`CheckService.check()` = `validate()`). 걸리면 걸린 사유만 알려 주고 같은 말 높임·들은
   경로로 다시 쓴다(다시 쓰기는 최대 2번).
4. 끝까지 걸리면 걸린 것이 가장 적은 글을 저장하고 걸린 항목을 표시한다(사람이 고친다).
5. [다른 댓글 만들기]는 직전 초안과 다른 말 높임·들은 경로 조합을 뽑고, 같은 영상에서 이미 짚은
   구절과 앞 댓글의 `wish`를 요청 글에 넣는다.

저장: 코드가 뽑은 두 값과 AI의 기분은 `drafts.tone_label`에 " / "로 이어 저장한다(다시 쓸 때 여기서
읽는다). `used_quote`는 `evidence_quote`, 그 출처는 `evidence_source`. `wish`와 AI가 본 근거
(`basis`)는 DB 칸을 늘리지 않고 `review_json`에 함께 둔다.

AI 검수 한 번(`review` · `app/analysis/review.py`): 규칙 검사를 통과한 초안을 AI가 세 가지로 읽는다.
거짓이면 같은 말 높임·들은 경로로 한 번만 다시 쓰고 다시 검수한다. 다시 쓴 글이 규칙 검사에 걸리면
앞 글을 둔다. 검수는 게시를 막지 않고, 호출이 실패하면 「검수 못 함」으로 남긴다. 설정
`comment.ai_review`(기본 켬).

검사에 쓰는 이전 글(V11)은 **다른 영상에서 승인·게시한 글**이다. 승인은 지금 글을 다시 검사한 뒤
통과한 것만 받는다. 승인하면 같은 영상의 다른 초안은 모두 `superseded`가 된다(영상당 승인
초안 하나).

7단계: 분석·초안 생성·승인을 작업 기록(`runs`)에 남긴다(`ledger`를 넣었을 때).
LLM은 `LLMClient` 규격만 쓴다(`llm` 인자는 그때그때 공급자를 돌려주는 함수).
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
from typing import Any

from app import db
from app.analysis import analyzer
from app.analysis import review as rv
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

MAX_ATTEMPTS = 3  # 처음 쓰기 + 다시 쓰기 2번
DraftStatus = str  # 'draft' | 'approved' | 'superseded'
TONE_SEP = " / "  # tone_label: 말 높임 / 들은 경로 / 기분
# [짚을 내용]을 고르는 출처 순서(지시서 4절). 댓글은 앞의 셋에 근거가 없을 때만
EVIDENCE_GROUPS = (("transcript",), ("title", "description"), ("comment",))

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
    # [...], "first": [...], "wish_kind": 갈래, "wish": 알고 싶은 것, "basis": AI가 본 근거}
    # — 검수를 안 한 초안은 status가 없다. 사람이 고친 글은 빈 dict
    review: dict[str, Any] | None = None
    # 2026-11-18 검수 기록: 다시 쓰기를 했으면 고치기 전 글·다시 쓴 글(버렸어도)·든 시간(ms)
    review_before: str = ""
    review_after: str = ""
    review_ms: int = 0
    rewrite_ms: int = 0

    @property
    def review_status(self) -> str:
        return str((self.review or {}).get("status") or "")

    @property
    def wish(self) -> str:
        """AI가 적어 낸 「운명원에서 알고 싶은 것」(`review_json`에 함께 둔다, 지시서 3절)."""
        return str((self.review or {}).get("wish") or "")


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



@dataclass(frozen=True)
class Voice:
    """코드가 뽑는 두 값(지시서 3절)."""

    voice: str  # 말 높임
    heard: str  # 운명원을 들은 경로

    def label(self, mood: str = "") -> str:
        return TONE_SEP.join(x for x in (self.voice, self.heard, mood) if x)


def voice_of(tone_label: str) -> Voice | None:
    """저장된 `tone_label`에서 말 높임·들은 경로를 읽는다(예전 초안이면 None)."""
    parts = [p.strip() for p in (tone_label or "").split(TONE_SEP)]
    if len(parts) >= 2 and parts[0] in prompts.VOICES and parts[1] in prompts.HEARD_FROM:
        return Voice(parts[0], parts[1])
    return None


def mood_of(tone_label: str) -> str:
    parts = [p.strip() for p in (tone_label or "").split(TONE_SEP)]
    return parts[2] if len(parts) >= 3 and voice_of(tone_label) else ""


def pick_voice(
    rng: random.Random,
    avoid: Voice | None = None,
    recent: Sequence[Voice] = (),
) -> Voice:
    """말 높임·들은 경로를 무작위로. `avoid`(같은 영상 직전 초안)와 같은 조합은 뽑지 않는다.

    `recent`: 다른 영상의 최근 초안(새것부터) — 2026-11-18 대표 목표(운명원 말하기가 모두 같으면
    안 됨)로 말 높임은 직전과 번갈아, 들은 경로는 최근 두 개와 다르게 뽑는다
    (남는 게 없으면 그만큼 푼다)."""
    combos = [Voice(v, h) for v in prompts.VOICES for h in prompts.HEARD_FROM]
    if avoid is not None:
        combos = [c for c in combos if c != avoid] or combos
    if recent:
        combos = [c for c in combos if c.voice != recent[0].voice] or combos
        heard = {v.heard for v in recent[:2]}
        combos = ([c for c in combos if c.heard not in heard]
                  or [c for c in combos if c.heard != recent[0].heard] or combos)
    return rng.choice(combos)


RECENT_BODIES = 3  # 요청 글에 넣는 「다른 영상에 최근 단 댓글」 수(2026-11-18)
RECENT_SITUATIONS = 8  # 그 아래 「이미 쓴 처지」 수(12회차: 본문 셋만으로는 처지가 겹쳤다)


def situation_of(review_json: str | None) -> str:
    """초안 `review_json`에 남긴 처지(AI가 적은 `situation`). 없거나 못 읽으면 빈 글."""
    try:
        data = json.loads(review_json or "{}")
    except ValueError:
        return ""
    return str(data.get("situation") or "") if isinstance(data, dict) else ""


def saying_of(body: str, brand: str) -> int | None:
    """본문이 쓴 들은 말 계열(`prompts.SAYINGS`의 번호). 알아볼 낱말이 없으면 None."""
    for i, (_, keys) in enumerate(prompts.SAYINGS):
        if any(k.format(brand=brand) in body for k in keys):
            return i
    return None


def pick_saying(rng: random.Random, brand: str, recent_bodies: Sequence[str] = ()) -> str:
    """들은 말의 요지 하나. 다른 영상 최근 댓글 두 개가 쓴 계열은 피한다(다 쓰였으면 아무거나)."""
    used = {saying_of(b, brand) for b in recent_bodies[:2]}
    idx = [i for i in range(len(prompts.SAYINGS)) if i not in used] or list(
        range(len(prompts.SAYINGS)))
    return prompts.SAYINGS[rng.choice(idx)][0].format(brand=brand)


# 2026-11-19 대표: 짧은 맞장구·감탄·앞뒤 없이는 뜻을 모를 구절을 근거로 고르지 않는다.
# 글자 수만이 아니라 영상 주제·고민과 겹치는지를 본다(낱말 목록은 두지 않는다).
THIN_CHARS = 8  # 이보다 짧은 구절(한글·영문·숫자 글자 수)은 근거로 쓰기에 얇다
LONE_CHARS = 14  # 주제·고민과 겹치는 데가 하나도 없으면 이 길이까지는 얇다고 본다


def _letters(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _pairs(text: str) -> set[str]:
    t = _letters(text).lower()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def topic_overlap(quote: str, topic: str) -> int:
    """구절과 영상 주제 글(분석의 주제·고민·핵심 말·제목)이 함께 가진 두 글자 묶음 수."""
    return len(_pairs(quote) & _pairs(topic)) if topic else 0


def thin_quote(quote: str, topic: str) -> bool:
    """근거로 쓰기에 얇은 구절: 아주 짧거나, 꽤 짧은데 영상 주제·고민과 겹치는 데가 없음."""
    n = len(_letters(quote))
    return n < THIN_CHARS or (n < LONE_CHARS and topic_overlap(quote, topic) == 0)


def pick_evidence(
    evidence: Sequence[Evidence], avoid_quotes: Sequence[str] = (), *, topic: str = "",
    title: str = "",
) -> Evidence:
    """[짚을 내용]의 근거 하나: 자막 → 제목·설명 → 인기 댓글 순으로 근거가 있는 첫 무리에서,
    이미 짚은 구절이 아닌 것(모두 짚었으면 그 무리의 첫 것). 근거가 없으면 AppError.

    `topic`(분석의 주제·고민·핵심 말·제목)을 주면(2026-11-19): 얇은 구절(`thin_quote`)은 빼고,
    주제와 많이 겹치는 구절을 먼저 고른다. 자막·제목·설명에 쓸 만한 근거가 없으면 확인된 제목
    (`title`)을 근거로 쓴다(자막·제목·설명 근거가 있었는데 모두 얇았을 때만 — 인기 댓글 근거만
    있는 영상은 예전처럼 댓글). 다 얇으면 예전처럼 고른다."""
    avoid = {normalize(q) for q in avoid_quotes if q}
    dropped = False  # 자막·제목·설명 근거를 얇아서 뺐는지
    for group in EVIDENCE_GROUPS:
        if topic and dropped and group == EVIDENCE_GROUPS[-1] and title.strip():
            return Evidence(" ".join(title.split()), "title")  # 자막·제목·설명이 다 얇음
        items = sorted((e for e in evidence if e.source in group),
                       key=lambda e: group.index(e.source))  # 제목 다음 설명(같으면 모델 순서)
        if topic:
            kept = [e for e in items if not thin_quote(e.quote, topic)]
            dropped = dropped or len(kept) < len(items)
            items = sorted(kept, key=lambda e: -topic_overlap(e.quote, topic))
        if items:
            fresh = [e for e in items if normalize(e.quote) not in avoid]
            return (fresh or items)[0]
    if topic:
        return pick_evidence(evidence, avoid_quotes)  # 다 얇으면 예전처럼
    if evidence:
        return evidence[0]
    raise AppError(ErrorKind.NO_LOVE_CONCERN, detail="근거 구절이 없음")


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
        rng: random.Random | None = None,
        ai_review: bool = True,
    ) -> None:
        self.context = context
        self.rng = rng if rng is not None else random.Random()  # 시험은 씨앗을 넣는다
        self.checks = checks
        self._llm = llm
        self.db_path = db_path
        self.clock = clock
        self.brand_facts = tuple(brand_facts)
        self.max_attempts = max(1, int(max_attempts))
        self.ledger = ledger
        self.disclose_default = bool(disclose_default)  # R3: 설정의 「광고 표기 기본값」
        self.ai_review = bool(ai_review)  # 설정 comment.ai_review: 규칙 검사 뒤 AI 검수 한 번
        self.last_run: dict[str, Any] = {}  # 마지막 초안 만들기의 과정(시도별 글·검수)

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
        때). False면 검수를 미뤄 두고(「pending」) 화면이 `review()`를 따로 부른다.
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
            analysis = self.analyze(video_id)  # 예전 분석은 다시 한다
        mine = self.list(video_id)
        last = next((voice_of(d.tone_label) for d in mine if voice_of(d.tone_label)), None)
        recent = [v for d in self._recent_elsewhere(video_id) if (v := voice_of(d["tone_label"]))]
        voice = pick_voice(self.rng, avoid=last, recent=recent)
        used = list(dict.fromkeys([*avoid_quotes, *(d.evidence_quote for d in mine)]))
        title = ""
        try:
            title = self.context.current(video_id).video.video.title or ""
        except AppError:
            pass
        topic = " ".join([analysis.topic, analysis.concern, *analysis.key_phrases, title])
        evidence = pick_evidence(analysis.evidence, used, topic=topic, title=title)
        kit = self._kit(video_id, analysis.concern, evidence, voice, disclose, others=mine)
        llm = kit["llm"]

        best: tuple[int, int, str, dict[str, Any], Validation] | None = None
        run: dict[str, Any] = {
            "voice": voice.voice, "heard": voice.heard, "said": kit["said"],
            "basis": evidence.to_dict(),
            "attempts": [],
        }
        self.last_run = run
        failure_lines: list[str] = []
        previous_body = ""
        attempts = 0
        first_passed = False
        for attempt in range(1, self.max_attempts + 1):
            try:
                text, data, validation = self._write(
                    kit, failure_lines=failure_lines, previous_body=previous_body
                )
            except AppError:
                if best is None:
                    raise
                break  # 앞에서 받은 것 중 가장 나은 것을 저장한다
            attempts = attempt
            fails = len(validation.failures)
            run["attempts"].append({
                "body": text, "mood": data["mood"], "wish": data["wish"],
                "situation": data["situation"],
                "used_quote": data["used_quote"], "failures": validation.failure_lines(),
            })
            if best is None or fails < best[0]:
                best = (fails, attempt, text, data, validation)
            if validation.passed:
                first_passed = attempt == 1
                break
            failure_lines = validation.failure_lines()
            previous_body = data["body"]

        assert best is not None
        _, _, text, data, validation = best
        quote = data["used_quote"] or evidence.quote
        source = self._source_of(video_id, quote) or evidence.source
        extra = {"wish": data["wish"], "basis": evidence.to_dict(), "said": kit["said"],
                 "situation": data["situation"]}
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
                "created_at, updated_at, disclosed, review_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'draft',0,?,?,?,?)",
                (
                    video_id,
                    text,
                    quote,
                    source,
                    voice.label(data["mood"]),
                    str(getattr(llm, "model", "") or ""),
                    attempts,
                    int(first_passed),
                    _validation_to_json(validation),
                    int(validation.passed),
                    now,
                    now,
                    int(disclose),
                    json.dumps(extra, ensure_ascii=False),
                ),
            )
            draft_id = int(cur.lastrowid)
        return self.get(draft_id)

    def _kit(
        self, video_id: str, concern: str, evidence: Evidence, voice: Voice,
        disclose: bool, *, others: Sequence[Draft], said: str = "",
    ) -> dict[str, Any]:
        """쓰기에 필요한 것(처음 쓰기·규칙 다시 쓰기·검수 뒤 다시 쓰기가 함께 쓴다).

        `others`: 같은 영상의 다른 초안 — 이미 짚은 구절과 앞 댓글의 `wish`를 요청 글에 넣는다."""
        rules = self.rules
        title = description = transcript = ""
        try:
            current = self.context.current(video_id)
            title = current.video.video.title or ""
            description = current.video.video.description or ""
            transcript = current.transcript_text or ""
        except AppError:
            pass
        material = prompts.material_lines(
            quote=evidence.quote, source=evidence.source, transcript=transcript,
            title=title, description=description,
        )
        used_quotes_ = list(dict.fromkeys(d.evidence_quote for d in others if d.evidence_quote))
        used_wishes = list(dict.fromkeys(d.wish for d in others if d.wish))
        rows = self._recent_elsewhere(video_id)
        bodies = [toggle_disclosure(d["body"] or "", rules.disclosure, False) for d in rows]
        recent_bodies = list(dict.fromkeys(b for b in bodies if b))[:RECENT_BODIES]
        recent_situations = list(dict.fromkeys(
            s for d in rows if (s := situation_of(d["review_json"]))))[:RECENT_SITUATIONS]
        said = said or pick_saying(self.rng, rules.brand, recent_bodies)
        system = prompts.draft_system(
            brand=rules.brand, facts=self.brand_facts, voice=voice.voice, heard=voice.heard,
            from_comment=evidence.source == "comment", said=said,
        )
        return {
            "llm": self._llm(), "video_id": video_id, "system": system, "title": title,
            "concern": concern, "material": material, "used_quotes": used_quotes_,
            "used_wishes": used_wishes, "recent_bodies": recent_bodies, "said": said,
            "recent_situations": recent_situations,
            "evidence": evidence, "disclose": disclose,
            "mark": rules.disclosure if disclose else "",
            "previous": self.previous_texts(video_id),
        }

    def _write(
        self, kit: dict[str, Any], *, failure_lines: Sequence[str], previous_body: str
    ) -> tuple[str, dict[str, str], Validation]:
        """AI에게 한 번 쓰게 하고 규칙 검사까지. (표기 붙은 글, AI 답, 검사)."""
        rules = self.rules
        user = prompts.draft_user(
            title=kit["title"], concern=kit["concern"], material=kit["material"],
            used_quotes=kit["used_quotes"], used_wishes=kit["used_wishes"],
            recent_bodies=kit.get("recent_bodies", ()),
            recent_situations=kit.get("recent_situations", ()),
            previous_body=previous_body, failure_lines=failure_lines,
        )
        raw = kit["llm"].generate_json(
            system=kit["system"], user=user, schema=prompts.DRAFT_SCHEMA,
            temperature=prompts.DRAFT_TEMPERATURE, max_tokens=prompts.DRAFT_MAX_TOKENS,
        )
        raw = raw if isinstance(raw, dict) else {}
        body = clean_body(raw.get("body"), rules.disclosure)
        data = {
            "body": body,
            "mood": " ".join(str(raw.get("mood") or "").split())[:20],
            "wish": " ".join(str(raw.get("wish") or "").split())[:80],
            "situation": " ".join(str(raw.get("situation") or "").split())[:60],
            "used_quote": " ".join(str(raw.get("used_quote") or "").split()).strip(_QUOTES),
        }
        text = with_disclosure(body, kit["mark"])
        validation = self.checks.check(
            kit["video_id"], text, previous_texts=kit["previous"],
            evidence_quote=data["used_quote"] or kit["evidence"].quote,
            disclose=kit["disclose"],
        )
        return text, data, validation

    # ------------------------------------------------------------ AI 검수 한 번

    def review(self, draft_id: int) -> Draft:
        """규칙 검사를 통과한 모델 초안을 AI가 한 번 더 읽는다(`app/analysis/review.py`).

        검수할 것이 없으면(설정을 끔·이미 함·규칙 검사에 걸림·사람이 고침·승인됨) 그대로 돌려준다.
        거짓이면 같은 말 높임·들은 경로로 **한 번만** 다시 쓰고, 다시 쓴 글이 규칙 검사를 통과할
        때만 그 글로 바꿔 다시 검수한다. 어떤 경우에도 예외를 내지 않는다(검수 때문에 초안 만들기가
        실패하지 않게). 과정은 `last_run["review"]`에 남는다.
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
            result, new = self._review(draft, info)
        except Exception as exc:  # noqa: BLE001 — 검수는 초안 만들기를 절대 막지 않는다
            info["error"] = f"{type(exc).__name__}: {exc}"
            result, new = {"status": rv.ERROR, "problems": []}, None
        result["seconds"] = info["seconds"] = round(time.monotonic() - started, 1)
        info["status"] = result["status"]
        rewrite = info.get("rewrite") or {}
        if rewrite:
            result["kept"] = new is not None
        return self._save_review(
            draft, result, new=new,
            before=draft.body if rewrite else "", after=str(rewrite.get("body") or ""),
            review_ms=int(info["review_ms"]), rewrite_ms=int(info["rewrite_ms"]),
        )

    def _review(
        self, draft: Draft, info: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """(검수 결과, 바꿀 글의 내용 또는 None)."""
        rules = self.rules
        analysis = self.stored_analysis(draft.video_id)
        basis = (draft.review or {}).get("basis") or {}
        evidence = Evidence(
            quote=str(basis.get("quote") or draft.evidence_quote),
            source=str(basis.get("source") or draft.evidence_source),
        )
        voice = voice_of(draft.tone_label) or pick_voice(self.rng)
        others = [d for d in self.list(draft.video_id) if d.id != draft.id]
        concern = analysis.concern if analysis else ""
        kit = self._kit(draft.video_id, concern, evidence, voice, draft.disclosed, others=others,
                        said=str((draft.review or {}).get("said") or ""))  # 처음과 같은 들은 말
        system = rv.review_system(brand=rules.brand)

        def ask(text: str) -> rv.Verdict | None:
            body = toggle_disclosure(text, rules.disclosure, False)
            started = time.monotonic()
            try:
                return rv.ask(kit["llm"], system=system, user=rv.review_user(
                    body=body, title=kit["title"], concern=kit["concern"],
                    material=kit["material"]))
            except (AppError, ValueError) as exc:
                info.setdefault("errors", []).append(str(getattr(exc, "message", exc)))
                return None
            finally:
                info["review_ms"] += int((time.monotonic() - started) * 1000)

        first = ask(draft.body)
        if first is None:
            return {"status": rv.ERROR, "problems": []}, None
        info["first"] = {"ok": first.ok, "problems": first.problems, "wish_kind": first.wish_kind}
        if first.ok:
            return {"status": rv.PASSED, "problems": [], "wish_kind": first.wish_kind}, None
        flagged = {"status": rv.FLAGGED, "problems": first.problems, "first": first.problems,
                   "wish_kind": first.wish_kind}
        # 한 번만 다시 쓴다: 같은 말 높임·들은 경로·[짚을 내용]에 검수 문제를 「걸린 까닭」으로
        started = time.monotonic()
        try:
            text, data, validation = self._write(
                kit, failure_lines=rv.retry_lines(first.problems),
                previous_body=toggle_disclosure(draft.body, rules.disclosure, False),
            )
        except AppError as exc:
            info["rewrite_error"] = exc.message
            return flagged, None  # 다시 쓰기 실패·시간 초과: 앞 초안 그대로
        finally:
            info["rewrite_ms"] += int((time.monotonic() - started) * 1000)
        info["rewrite"] = {"body": text, "failures": validation.failure_lines()}
        if not data["body"] or text == draft.body or not validation.passed:
            return flagged, None  # 다시 쓴 글이 규칙 검사에 걸리면 앞 글을 둔다
        quote = data["used_quote"] or evidence.quote
        new = {
            "text": text, "validation": validation, "wish": data["wish"],
            "situation": data["situation"], "tone_label": voice.label(data["mood"]),
            "evidence_quote": quote,
            "evidence_source": self._source_of(draft.video_id, quote) or evidence.source,
        }
        second = ask(text)
        if second is None:
            # 두 번째 검수 실패: 검수를 통과했는지 모르는 글로 바꾸지 않는다 — 앞 초안
            return {"status": rv.ERROR, "problems": [], "first": first.problems}, None
        info["second"] = {"ok": second.ok, "problems": second.problems,
                          "wish_kind": second.wish_kind}
        if second.ok:
            return ({"status": rv.REWRITTEN, "problems": [], "first": first.problems,
                     "wish_kind": second.wish_kind}, new)
        return ({"status": rv.FLAGGED, "problems": second.problems, "first": first.problems,
                 "wish_kind": second.wish_kind}, new)

    def _save_review(
        self, draft: Draft, result: dict[str, Any], *, new: dict[str, Any] | None = None,
        before: str = "", after: str = "", review_ms: int = 0, rewrite_ms: int = 0,
    ) -> Draft:
        """검수 결과를 남긴다. `new`가 있으면 다시 쓴 글로 바꾼다(모델에게 쓰게 한 횟수 +1).

        `wish`·`basis`는 그대로 이어 둔다(다시 쓴 글이면 그 글의 `wish`). 규칙 검사를 통과한
        초안이 통과 못 한 글로 바뀌지 않게 여기서 한 번 더 막는다."""
        now = self._now()
        if new is not None and not new["validation"].passed:
            new = None
            if "kept" in result:
                result = {**result, "kept": False}
        old = draft.review or {}
        keep = {k: old[k] for k in ("wish", "basis", "said", "situation") if k in old}
        if new is not None:
            keep["wish"] = new["wish"]
            if new.get("situation"):
                keep["situation"] = new["situation"]
        raw = json.dumps({**result, **keep}, ensure_ascii=False)
        trace = (before, after, int(review_ms), int(rewrite_ms))
        with db.session(self.db_path) as conn:
            if new is not None:
                validation = new["validation"]
                conn.execute(
                    "UPDATE drafts SET body=?, validation_json=?, passed=?, attempts=attempts+1, "
                    "tone_label=?, evidence_quote=?, evidence_source=?, "
                    "review_json=?, review_before=?, review_after=?, review_ms=?, rewrite_ms=?, "
                    "updated_at=? WHERE id=?",
                    (new["text"], _validation_to_json(validation), int(validation.passed),
                     new["tone_label"], new["evidence_quote"], new["evidence_source"],
                     raw, *trace, now, draft.id),
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


    def check_basis(self, video_id: str) -> str | None:
        """사람이 쓴 글을 검사할 근거 구절(V6, 화면의 실시간 검사): 그 영상의 지금 초안(밀려나지
        않은 것 중 최신)이 짚은 구절. 없으면 None — 그러면 V6은 글에서 근거를 찾는다."""
        self._check_id(video_id)
        current = next((d for d in self.list(video_id) if d.status != "superseded"), None)
        return current.evidence_quote if current and current.evidence_quote else None

    def _recent_elsewhere(self, video_id: str, limit: int = 8) -> list[Any]:
        """다른 영상의 최근 초안(상태와 상관없이, 새것부터).
        운명원 말하기·들은 경로를 영상마다 겹치지 않게 하려고 쓴다(2026-11-18)."""
        with db.session(self.db_path) as conn:
            return conn.execute(
                "SELECT body, tone_label, review_json FROM drafts WHERE video_id IS NOT ? "
                "ORDER BY id DESC LIMIT ?",
                (video_id, limit),
            ).fetchall()

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
        return self.checks.check(
            video_id,
            text,
            previous_texts=self.previous_texts(video_id),
            evidence_quote=quote,
            disclose=disclose,
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

