"""Avito Autoload + Item stats API client."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.db import Project

log = logging.getLogger("avitolog.avito")
BASE = "https://api.avito.ru"


class AvitoError(RuntimeError):
    pass


async def get_token(client_id: str, client_secret: str) -> str:
    if not client_id or not client_secret:
        raise AvitoError("Avito client_id/secret не заданы в настройках проекта")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or not data.get("access_token"):
            raise AvitoError(f"Avito token error: {resp.status_code} {resp.text[:400]}")
        return str(data["access_token"])


async def ensure_autoload_profile(project: Project, feed_url: str, token: str) -> dict[str, Any]:
    payload = {
        "autoload_enabled": True,
        "report_email": "noreply@avitolog.local",
        "feeds_data": [{"feed_name": f"project-{project.id}", "feed_url": feed_url}],
        "schedule": [{"rate": 50, "weekdays": [0, 1, 2, 3, 4, 5, 6], "time_slots": [10]}],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BASE}/autoload/v2/profile",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        # Some accounts use PUT-like upsert; accept 2xx
        if resp.status_code >= 400:
            log.warning("autoload profile upsert failed: %s %s", resp.status_code, resp.text[:300])
            return {"ok": False, "body": resp.text[:500]}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"ok": True}


async def trigger_upload(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BASE}/autoload/v2/upload",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            # try alternate path used in newer APIs
            resp2 = await client.post(
                f"{BASE}/autoload/v1/upload",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp2.status_code >= 400:
                raise AvitoError(f"upload failed: {resp.status_code}/{resp2.status_code} {resp.text[:300]}")
            return _safe_json(resp2)
        return _safe_json(resp)


async def get_item_info(token: str, user_id: str, item_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{BASE}/core/v1/accounts/{user_id}/items/{item_id}/",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            raise AvitoError(f"getItemInfo {resp.status_code}: {resp.text[:400]}")
        return _safe_json(resp)


async def get_item_stats(token: str, user_id: str, item_ids: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BASE}/stats/v1/accounts/{user_id}/items",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"itemIds": [int(i) for i in item_ids if str(i).isdigit()], "periodGrouping": "day"},
        )
        if resp.status_code >= 400:
            # fallback shape
            resp = await client.post(
                f"{BASE}/stats/v1/accounts/{user_id}/items",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"itemIds": item_ids},
            )
        if resp.status_code >= 400:
            raise AvitoError(f"itemStats {resp.status_code}: {resp.text[:400]}")
        return _safe_json(resp)


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:  # noqa: BLE001
        return {"raw": resp.text[:1000]}
