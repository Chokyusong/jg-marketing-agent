"""영상 맥락 묶음: AI가 읽을 영상 자료를 모은다(DESIGN 5.1, PLAYBOOK 3단계).

순서
1. 자막(R4): **사람이 붙여 넣은 자막 > 자동으로 읽은 자막 > 없음.** 붙여 넣은 자막이 없고 설정의
   자막 출처가 `auto`(기본, 「자막 자동으로 읽기」 켬)면 `AutoTranscriptProvider`로 읽는다.
   읽은 자막과 못 읽은 이유는 `video_context`에 저장해 같은 영상에서 다시 부르지 않는다
   (못 읽은 이유가 잠깐의 문제 — 막힘·시간 초과 등 — 면 30분 뒤에 한 번 더 읽어 본다).
   못 읽어도 오류가 아니다.
   `manual`이면 자동으로 읽지 않는다. 옛 값 `unofficial`이면 `transcript_provider_off` 오류.
2. 자막이 없으면 제목과 설명을 본문으로 쓴다(과제 원문이 허용한 대체). 이때 AI에 넘기는 글 머리에
   「설명란에는 광고·협찬 글이 섞여 있을 수 있다」는 안내(`NO_TRANSCRIPT_NOTE`)를 붙인다.
3. 인기 댓글: commentThreads.list(order=relevance) 상위 20개(1단위). 댓글이 막힌 영상이면
   오류가 아니라 빈 목록으로 진행한다.

같은 영상의 맥락은 `video_context`에 저장해 두고, 다시 만들 때(`refresh=True`)만 댓글을 새로
부른다(할당량 절약). 자막을 붙여 넣거나 지우면 저장된 댓글로 다시 묶는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from app import db
from app.errors import AppError, ErrorKind
from app.transcript.auto import (
    REASON_NOTES,
    TRANSIENT_REASONS,
    AutoResult,
    AutoTranscriptProvider,
    source_label,
)
from app.transcript.base import Transcript, check_provider_setting
from app.transcript.manual import ManualTranscriptProvider, prepare_transcript
from app.youtube.client import Comment
from app.youtube.quota import Clock
from app.youtube.service import StoredVideo, VideoService
from app.youtube.url_parser import is_video_id

log = logging.getLogger("app.analysis.context")

BodySource = Literal["transcript", "title_description"]
TranscriptSourceName = Literal["manual", "auto", "unofficial", "none"]

MAX_COMMENTS = 20
# 길이 맞추기 규칙(PLAYBOOK 3단계)
DESCRIPTION_LIMIT = 1500
COMMENT_LIMIT = 200
MIDDLE_CUT = "\n…(중략)…\n"
# 자막이 없을 때(본문 출처가 제목·설명) 분석에 넘기는 글 머리에 붙이는 안내(실제 데이터 보정).
# 실제 영상의 설명란이 협찬 상품 소개로 채워져 분석이 상품을 영상의 주제로 읽었다.
NO_TRANSCRIPT_NOTE = (
    "[안내] 자막이 없어 제목·설명·인기 댓글로 분석한다. 설명란과 댓글에는 광고·협찬·상품 소개·"
    "이벤트 응모 글이 섞여 있을 수 있다. 그런 글은 영상의 연애 고민이 아니다. "
    "근거는 연애 고민을 말하는 댓글 > 제목 > 설명 순으로 고른다(제목 낱말을 되풀이하지 않게 "
    "인기 댓글에 나온 사연·말을 먼저). 해시태그(#…) 낱말은 근거·핵심 말로 쓰지 않는다."
)
TRANSCRIPT_LABELS = {
    "manual": "붙여 넣은 자막",
    "auto": "자동으로 읽은 자막",
    "unofficial": "비공식 조회 자막",
}
# 자동 생성 자막은 받아쓰기라 틀린 말이 섞인다. AI에 넘기는 자막 머리에 알려 둔다
GENERATED_NOTE = "유튜브 자동 생성 자막이라 받아쓰기 틀림이 있을 수 있다"
AUTO_RETRY = timedelta(minutes=30)  # 잠깐의 문제로 못 읽었을 때 다시 읽어 보는 간격


@dataclass(frozen=True)
class VideoContext:
    video: StoredVideo
    body: str  # AI가 읽을 본문(자막, 없으면 제목+설명)
    body_source: BodySource
    transcript_source: TranscriptSourceName
    transcript_text: str
    comments: tuple[Comment, ...]  # 인기 댓글(최대 20)
    comments_disabled: bool
    built_at: str
    truncated: bool = False  # 기본 한도(llm.context_chars)의 prompt_text에서 줄였는지
    transcript_truncated: bool = False  # 그중 자막 가운데를 줄였는지
    # R4: 자동으로 읽은 자막의 언어(ko 등)와 자동 생성 여부, 자동으로 못 읽은 이유(코드와 한 줄)
    transcript_language: str = ""
    transcript_generated: bool | None = None
    transcript_reason: str = ""
    transcript_note: str = ""

    @property
    def video_id(self) -> str:
        return self.video.video.video_id

    @property
    def transcript_chars(self) -> int:
        return len(self.transcript_text)


@dataclass(frozen=True)
class FittedText:
    text: str
    truncated: bool
    transcript_truncated: bool


# ---------------------------------------------------------------- 글 만들기(순수 함수)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _cut(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", True
    return text[: limit - 1] + "…", True


def _keep_ends(text: str, limit: int) -> tuple[str, bool]:
    """한도를 넘으면 앞 절반 + 뒤 절반을 남기고 가운데를 `…(중략)…`으로 바꾼다."""
    if len(text) <= limit:
        return text, False
    keep = limit - len(MIDDLE_CUT)
    if keep <= 0:
        return (MIDDLE_CUT.strip() if limit >= len(MIDDLE_CUT.strip()) else ""), True
    head = (keep + 1) // 2
    tail = keep - head
    return text[:head] + MIDDLE_CUT + (text[len(text) - tail :] if tail else ""), True


def fit_prompt(context: VideoContext, max_chars: int) -> FittedText:
    """모델에 넣을 글을 한도 안으로 맞춘다.

    설명은 1,500자, 댓글은 한 개 200자까지 20개. 자막은 남은 한도를 넘으면 앞 절반 + 뒤 절반.
    한도가 아주 작으면 댓글을 뒤에서부터 빼고, 그래도 넘치면 설명을 더 줄인다. 결과는 항상
    `max_chars` 이하다.
    """
    video = context.video.video
    truncated = False

    head = f"[제목] {_one_line(video.title)}\n[채널] {_one_line(video.channel_title)}"
    if not context.transcript_text:
        head = f"{NO_TRANSCRIPT_NOTE}\n{head}"
    description, cut = _cut(video.description.strip(), DESCRIPTION_LIMIT)
    truncated |= cut

    comment_lines: list[str] = []
    for comment in context.comments[:MAX_COMMENTS]:
        line, cut = _cut(_one_line(comment.text), COMMENT_LIMIT)
        truncated |= cut
        if line:
            comment_lines.append(f"- {line}")
    truncated |= len(context.comments) > MAX_COMMENTS

    if context.transcript_text:
        label = TRANSCRIPT_LABELS.get(context.transcript_source, "자막")
        if context.transcript_source == "auto":
            kind = source_label(context.transcript_language, context.transcript_generated)
            label = f"{label}({kind})"
            if context.transcript_generated:
                label = f"{label} · {GENERATED_NOTE}"
        transcript_head = f"[자막 · {label}]"
    else:
        transcript_head = "[자막] 없음 · 제목과 설명으로 대신"

    def comments_block() -> str:
        if context.comments_disabled:
            return "[인기 댓글] 댓글이 막힌 영상"
        if not comment_lines:
            return "[인기 댓글] 없음"
        return f"[인기 댓글 {len(comment_lines)}개]\n" + "\n".join(comment_lines)

    def fixed_len() -> int:
        parts = [head, f"[설명]\n{description or '(설명 없음)'}", transcript_head, comments_block()]
        return sum(len(p) for p in parts) + len(parts)  # 구역 사이 줄바꿈 + 자막 머리 다음 줄바꿈

    while fixed_len() > max_chars and comment_lines:
        comment_lines.pop()
        truncated = True
    over = fixed_len() - max_chars
    if over > 0 and description:
        description, _ = _cut(description, max(0, len(description) - over))
        truncated = True

    transcript, transcript_cut = "", False
    if context.transcript_text:
        transcript, transcript_cut = _keep_ends(
            context.transcript_text, max(0, max_chars - fixed_len())
        )
        truncated |= transcript_cut

    transcript_part = transcript_head
    if context.transcript_text:
        transcript_part = f"{transcript_head}\n{transcript}"
    text = "\n".join(
        [head, f"[설명]\n{description or '(설명 없음)'}", transcript_part, comments_block()]
    )
    if len(text) > max_chars:  # 한도가 머리말보다 작은 극단적인 경우
        text, truncated = text[:max_chars], True
    return FittedText(text=text, truncated=truncated, transcript_truncated=transcript_cut)


def search_text(context: VideoContext) -> str:
    """근거 대조용 전체 글(자르지 않음): 제목 + 설명 + 자막 + 댓글."""
    video = context.video.video
    parts = [video.title, video.description, context.transcript_text]
    parts += [c.text for c in context.comments]
    return "\n".join(p.strip() for p in parts if p and p.strip())


# ---------------------------------------------------------------- 서비스


def _comments_to_json(comments: list[Comment]) -> str:
    data = [
        {"text": c.text, "like_count": c.like_count, "published_at": c.published_at}
        for c in comments
    ]
    return json.dumps(data, ensure_ascii=False)


def _comments_from_json(raw: str) -> list[Comment]:
    return [Comment(**item) for item in json.loads(raw or "[]")]


class ContextService:
    def __init__(
        self,
        videos: VideoService,
        *,
        db_path: Path,
        clock: Clock,
        transcript_provider: str = "manual",
        context_chars: int = 6000,
        auto: AutoTranscriptProvider | None = None,
    ) -> None:
        self.videos = videos
        self.db_path = db_path
        self.clock = clock
        self.transcript_provider = transcript_provider
        self.context_chars = context_chars
        self.manual = ManualTranscriptProvider(db_path)
        # R4: 자동 공급자. 자막 출처가 auto일 때만 쓴다(만들지 않았으면 처음 쓸 때 만든다)
        self._auto = auto

    @property
    def auto_enabled(self) -> bool:
        return self.transcript_provider == "auto"

    @property
    def auto(self) -> AutoTranscriptProvider:
        if self._auto is None:
            self._auto = AutoTranscriptProvider()
        return self._auto

    # -- 기능

    def build(self, video_id: str, *, refresh: bool = False) -> VideoContext:
        """맥락을 만든다. 저장된 댓글이 있으면 그대로 쓰고, `refresh`면 댓글을 새로 부른다."""
        stored = self.videos.get(video_id)  # 영상 ID 확인 + videos 표에 저장
        transcript, reason, note = self._transcript(video_id, fetch=True, refresh=refresh)

        row = self._load_row(video_id)
        if row is not None and row["built_at"] and not refresh:
            comments = _comments_from_json(row["comments_json"])
            disabled = bool(row["comments_disabled"])
        else:
            comments, disabled = self._fetch_comments(video_id)

        body_source: BodySource = "transcript" if transcript else "title_description"
        built_at = self.clock().isoformat()
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO video_context(video_id, comments_json, comments_disabled, "
                "body_source, built_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(video_id) DO UPDATE "
                "SET comments_json = excluded.comments_json, "
                "comments_disabled = excluded.comments_disabled, "
                "body_source = excluded.body_source, built_at = excluded.built_at",
                (video_id, _comments_to_json(comments), int(disabled), body_source, built_at),
            )

        context = self._assemble(stored, transcript, comments, disabled, built_at, reason, note)
        fitted = fit_prompt(context, self.context_chars)
        return replace(
            context, truncated=fitted.truncated, transcript_truncated=fitted.transcript_truncated
        )

    def current(self, video_id: str) -> VideoContext:
        """저장된 맥락을 그대로 묶어 돌려준다(DB에 다시 쓰지 않고 YouTube도 부르지 않는다).

        아직 만든 적이 없으면 `build()`로 만든다. 규칙 검사(6단계)가 입력마다 부른다.
        """
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        row = self._load_row(video_id)
        stored = self.videos.stored(video_id)
        if row is None or not row["built_at"] or stored is None:
            return self.build(video_id)
        transcript, reason, note = self._transcript(video_id, fetch=False)
        return self._assemble(
            stored,
            transcript,
            _comments_from_json(row["comments_json"]),
            bool(row["comments_disabled"]),
            row["built_at"],
            reason,
            note,
        )

    def set_manual_transcript(self, video_id: str, text: str) -> VideoContext:
        """붙여 넣은 자막을 저장하고 맥락을 다시 묶는다(댓글은 저장된 것을 쓴다)."""
        prepare_transcript(text)  # 영상을 부르기 전에 빈 글·너무 긴 글을 먼저 거른다
        self.videos.get(video_id)
        self.manual.save(video_id, text)
        return self.build(video_id)

    def clear_manual_transcript(self, video_id: str) -> VideoContext:
        if not is_video_id(video_id):
            raise AppError(ErrorKind.INVALID_URL, detail="영상 ID 형식이 아님")
        self.manual.clear(video_id)
        return self.build(video_id)

    def transcript_map(self, video_ids: list[str]) -> dict[str, bool]:
        """이미 읽은(맥락을 만든) 영상 → 자막이 있는지(2026-11-18, ① 목록의 「자막 있음/없음」).

        저장된 것만 본다 — YouTube도 자막 공급처도 부르지 않는다. 안 읽은 영상은 넣지 않는다."""
        ids = [v for v in dict.fromkeys(video_ids) if v]
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with db.session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT video_id, transcript_source, transcript_text <> '' AS has_text "
                f"FROM video_context WHERE built_at IS NOT NULL AND video_id IN ({marks})",
                ids,
            ).fetchall()
        return {
            r["video_id"]: bool(r["has_text"]) and r["transcript_source"] != "none" for r in rows
        }

    def prompt_text(self, context: VideoContext, max_chars: int | None = None) -> str:
        return fit_prompt(context, max_chars or self.context_chars).text

    def search_text(self, context: VideoContext) -> str:
        return search_text(context)

    # -- 내부

    def _transcript(
        self, video_id: str, *, fetch: bool, refresh: bool = False
    ) -> tuple[Transcript | None, str, str]:
        """(자막, 못 읽은 이유 코드, 한 줄). 붙여 넣은 자막 > 자동으로 읽은 자막 > 없음.

        `fetch`가 거짓이면 저장된 것만 본다(규칙 검사가 입력마다 부른다 — 바깥에 접속하지 않는다).
        """
        manual = self.manual.fetch(video_id)
        if manual is not None:
            return manual, "", ""
        check_provider_setting(self.transcript_provider)  # unofficial이면 여기서 오류
        if not self.auto_enabled:
            return None, "off", REASON_NOTES["off"]
        row = self._auto_row(video_id)
        if row is not None and row["transcript_source"] == "auto" and row["transcript_text"]:
            return _stored_auto(row), "", row["transcript_note"] or ""
        checked = row is not None and row["auto_checked_at"]
        if checked and (not fetch or not self._should_retry(row, refresh)):
            return None, row["auto_reason"] or "error", row["transcript_note"] or ""
        if not fetch:
            return None, "", ""  # 아직 읽어 보지 않았다(맥락을 만들 때 읽는다)
        result = self.auto.read(video_id)
        self._save_auto(video_id, result)
        return result.transcript, result.reason, result.note

    def _should_retry(self, row, refresh: bool) -> bool:
        """저장된 「못 읽음」을 다시 읽어 볼지. 잠깐의 문제만 30분 뒤에(또는 다시 만들 때)."""
        if (row["auto_reason"] or "") not in TRANSIENT_REASONS:
            return False
        if refresh:
            return True
        try:
            checked = datetime.fromisoformat(row["auto_checked_at"])
        except (TypeError, ValueError):
            return True
        return self.clock() - checked >= AUTO_RETRY

    def _auto_row(self, video_id: str):
        with db.session(self.db_path) as conn:
            return conn.execute(
                "SELECT transcript_source, transcript_text, transcript_language, "
                "transcript_generated, auto_reason, transcript_note, auto_checked_at "
                "FROM video_context WHERE video_id = ?",
                (video_id,),
            ).fetchone()

    def _save_auto(self, video_id: str, result: AutoResult) -> None:
        now = self.clock().isoformat()
        t = result.transcript
        with db.session(self.db_path) as conn:
            if t is not None:
                conn.execute(
                    "INSERT INTO video_context(video_id, transcript_source, transcript_text, "
                    "transcript_language, transcript_generated, auto_reason, transcript_note, "
                    "auto_checked_at) VALUES (?, 'auto', ?, ?, ?, '', ?, ?) "
                    "ON CONFLICT(video_id) DO UPDATE SET transcript_source = 'auto', "
                    "transcript_text = excluded.transcript_text, "
                    "transcript_language = excluded.transcript_language, "
                    "transcript_generated = excluded.transcript_generated, auto_reason = '', "
                    "transcript_note = excluded.transcript_note, "
                    "auto_checked_at = excluded.auto_checked_at "
                    "WHERE video_context.transcript_source <> 'manual'",
                    (video_id, t.text, t.language or "", int(bool(t.generated)), result.note, now),
                )
            else:
                conn.execute(
                    "INSERT INTO video_context(video_id, auto_reason, transcript_note, "
                    "auto_checked_at) VALUES (?, ?, ?, ?) ON CONFLICT(video_id) DO UPDATE SET "
                    "auto_reason = excluded.auto_reason, "
                    "transcript_note = excluded.transcript_note, "
                    "auto_checked_at = excluded.auto_checked_at",
                    (video_id, result.reason, result.note, now),
                )

    def _fetch_comments(self, video_id: str) -> tuple[list[Comment], bool]:
        try:
            comments = self.videos.client.get_top_comments(video_id, max_results=MAX_COMMENTS)
        except AppError as exc:
            if exc.kind is ErrorKind.COMMENTS_DISABLED:
                log.info("댓글이 막힌 영상 %s: 빈 목록으로 진행", video_id)
                return [], True
            raise
        return [c for c in comments if c.text.strip()][:MAX_COMMENTS], False

    def _load_row(self, video_id: str):
        with db.session(self.db_path) as conn:
            return conn.execute(
                "SELECT comments_json, comments_disabled, built_at FROM video_context "
                "WHERE video_id = ?",
                (video_id,),
            ).fetchone()

    @staticmethod
    def _assemble(
        stored: StoredVideo,
        transcript: Transcript | None,
        comments: list[Comment],
        disabled: bool,
        built_at: str,
        reason: str = "",
        note: str = "",
    ) -> VideoContext:
        video = stored.video
        if transcript is not None:
            body, body_source, source = transcript.text, "transcript", transcript.source
        else:
            body = "\n".join(p for p in (video.title.strip(), video.description.strip()) if p)
            body_source, source = "title_description", "none"
        return VideoContext(
            video=stored,
            body=body,
            body_source=body_source,
            transcript_source=source,
            transcript_text=transcript.text if transcript else "",
            comments=tuple(comments),
            comments_disabled=disabled,
            built_at=built_at,
            transcript_language=(transcript.language or "") if transcript else "",
            transcript_generated=transcript.generated if transcript else None,
            transcript_reason="" if transcript else reason,
            transcript_note=note,
        )


def _stored_auto(row) -> Transcript:
    generated = row["transcript_generated"]
    return Transcript(
        text=row["transcript_text"],
        source="auto",
        language=row["transcript_language"] or None,
        generated=None if generated is None else bool(generated),
    )
