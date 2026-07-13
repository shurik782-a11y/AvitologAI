"""Projects CRUD + memories + onboarding seed."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Message, MetricEvent, Project, get_db, utcnow
from app.schemas import MemoryCreate, MemoryOut, ProjectCreate, ProjectOut, ProjectUpdate
from app.services import memory as memory_svc
from app.services.avito_feed import ensure_feed_token, feed_public_url
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
    for k, v in data.items():
        setattr(row, k, v)
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
