"""Build Avito Autoload XML feed for a project — clear, minimal, validator-friendly."""
from __future__ import annotations

import re
import secrets
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Creative, Project

# Avito Autoload common limits (formatVersion 3)
_TITLE_MAX = 50
_DESC_MAX = 7500
_PHONE_RE = re.compile(r"[^\d+]")


def absolute_media_url(path: str) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    if base:
        return f"{base}{path}"
    return path


def ensure_feed_token(db: Session, project: Project) -> Project:
    """Backfill feed token for older projects (API keys not required)."""
    if not (project.avito_feed_token or "").strip():
        project.avito_feed_token = secrets.token_urlsafe(16)
        db.add(project)
        db.commit()
        db.refresh(project)
    return project


def feed_public_url(project: Project) -> str:
    token = (project.avito_feed_token or "").strip()
    if not token or not project.id:
        return ""
    base = (settings.public_base_url or "").rstrip("/")
    path = f"/api/projects/{project.id}/avito-feed.xml?token={token}"
    return f"{base}{path}" if base else path


def clean_title(raw: str) -> str:
    t = re.sub(r"\s+", " ", (raw or "").strip())
    for pat in (
        r"купить\s+онлайн(?:\s+с\s+(?:быстрой\s+)?доставкой)?",
        r"с\s+быстрой\s+доставкой",
        r"онлайн\s+с\s+доставкой",
        r"купить\s+онлайн",
        r"с\s+доставкой",
    ):
        t = re.sub(pat, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;-–—")
    if not t:
        t = "Объявление"
    if len(t) > _TITLE_MAX:
        t = t[:_TITLE_MAX].rstrip(" ,;-–—")
    return t


def clean_description(raw: str) -> str:
    t = (raw or "").strip()
    # Drop accidental English/JSON leaks if any slipped into stored draft
    low = t.lower()
    if "i need to" in low or '"need_images"' in low or "json object" in low:
        t = ""
    if len(t) > _DESC_MAX:
        t = t[:_DESC_MAX].rstrip()
    return t


def clean_phone(raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    # Keep leading + and digits only
    digits = _PHONE_RE.sub("", p)
    return digits[:20]


def re_price(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return digits or ""


def _text(el: ET.Element, tag: str, value: str) -> None:
    """Set element text; Avito XML is plain text (ET escapes automatically)."""
    child = ET.SubElement(el, tag)
    child.text = value


def build_feed_xml(db: Session, project: Project) -> str:
    """Build Autoload feed: one <Ad> per approved creative of this project only.

    Mapping (project / creative → XML):
    - Creative.avito_ad_id → Id (stable id for updates)
    - Creative.title → Title (≤50)
    - Creative.description → Description
    - Creative.price → Price (digits only; omit if empty)
    - Creative.images[].url → Images/Image@url (absolute HTTPS)
    - Project.avito_category → Category
    - Project.avito_address → Address
    - Project.avito_contact_phone → ContactPhone
    """
    creatives = list(
        db.scalars(
            select(Creative)
            .where(Creative.project_id == project.id, Creative.status == "approved")
            .order_by(Creative.id.asc())
        )
    )
    root = ET.Element("Ads", formatVersion="3", target="Avito.ru")
    category = (project.avito_category or "").strip()
    address = (project.avito_address or "").strip()
    phone = clean_phone(project.avito_contact_phone or "")

    for c in creatives:
        ad_id = (c.avito_ad_id or "").strip() or f"p{project.id}-c{c.id}"
        if not c.avito_ad_id:
            c.avito_ad_id = ad_id
            db.add(c)

        ad = ET.SubElement(root, "Ad")
        _text(ad, "Id", ad_id)
        _text(ad, "Title", clean_title(c.title or ""))
        desc = clean_description(c.description or "")
        _text(ad, "Description", desc or "Описание уточняется")

        price = re_price(c.price or "")
        if price:
            _text(ad, "Price", price)

        if category:
            _text(ad, "Category", category)
        if address:
            _text(ad, "Address", address)
        if phone:
            _text(ad, "ContactPhone", phone)

        urls: list[str] = []
        for img in c.images or []:
            url = img.get("url") if isinstance(img, dict) else None
            if not url:
                continue
            abs_url = absolute_media_url(str(url))
            if abs_url.startswith("http://") or abs_url.startswith("https://"):
                urls.append(abs_url)
        if urls:
            images_el = ET.SubElement(ad, "Images")
            for abs_url in urls[:10]:
                ET.SubElement(images_el, "Image", url=abs_url)

    db.commit()
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def write_feed_cache(project: Project, xml: str) -> Path:
    folder = Path(settings.data_dir) / "feeds"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"project_{project.id}.xml"
    path.write_text(xml, encoding="utf-8")
    return path
