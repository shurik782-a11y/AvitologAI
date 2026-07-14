"""Persist chat/generated images: Postgres (durable) + disk cache under /uploads."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from app.config import settings
from app.db import SessionLocal, StoredMedia

_DATA_URL_RE = re.compile(
    r"^data:(image/(?:png|jpeg|jpg|webp|gif));base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)

_SAFE_NAME_RE = re.compile(r"^[a-f0-9]{16,64}\.(png|jpe?g|webp|gif)$", re.IGNORECASE)


def uploads_dir() -> Path:
    folder = Path(settings.data_dir) / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _mime_for_suffix(suffix: str) -> str:
    s = (suffix or ".png").lower()
    if s in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if s == ".webp":
        return "image/webp"
    if s == ".gif":
        return "image/gif"
    return "image/png"


def _name_to_id(name: str) -> str:
    return Path(name).stem


def save_bytes(data: bytes, suffix: str = ".png") -> str:
    """Write image to DB + disk; return durable `/uploads/{id}{suffix}` path."""
    if not data or len(data) > 6_000_000:
        return ""
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    media_id = uuid.uuid4().hex
    name = f"{media_id}{suffix}"
    content_type = _mime_for_suffix(suffix)

    # Disk cache (may vanish on Railway redeploy without a volume)
    path = uploads_dir() / name
    try:
        path.write_bytes(data)
    except OSError:
        pass

    # Durable store — same Postgres as creatives/messages
    with SessionLocal() as db:
        db.merge(
            StoredMedia(id=media_id, content_type=content_type, data=data)
        )
        db.commit()

    return f"/uploads/{name}"


def load_bytes(url_or_name: str) -> tuple[bytes, str] | None:
    """Load image by `/uploads/name`, bare filename, or media id. Disk first, then DB."""
    raw = (url_or_name or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return None
    name = Path(raw).name
    if raw.startswith("/uploads/"):
        name = raw[len("/uploads/") :]
    if not name or ".." in name or "/" in name or "\\" in name:
        return None

    disk = uploads_dir() / name
    if disk.is_file():
        try:
            blob = disk.read_bytes()
        except OSError:
            blob = b""
        if blob:
            return blob, _mime_for_suffix(disk.suffix)

    media_id = _name_to_id(name)
    with SessionLocal() as db:
        row = db.get(StoredMedia, media_id)
        if row is None or not row.data:
            return None
        # Restore disk cache for StaticFiles / next hits
        try:
            if _SAFE_NAME_RE.match(name):
                disk.write_bytes(row.data)
        except OSError:
            pass
        return bytes(row.data), (row.content_type or "image/png")


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
    """Save chat photos; return [{type,url}] with durable /uploads paths only."""
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
