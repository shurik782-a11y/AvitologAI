"""Persist chat/settings image payloads under /uploads."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from app.config import settings

_DATA_URL_RE = re.compile(
    r"^data:(image/(?:png|jpeg|jpg|webp|gif));base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def save_bytes(data: bytes, suffix: str = ".png") -> str:
    folder = Path(settings.data_dir) / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{suffix}"
    (folder / name).write_bytes(data)
    return f"/uploads/{name}"


def persist_data_url(data_url: str) -> str:
    """Decode data:image/...;base64,... into /uploads/… path. Pass through paths/URLs."""
    raw = (data_url or "").strip()
    if not raw:
        return ""
    if raw.startswith("/uploads/") or raw.startswith("http://") or raw.startswith("https://"):
        return raw
    m = _DATA_URL_RE.match(raw)
    if not m:
        return ""
    mime = m.group(1).lower()
    try:
        blob = base64.b64decode(m.group(2), validate=False)
    except Exception:
        return ""
    if not blob or len(blob) > 6_000_000:
        return ""
    suffix = ".jpg" if "jpeg" in mime or mime.endswith("jpg") else f".{mime.split('/')[-1]}"
    return save_bytes(blob, suffix=suffix)


def persist_attachment_list(urls: list | None, *, max_n: int = 8) -> list[dict]:
    """Save chat photos to disk; return [{type,url}] with durable /uploads paths only."""
    out: list[dict] = []
    for u in urls or []:
        if not isinstance(u, str):
            continue
        path = persist_data_url(u)
        if path.startswith("/uploads/") or path.startswith("http://") or path.startswith("https://"):
            out.append({"type": "image", "url": path})
        if len(out) >= max_n:
            break
    return out


def persist_reference_list(urls: list | None, *, max_n: int = 5) -> list[str]:
    out: list[str] = []
    for u in urls or []:
        if not isinstance(u, str):
            continue
        path = persist_data_url(u)
        if path and path not in out:
            out.append(path)
        if len(out) >= max_n:
            break
    return out
