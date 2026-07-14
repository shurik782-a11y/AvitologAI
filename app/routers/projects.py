"""Projects CRUD + memories + onboarding seed + competitor import."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db import Message, MetricEvent, Project, get_db, utcnow
from app.schemas import (
    CompetitorsImportResult,
    MemoryCreate,
    MemoryOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from app.services import memory as memory_svc
from app.services.avito_feed import ensure_feed_token, feed_public_url
from app.services.competitors import import_competitors_table
from app.services.media_store import persist_reference_list
from app.services.onboarding import ONBOARDING_SEED

router = APIRouter()


def serialize_project(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        theme=p.theme or "",
        ideas=p.ideas or "",
        constraints=p.constraints or "",
        orchestrator_model=p.orchestrator_model or "",
        vision_model=p.vision_model or "",
        image_model=p.image_model or "",
        orchestrator_prompt=p.orchestrator_prompt or "",
        vision_prompt=p.vision_prompt or "",
        image_style_prompt=p.image_style_prompt or "",
        listing_type=getattr(p, "listing_type", "") or "",
        advantages=getattr(p, "advantages", "") or "",
        buyer_pains=getattr(p, "buyer_pains", "") or "",
        why_here=getattr(p, "why_here", "") or "",
        ad_idea=getattr(p, "ad_idea", "") or "",
        search_query=getattr(p, "search_query", "") or "",
        conversion_offer=getattr(p, "conversion_offer", "") or "",
        company_info=getattr(p, "company_info", "") or "",
        photo_count=int(getattr(p, "photo_count", None) or settings.photo_count_default),
        allow_people=bool(getattr(p, "allow_people", False)),
        allow_text_overlays=bool(getattr(p, "allow_text_overlays", False)),
        competitor_insights=getattr(p, "competitor_insights", "") or "",
        visual_style_notes=getattr(p, "visual_style_notes", "") or "",
        onboarding_status=p.onboarding_status or "awaiting_brief",
        avito_feed_token=p.avito_feed_token or "",
        avito_category=p.avito_category or "",
        avito_address=p.avito_address or "",
        avito_contact_phone=p.avito_contact_phone or "",
        avito_client_id=p.avito_client_id or "",
        avito_user_id=p.avito_user_id or "",
        avito_client_secret_set=bool(p.avito_client_secret),
        feed_url=feed_public_url(p),
        extra=p.extra or {},
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    rows = list(db.scalars(select(Project).order_by(Project.updated_at.desc())))
    out: list[ProjectOut] = []
    for row in rows:
        ensure_feed_token(db, row)
        out.append(serialize_project(row))
    return out


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    row = Project(
        name=body.name.strip(),
        theme=body.theme,
        ideas=body.ideas,
        constraints=body.constraints,
        orchestrator_model=body.orchestrator_model,
        vision_model=body.vision_model,
        image_model=body.image_model,
        orchestrator_prompt=body.orchestrator_prompt,
        vision_prompt=body.vision_prompt,
        image_style_prompt=body.image_style_prompt,
        listing_type=body.listing_type,
        advantages=body.advantages,
        buyer_pains=body.buyer_pains,
        why_here=body.why_here,
        ad_idea=body.ad_idea,
        search_query=body.search_query,
        conversion_offer=body.conversion_offer,
        company_info=body.company_info,
        photo_count=max(1, min(int(body.photo_count or 1), settings.photo_count_max)),
        allow_people=bool(body.allow_people),
        allow_text_overlays=bool(body.allow_text_overlays),
        competitor_insights=body.competitor_insights,
        visual_style_notes=body.visual_style_notes,
        avito_category=body.avito_category,
        avito_address=body.avito_address,
        avito_contact_phone=body.avito_contact_phone,
        avito_client_id=body.avito_client_id,
        avito_client_secret=body.avito_client_secret,
        avito_user_id=body.avito_user_id,
        onboarding_status="awaiting_brief",
        avito_feed_token=secrets.token_urlsafe(16),
        extra=body.extra or {},
    )
    db.add(row)
    db.flush()
    db.add(
        Message(
            project_id=row.id,
            role="assistant",
            content=ONBOARDING_SEED,
            meta={"onboarding": True, "seed": True},
        )
    )
    db.add(MetricEvent(project_id=row.id, name="project.created", value=1))
    db.commit()
    db.refresh(row)
    return serialize_project(row)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    ensure_feed_token(db, row)
    return serialize_project(row)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectOut:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    data = body.model_dump(exclude_unset=True)
    if "avito_client_secret" in data and data["avito_client_secret"] is not None:
        secret = data["avito_client_secret"].strip()
        if secret and not secret.startswith("•"):
            row.avito_client_secret = secret
        data.pop("avito_client_secret", None)
    if "photo_count" in data and data["photo_count"] is not None:
        data["photo_count"] = max(1, min(int(data["photo_count"]), settings.photo_count_max))
    if "extra" in data and data["extra"] is not None:
        incoming = dict(data["extra"] or {})
        merged = dict(row.extra or {})
        if "reference_images" in incoming:
            merged["reference_images"] = persist_reference_list(
                incoming.get("reference_images") or [], max_n=5
            )
            if merged["reference_images"]:
                merged["reference_received"] = True
        for k, v in incoming.items():
            if k == "reference_images":
                continue
            merged[k] = v
        data["extra"] = merged
    for k, v in data.items():
        setattr(row, k, v)
    if "extra" in data:
        flag_modified(row, "extra")
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_feed_token(db, row)
    return serialize_project(row)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/competitors/import", response_model=CompetitorsImportResult)
async def competitors_import(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> CompetitorsImportResult:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    try:
        result = await import_competitors_table(db, row, raw, filename=file.filename or "data.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Импорт не удался: {exc}") from exc
    return result


@router.get("/{project_id}/memories", response_model=list[MemoryOut])
def get_memories(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return memory_svc.list_memories(db, project_id)


@router.post("/{project_id}/memories", response_model=MemoryOut)
def add_memory(project_id: int, body: MemoryCreate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return memory_svc.upsert_memory(db, project_id, body.kind, body.content)
