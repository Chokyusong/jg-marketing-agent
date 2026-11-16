"""사용자가 붙여 넣은 자막: 정리, 저장, 읽기, 지우기.

- 저장 위치는 `video_context` 표의 자막 칸이다(영상당 1행). 이 모듈은 자막 칸만 다룬다.
- 정리: NFC로 맞추기, 줄바꿈 통일, 줄마다 연속 공백을 한 칸으로, 빈 줄은 최대 한 줄, 앞뒤 공백 제거.
- 시간 표시(`1:23`)는 지우지 않는다. 장면을 언급할 때 근거가 된다.
- 정리한 뒤 비었으면 `transcript_empty`, 20,000자를 넘으면 `transcript_too_long`.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app import db
from app.errors import AppError, ErrorKind
from app.transcript.base import Transcript

MAX_TRANSCRIPT_CHARS = 20_000

_SPACES = re.compile(r"[^\S\n]+")  # 줄바꿈을 뺀 공백(탭·전각 공백·nbsp 포함)
_INVISIBLE = re.compile(r"[​‌‍⁠﻿]")  # 폭 없는 글자
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_transcript(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


def prepare_transcript(text: str) -> str:
    """정리하고 길이를 확인한다. 저장할 글을 돌려준다."""
    cleaned = clean_transcript(text)
    if not cleaned:
        raise AppError(ErrorKind.TRANSCRIPT_EMPTY)
    if len(cleaned) > MAX_TRANSCRIPT_CHARS:
        raise AppError(
            ErrorKind.TRANSCRIPT_TOO_LONG,
            detail=f"정리한 뒤 {len(cleaned):,}자 / 최대 {MAX_TRANSCRIPT_CHARS:,}자",
        )
    return cleaned


class ManualTranscriptProvider:
    name = "manual"

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def fetch(self, video_id: str) -> Transcript | None:
        with db.session(self.db_path) as conn:
            row = conn.execute(
                "SELECT transcript_text FROM video_context "
                "WHERE video_id = ? AND transcript_source = 'manual'",
                (video_id,),
            ).fetchone()
        if row is None or not row["transcript_text"]:
            return None
        return Transcript(text=row["transcript_text"], source="manual")

    def save(self, video_id: str, text: str) -> Transcript:
        """붙여 넣은 자막을 정리해 저장한다. 영상은 `videos` 표에 먼저 있어야 한다."""
        cleaned = prepare_transcript(text)
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO video_context(video_id, transcript_source, transcript_text) "
                "VALUES (?, 'manual', ?) ON CONFLICT(video_id) DO UPDATE SET "
                "transcript_source = 'manual', transcript_text = excluded.transcript_text",
                (video_id, cleaned),
            )
        return Transcript(text=cleaned, source="manual")

    def clear(self, video_id: str) -> bool:
        """붙여 넣은 자막을 지운다. 지운 것이 있었으면 True."""
        with db.session(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE video_context SET transcript_source = 'none', transcript_text = '' "
                "WHERE video_id = ? AND transcript_source = 'manual'",
                (video_id,),
            )
        return cur.rowcount > 0
