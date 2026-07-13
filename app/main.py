"""AvitologAI — FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import (
    auth,
    avito_metrics,
    billing,
    chat,
    feed,
    metrics,
    projects,
    publications,
    settings as settings_router,
    telegram,
)
from app.services.auth import require_admin_user
from app.services.telegram import setup_telegram

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("avitolog")

_admin = [Depends(require_admin_user)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
    except Exception:
        log.exception("init_db failed — check DATABASE_URL")
        raise
    try:
        await setup_telegram()
    except Exception:
        log.exception("Telegram setup failed — check TELEGRAM_BOT_TOKEN / PUBLIC_BASE_URL")
    if not settings.admin_ids.strip():
        log.warning("ADMIN_IDS пуст — API открыт (dev). Задайте ADMIN_IDS=telegram_user_id для продакшена.")
    yield


app = FastAPI(title="AvitologAI", version="0.2.1", lifespan=lifespan)

_origins = ["*"]
if settings.public_base_url:
    base = settings.public_base_url.rstrip("/")
    _origins = [base, "https://web.telegram.org", "https://telegram.org"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(feed.router, prefix="/api", tags=["feed"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"], dependencies=_admin)
app.include_router(publications.router, prefix="/api/projects", tags=["publications"], dependencies=_admin)
app.include_router(chat.router, prefix="/api", tags=["chat"], dependencies=_admin)
app.include_router(avito_metrics.router, prefix="/api", tags=["avito-metrics"], dependencies=_admin)
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"], dependencies=_admin)
app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"], dependencies=_admin)
app.include_router(billing.router, prefix="/api/billing", tags=["billing"], dependencies=_admin)
app.include_router(telegram.router, prefix="/api", tags=["telegram"])

static_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
uploads_dir = Path(settings.data_dir) / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": "AvitologAI",
        "public_base_url": settings.public_base_url or "",
        "telegram_configured": bool(settings.telegram_bot_token),
        "admin_gate": bool(settings.admin_ids.strip()),
    }


if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str = "") -> FileResponse:
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
