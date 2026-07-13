"""Telegram Bot API helpers (webhook + /start WebApp button)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("avitolog.telegram")


def bot_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def webapp_url() -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        return ""
    return base


async def tg_call(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(bot_api_url(method), json=payload or {})
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data


async def setup_telegram() -> None:
    """Register webhook + default menu button when token and public URL exist."""
    if not settings.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return
    base = webapp_url()
    if not base:
        log.warning("PUBLIC_BASE_URL not set — skip webhook/menu setup")
        return

    webhook = f"{base}/api/telegram/webhook"
    await tg_call(
        "setWebhook",
        {
            "url": webhook,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        },
    )
    await tg_call(
        "setChatMenuButton",
        {
            "menu_button": {
                "type": "web_app",
                "text": "AvitologAI",
                "web_app": {"url": base},
            }
        },
    )
    log.info("Telegram webhook=%s menu=%s", webhook, base)


async def send_start(chat_id: int) -> None:
    base = webapp_url()
    if not base:
        await tg_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "AvitologAI почти готов, но на сервере не задан PUBLIC_BASE_URL.\n"
                    "Добавьте в Railway: PUBLIC_BASE_URL=https://avitologai-production.up.railway.app"
                ),
            },
        )
        return

    text = (
        "Привет! Я AvitologAI — ассистент по креативам для Авито.\n\n"
        "Нажмите кнопку ниже, чтобы открыть приложение."
    )
    keyboard = {
        "keyboard": [
            [{"text": "Открыть AvitologAI", "web_app": {"url": base}}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }
    await tg_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": keyboard,
        },
    )


async def handle_update(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    text = (message.get("text") or "").strip()
    if text.startswith("/start") or text in {"/app", "app", "меню", "Меню"}:
        await send_start(int(chat_id))
        return
    if text.startswith("/help"):
        await tg_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Команды:\n/start — открыть приложение\n/help — справка",
            },
        )
