"""Stage 1: FastAPI local dashboard shell.

No external API calls or social-media posting are implemented at this stage.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="JG Marketing AI Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Render the three-stage local dashboard."""
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/api/health")
def health():
    """Return a machine-readable startup check."""
    return {"status": "ok", "app": "JG Marketing AI Agent", "stage": 1}
