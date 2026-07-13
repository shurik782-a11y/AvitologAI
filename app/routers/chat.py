"""Chat + creative approval inside a project."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Creative, Message, MetricEvent, Project, get_db
from app.schemas import ApproveRequest, ChatRequest, ChatResponse, CreativeOut, MessageOut
from app.services.orchestrator import run_orchestrator
from app.services.openrouter import OpenRouterError

router = APIRouter()


@router.get("/projects/{project_id}/messages", response_model=list[MessageOut])
def list_messages(project_id: int, db: Session = Depends(get_db)) -> list[Message]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return list(
        db.scalars(select(Message).where(Message.project_id == project_id).order_by(Message.id.asc()))
    )


@router.get("/projects/{project_id}/creatives", response_model=list[CreativeOut])
def list_creatives(project_id: int, db: Session = Depends(get_db)) -> list[Creative]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return list(
        db.scalars(
            select(Creative).where(Creative.project_id == project_id).order_by(Creative.id.desc())
        )
    )


@router.post("/projects/{project_id}/chat", response_model=ChatResponse)
async def chat(project_id: int, body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        user_msg, assistant_msg, creative = await run_orchestrator(
            db,
            project,
            user_text=body.content,
            images=body.images,
            generate_images=body.generate_images,
            revise_of_creative_id=body.revise_of_creative_id,
        )
    except OpenRouterError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Orchestrator failed: {exc}") from exc
    return ChatResponse(
        messages=[MessageOut.model_validate(user_msg), MessageOut.model_validate(assistant_msg)],
        creative=CreativeOut.model_validate(creative),
    )


@router.post("/projects/{project_id}/creatives/{creative_id}/approve", response_model=CreativeOut)
def approve_creative(
    project_id: int,
    creative_id: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
) -> Creative:
    creative = db.get(Creative, creative_id)
    if not creative or creative.project_id != project_id:
        raise HTTPException(404, "Creative not found")
    creative.status = "approved"
    db.add(creative)
    db.add(
        MetricEvent(
            project_id=project_id,
            name="creative.approved",
            value=1,
            payload={"note": body.note},
        )
    )
    db.add(
        Message(
            project_id=project_id,
            role="assistant",
            content="Креатив утверждён. (Публикация на Avito — в следующей версии через Автозагрузку.)",
            meta={"creative_id": creative_id, "approved": True},
        )
    )
    db.commit()
    db.refresh(creative)
    return creative
