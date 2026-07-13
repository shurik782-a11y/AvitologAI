"""AvitologAI — FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import chat, metrics, projects, settings as settings_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AvitologAI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])

static_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
uploads_dir = Path(settings.data_dir) / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "AvitologAI"}


if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str = "") -> FileResponse:
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
