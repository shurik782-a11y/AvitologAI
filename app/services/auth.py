"""Telegram WebApp initData verification + ADMIN_IDS gate."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Request

from app.config import settings

log = logging.getLogger("avitolog.auth")


def parse_admin_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            log.warning("skip invalid ADMIN_IDS entry: %s", part)
    return out


def admin_ids() -> set[int]:
    return parse_admin_ids(settings.admin_ids)


def validate_webapp_init_data(init_data: str, bot_token: str, *, max_age_sec: int = 86400) -> dict[str, Any]:
    """Validate Telegram Mini App initData; return parsed user dict."""
    if not init_data or not bot_token:
        raise HTTPException(401, "Требуется Telegram WebApp авторизация")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Некорректный initData (нет hash)")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Подпись initData неверна")

    auth_date = parsed.get("auth_date")
    if auth_date:
        try:
            age = int(time.time()) - int(auth_date)
            if age > max_age_sec or age < -60:
                raise HTTPException(401, "Сессия Telegram устарела — переоткройте приложение")
        except ValueError as exc:
            raise HTTPException(401, "Некорректный auth_date") from exc

    user_raw = parsed.get("user") or "{}"
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(401, "Некорректный user в initData") from exc
    if not isinstance(user, dict) or user.get("id") is None:
        raise HTTPException(401, "В initData нет user.id")
    return user


def require_admin_user(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    """FastAPI dependency: allow only ADMIN_IDS when configured."""
    ids = admin_ids()
    # Dev/smoke: open API only when ADMIN_IDS пуст
    if not ids:
        return {"id": 0, "dev_open": True}

    if not settings.telegram_bot_token:
        raise HTTPException(503, "TELEGRAM_BOT_TOKEN не задан — нельзя проверить ADMIN_IDS")

    init_data = x_telegram_init_data or ""
    if not init_data:
        # Also accept Authorization: tma <initData>
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("tma "):
            init_data = auth[4:].strip()

    user = validate_webapp_init_data(init_data, settings.telegram_bot_token)
    uid = int(user["id"])
    if uid not in ids:
        raise HTTPException(403, "Нет доступа: ваш Telegram ID не в ADMIN_IDS")
    return user


def is_public_api_path(path: str) -> bool:
    if path in {"/api/health", "/api/telegram/webhook", "/api/telegram/status"}:
        return True
    if path.endswith("/avito-feed.xml"):
        return True
    return False
