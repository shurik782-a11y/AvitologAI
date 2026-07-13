"""Build Avito Autoload XML feed for a project."""
from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Creative, Project


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


def build_feed_xml(db: Session, project: Project) -> str:
    creatives = list(
        db.scalars(
            select(Creative)
            .where(Creative.project_id == project.id, Creative.status == "approved")
            .order_by(Creative.id.asc())
        )
    )
    root = ET.Element("Ads", formatVersion="3", target="Avito.ru")
    for c in creatives:
        ad_id = c.avito_ad_id or f"p{project.id}-c{c.id}"
        if not c.avito_ad_id:
            c.avito_ad_id = ad_id
            db.add(c)
        ad = ET.SubElement(root, "Ad")
        ET.SubElement(ad, "Id").text = ad_id
        ET.SubElement(ad, "Title").text = (c.title or "Объявление")[:50]
        ET.SubElement(ad, "Description").text = c.description or ""
        if c.price:
            ET.SubElement(ad, "Price").text = re_price(c.price)
        if project.avito_category:
            ET.SubElement(ad, "Category").text = project.avito_category
        if project.avito_address:
            ET.SubElement(ad, "Address").text = project.avito_address
        if project.avito_contact_phone:
            ET.SubElement(ad, "ContactPhone").text = project.avito_contact_phone
        images = ET.SubElement(ad, "Images")
        for img in c.images or []:
            url = img.get("url") if isinstance(img, dict) else None
            if url:
                ET.SubElement(images, "Image", url=absolute_media_url(url))
    db.commit()
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def re_price(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or "0"


def write_feed_cache(project: Project, xml: str) -> Path:
    folder = Path(settings.data_dir) / "feeds"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"project_{project.id}.xml"
    path.write_text(xml, encoding="utf-8")
    return path
