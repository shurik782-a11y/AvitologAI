"""OpenRouter billing summary for header."""
from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import AppSettings, get_db
from app.schemas import BillingSummary

router = APIRouter()

_cache: dict[str, Any] = {"ts": 0.0, "data": None}
_TTL = 90.0


@router.get("/summary", response_model=BillingSummary)
async def billing_summary(db: Session = Depends(get_db)) -> BillingSummary:
    now = time.time()
    if _cache["data"] and now - float(_cache["ts"]) < _TTL:
        return BillingSummary.model_validate(_cache["data"])

    row = db.get(AppSettings, 1)
    api_key = (row.openrouter_api_key if row else "") or settings.openrouter_api_key
    if not api_key:
        out = BillingSummary(available=False, label="баланс н/д", error="no_key")
        return out

    remaining: float | None = None
    usage_monthly: float | None = None
    err = ""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{settings.openrouter_base_url}/key",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code < 400:
                data = resp.json().get("data") or resp.json()
                usage_monthly = _f(data.get("usage_monthly"))
                remaining = _f(data.get("limit_remaining"))
                if remaining is None:
                    limit = _f(data.get("limit"))
                    usage = _f(data.get("usage"))
                    if limit is not None and usage is not None:
                        remaining = max(limit - usage, 0.0)
            else:
                err = f"key {resp.status_code}"

            # optional credits endpoint (management key)
            credits = await client.get(
                f"{settings.openrouter_base_url}/credits",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if credits.status_code < 400:
                cdata = credits.json().get("data") or credits.json()
                total = _f(cdata.get("total_credits"))
                used = _f(cdata.get("total_usage"))
                if total is not None and used is not None:
                    remaining = max(total - used, 0.0)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:200]

    if remaining is None and usage_monthly is None:
        out = BillingSummary(available=False, label="баланс н/д", error=err or "unavailable")
    else:
        out = BillingSummary(
            available=True,
            remaining=remaining,
            usage_monthly=usage_monthly,
            label=_label(remaining, usage_monthly),
            error=err,
        )
    _cache["ts"] = now
    _cache["data"] = out.model_dump()
    return out


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _label(remaining: float | None, monthly: float | None) -> str:
    parts = []
    if remaining is not None:
        parts.append(f"осталось ${remaining:.2f}")
    if monthly is not None:
        parts.append(f"мес. ${monthly:.2f}")
    return " · ".join(parts) if parts else "баланс н/д"
