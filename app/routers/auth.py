"""Auth endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import settings
from app.services.auth import admin_ids, require_admin_user

router = APIRouter()


@router.get("/auth/me")
def auth_me(user: dict[str, Any] = Depends(require_admin_user)) -> dict[str, Any]:
    ids = sorted(admin_ids())
    return {
        "ok": True,
        "user_id": user.get("id"),
        "username": user.get("username") or "",
        "first_name": user.get("first_name") or "",
        "dev_open": bool(user.get("dev_open")),
        "admin_gate": bool(ids),
        "admins_configured": len(ids),
        "app": settings.app_name,
    }
