"""Chat + creative approval inside a project."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Creative, Message, MetricEvent, Project, get_db
from app.routers.publications import _run_publish, approve_and_publish_sync_message
from app.schemas import (
    ApproveRequest,
    ApproveResponse,
    ChatRequest,
    ChatResponse,
    CreativeOut,
    MessageOut,
)
from app.services.avito_feed import feed_public_url
from app.services.onboarding import run_onboarding
from app.services.openrouter import OpenRouterError
from app.services.orchestrator import run_orchestrator

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
        if (project.onboarding_status or "") == "awaiting_brief":
            user_msg, assistant_msgs = await run_onboarding(db, project, body.content)
            return ChatResponse(
                messages=[MessageOut.model_validate(user_msg)]
                + [MessageOut.model_validate(m) for m in assistant_msgs],
                creative=None,
                onboarding_done=True,
            )
        user_msg, assistant_msgs, creative = await run_orchestrator(
            db,
            project,
            user_text=body.content,
            images=body.images,
            revise_of_creative_id=body.revise_of_creative_id,
        )
    except OpenRouterError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Orchestrator failed: {exc}") from exc
    return ChatResponse(
        messages=[MessageOut.model_validate(user_msg)]
        + [MessageOut.model_validate(m) for m in assistant_msgs],
        creative=CreativeOut.model_validate(creative) if creative else None,
        onboarding_done=False,
    )


@router.patch("/projects/{project_id}/creatives/{creative_id}", response_model=CreativeOut)
def patch_creative(
    project_id: int,
    creative_id: int,
    body: dict,
    db: Session = Depends(get_db),
) -> Creative:
    creative = db.get(Creative, creative_id)
    if not creative or creative.project_id != project_id:
        raise HTTPException(404, "Creative not found")
    for key in ("avito_item_id", "avito_ad_id", "price", "publish_status", "title"):
        if key in body and body[key] is not None:
            setattr(creative, key, str(body[key]))
    db.add(creative)
    db.commit()
    db.refresh(creative)
    return creative


@router.post("/projects/{project_id}/creatives/{creative_id}/approve", response_model=ApproveResponse)
async def approve_creative(
    project_id: int,
    creative_id: int,
    body: ApproveRequest,
    db: Session = Depends(get_db),
) -> ApproveResponse:
    project = db.get(Project, project_id)
    creative = db.get(Creative, creative_id)
    if not project or not creative or creative.project_id != project_id:
        raise HTTPException(404, "Creative not found")
    creative.status = "approved"
    if not creative.avito_ad_id:
        creative.avito_ad_id = f"p{project_id}-c{creative_id}"
    creative.publish_status = "approved"
    if not creative.published_at:
        from app.db import utcnow

        creative.published_at = utcnow()
    db.add(creative)
    db.add(
        MetricEvent(
            project_id=project_id,
            name="creative.approved",
            value=1,
            payload={"note": body.note},
        )
    )
    db.commit()
    db.refresh(creative)

    run = None
    feed_url = feed_public_url(project)
    if body.trigger_upload:
        run = await _run_publish(db, project)
        feed_url = run.feed_url or feed_url
    approve_and_publish_sync_message(db, project, creative, feed_url, run)
    db.commit()
    db.refresh(creative)

    return ApproveResponse(
        creative=CreativeOut.model_validate(creative),
        feed_url=feed_url,
        publish_run_id=run.id if run else None,
        message="Утверждено, фид обновлён",
    )
