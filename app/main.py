"""FastAPI 앱 생성과 라우터 연결.

1단계의 `/`(대시보드)와 `/api/health`는 그대로 둔다.
2단계: YouTube 영상 불러오기(①칸)와 시스템 상태 API를 붙였다.
3단계: 영상 맥락(자막 붙여넣기·인기 댓글) API를 붙였다(②칸 자막 출처).
실제 유튜브 화면을 자동으로 조작하는 코드는 없다(DESIGN 6.1).
"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import status as status_api
from app.api import videos as videos_api
from app.api.deps import ServiceHolder
from app.config import Settings
from app.errors import AppError
from app.transcript.manual import MAX_TRANSCRIPT_CHARS
from app.youtube.quota import Clock, utc_now

BASE_DIR = Path(__file__).resolve().parent
mimetypes.add_type("font/woff2", ".woff2")  # 글꼴 파일을 올바른 형식으로 내려보낸다
APP_VERSION = "0.3.0"
STAGE = 3
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def create_app(
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    """앱을 만든다. 테스트는 임시 설정과 가짜 전송(httpx.MockTransport)을 넣는다."""
    holder = ServiceHolder(settings, transport=transport, clock=clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        holder.close()

    app = FastAPI(title="JG Marketing AI Agent", version=APP_VERSION, lifespan=lifespan)
    app.state.services = holder
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        """대시보드 한 화면(UI_SPEC). 키 값은 화면에 넣지 않는다."""
        current = holder.settings
        options = sorted({10, 20, current.discover.max_results})
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "version": APP_VERSION,
                "stage": STAGE,
                "default_query": current.discover.query,
                "default_max_results": current.discover.max_results,
                "max_results_options": options,
                "daily_max_comments": current.daily_max_comments,
                "profiles": list(current.rules.get("profiles") or []),
                "disclosure": (current.rules.get("comment") or {}).get("disclosure", "[광고]"),
                "max_transcript_chars": MAX_TRANSCRIPT_CHARS,
            },
        )

    @app.get("/api/health")
    def health():
        """Return a machine-readable startup check."""
        return {"status": "ok", "app": "JG Marketing AI Agent", "stage": 1}

    app.include_router(status_api.router)
    app.include_router(videos_api.router)
    return app


app = create_app()
