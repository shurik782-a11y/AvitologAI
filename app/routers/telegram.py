"""Telegram webhook endpoint."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.services.telegram import handle_update

router = APIRouter()
log = logging.getLogger("avitolog.telegram")


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Bot not configured")
    # Optional shared secret if user sets TELEGRAM_WEBHOOK_SECRET later
    secret = getattr(settings, "telegram_webhook_secret", "") or ""
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(403, "Bad secret")
    try:
        update: dict[str, Any] = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Invalid JSON") from exc
    try:
        await handle_update(update)
    except Exception:
        log.exception("Failed to handle Telegram update")
    return {"ok": True}


@router.get("/telegram/status")
async def telegram_status() -> dict[str, Any]:
    from app.services.telegram import webapp_url

    return {
        "token_set": bool(settings.telegram_bot_token),
        "public_base_url": settings.public_base_url,
        "webapp_url": webapp_url(),
        "webhook_path": "/api/telegram/webhook",
    }
