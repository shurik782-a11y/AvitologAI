"""Projects CRUD + memories."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import MetricEvent, Project, get_db, utcnow
from app.schemas import MemoryCreate, MemoryOut, ProjectCreate, ProjectOut, ProjectUpdate
from app.services import memory as memory_svc

router = APIRouter()


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.updated_at.desc())))


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)) -> Project:
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
        extra=body.extra or {},
    )
    db.add(row)
    db.add(MetricEvent(project_id=None, name="project.created", value=1))
    db.commit()
    db.refresh(row)
    return row


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    return row


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)) -> Project:
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
