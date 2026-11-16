"""통제된 테스트 페이지(sandbox) — 8단계(DESIGN 6.1).

이 앱이 직접 주는 단순한 화면이다. 유튜브 화면을 베끼지 않는다.
자동 입력·게시·확인은 이 페이지에서만 한다(실제 유튜브에는 하지 않는다).
댓글은 이 앱의 `sandbox_comments` 표에만 저장된다.

- `GET /sandbox/watch?v=<영상ID>&profile=<이름>&fail=<스위치>` — 화면
- `GET /sandbox/api/comments?v=<영상ID>` — 그 영상의 테스트 댓글(오래된 것이 위)
- `POST /sandbox/api/comments` — 댓글 저장. 댓글 상자의 입력 이벤트 수를 함께 받는다

일부러 실패를 내는 스위치(`fail`): `hide_button`(「댓글」 단추가 없다) · `slow`(저장 응답이 늦다)
· `reject`(저장을 거절한다). 실패 처리와 화면 캡처를 시험하는 데 쓴다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import db
from app.api.deps import get_services
from app.youtube.quota import utc_now
from app.youtube.url_parser import is_video_id

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
FAIL_SWITCHES = ("hide_button", "slow", "reject")
SLOW_SECONDS = 2.5  # fail=slow일 때 저장 응답을 늦추는 시간
MAX_BODY = 1000

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
FailSwitch = Literal["", "hide_button", "slow", "reject"]


class SandboxCommentIn(BaseModel):
    video_id: str
    body: str = Field(min_length=1, max_length=MAX_BODY)
    profile: str = Field(default="", max_length=40)
    input_events: int = Field(default=0, ge=0, le=100_000)
    fail: FailSwitch = ""


class SandboxCommentOut(BaseModel):
    id: int
    video_id: str
    profile: str
    body: str
    input_events: int
    created_at: str


class SandboxCommentsOut(BaseModel):
    video_id: str
    items: list[SandboxCommentOut]


def add_comment(
    db_path: Path,
    video_id: str,
    body: str,
    *,
    profile: str = "",
    input_events: int = 0,
    now: datetime | None = None,
) -> int:
    stamp = (now or utc_now()).isoformat()
    with db.session(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO sandbox_comments(video_id, profile, body, input_events, created_at) "
            "VALUES (?,?,?,?,?)",
            (video_id, profile, body, int(input_events), stamp),
        )
        return int(cur.lastrowid)


def list_comments(db_path: Path, video_id: str) -> list[SandboxCommentOut]:
    with db.session(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sandbox_comments WHERE video_id = ? ORDER BY id", (video_id,)
        ).fetchall()
    return [
        SandboxCommentOut(
            id=int(r["id"]),
            video_id=r["video_id"],
            profile=r["profile"],
            body=r["body"],
            input_events=int(r["input_events"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


def _bad_video() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"kind": "invalid_url", "message": "영상 ID(11자)가 아닙니다."}},
    )


@router.get("/watch", response_class=HTMLResponse)
def watch(
    request: Request,
    v: Annotated[str, Query(max_length=20)] = "",
    profile: Annotated[str, Query(max_length=40)] = "",
    fail: Annotated[str, Query(max_length=20)] = "",
):
    if not is_video_id(v):
        return HTMLResponse("<!doctype html><meta charset=utf-8><p>영상 ID가 없습니다.</p>", 422)
    services = get_services(request)
    stored = services.videos.stored(v)  # YouTube를 부르지 않는다. 없어도 테스트 페이지는 뜬다
    title = stored.video.title if stored is not None else ""
    return TEMPLATES.TemplateResponse(
        request=request,
        name="sandbox.html",
        context={
            "video_id": v,
            "title": title or f"테스트 영상 {v}",
            "profile": profile,
            "fail": fail if fail in FAIL_SWITCHES else "",
        },
    )


@router.get("/api/comments", response_model=SandboxCommentsOut)
def get_comments(request: Request, v: Annotated[str, Query(max_length=20)] = ""):
    if not is_video_id(v):
        return _bad_video()
    settings = get_services(request).settings
    return SandboxCommentsOut(video_id=v, items=list_comments(settings.db_path, v))


@router.post("/api/comments", response_model=SandboxCommentOut)
async def post_comment(
    payload: SandboxCommentIn, services: Annotated[object, Depends(get_services)]
):
    if not is_video_id(payload.video_id):
        return _bad_video()
    if payload.fail == "slow":
        await asyncio.sleep(SLOW_SECONDS)
    if payload.fail == "reject":
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "kind": "sandbox_rejected",
                    "message": "테스트 페이지가 댓글 저장을 거절했습니다(실패 스위치 reject).",
                }
            },
        )
    db_path = services.settings.db_path  # type: ignore[attr-defined]
    new_id = await asyncio.to_thread(
        add_comment,
        db_path,
        payload.video_id,
        payload.body,
        profile=payload.profile,
        input_events=payload.input_events,
    )
    for item in list_comments(db_path, payload.video_id):
        if item.id == new_id:
            return item
    raise RuntimeError("저장한 테스트 댓글을 다시 읽지 못했습니다.")
