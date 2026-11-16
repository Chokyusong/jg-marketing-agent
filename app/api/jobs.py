"""게시 작업 API(8단계). 얇게: 입력 검증 → 작업 서비스 → 응답.

- `POST /api/jobs` — 작업 시작(승인한 초안 + 그 대상에서 댓글 안 단 영상 + 오늘 남은 횟수).
  sandbox는 이 앱의 `/sandbox/watch` 주소를 연다. 주소는 요청 머리말(Host)이 아니라 서버가 실제로
  듣고 있는 주소·포트로 만든다.
- `GET /api/jobs/{id}` — 진행 상태(화면이 0.5초마다 물어 온다)
- `POST /api/jobs/{id}/approve` — sandbox 승인 대기에서 [게시 승인]
- `POST /api/jobs/{id}/confirm` — assist에서 [게시했어요] / [게시 안 함]
- `POST /api/jobs/{id}/cancel`
- `GET /api/jobs/{id}/screenshot` — 실패한 sandbox 작업의 화면 캡처(PNG)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app.api.deps import Services, get_services
from app.schemas import JobConfirmIn, JobIn, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
ServicesDep = Annotated[Services, Depends(get_services)]


def local_base_url(request: Request) -> str:
    """이 서버가 듣고 있는 주소(http://127.0.0.1:포트).

    이 앱은 127.0.0.1에서만 듣는다. 듣는 주소가 로컬이 아니면(테스트 클라이언트의 testserver 등)
    127.0.0.1로 바꾼다 — 테스트 페이지를 바깥 주소로 여는 일이 없게.
    """
    server = request.scope.get("server") or ("127.0.0.1", 80)
    host, port = str(server[0]), int(server[1] or 80)
    if host not in ("127.0.0.1", "localhost"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


@router.post("", response_model=JobOut)
def start_job(payload: JobIn, request: Request, services: ServicesDep) -> JobOut:
    job_id = services.jobs.start(
        payload.video_id,
        payload.draft_id,
        payload.profile or None,
        payload.target,
        base_url=local_base_url(request),
        daily_limit=payload.daily_limit,
        fail=payload.fail,
    )
    return JobOut.from_view(services.jobs.get(job_id))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, services: ServicesDep) -> JobOut:
    return JobOut.from_view(services.jobs.get(job_id))


@router.post("/{job_id}/approve", response_model=JobOut)
def approve_job(job_id: str, services: ServicesDep) -> JobOut:
    return JobOut.from_view(services.jobs.approve(job_id))


@router.post("/{job_id}/confirm", response_model=JobOut)
def confirm_job(job_id: str, payload: JobConfirmIn, services: ServicesDep) -> JobOut:
    return JobOut.from_view(services.jobs.confirm(job_id, payload.posted))


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, services: ServicesDep) -> JobOut:
    return JobOut.from_view(services.jobs.cancel(job_id))


@router.get("/{job_id}/screenshot", response_class=FileResponse)
def job_screenshot(job_id: str, services: ServicesDep) -> FileResponse:
    path = services.jobs.screenshot_path(job_id)
    return FileResponse(path, media_type="image/png", filename=f"{job_id}.png")
