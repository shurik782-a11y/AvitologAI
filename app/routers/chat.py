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
from app.services.status_steps import emit_status
from app.services.test_run import (
    enable_test_run,
    is_test_run,
    match_test_run_trigger,
    test_run_banner,
)

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

    triggered, remainder = match_test_run_trigger(body.content or "")
    content = remainder if triggered else (body.content or "")
    just_enabled = False
    if triggered:
        project = enable_test_run(db, project)
        just_enabled = True

    try:
        pre_orch: list[Message] = []
        # Only the trigger phrase, no brief yet
        if just_enabled and not content.strip() and not (body.images or []):
            user_msg = Message(
                project_id=project.id,
                role="user",
                content=body.content or "тестовый прогон",
                attachments=[],
                meta={"test_run": True, "trigger": True},
            )
            db.add(user_msg)
            db.commit()
            db.refresh(user_msg)
            statuses = [
                emit_status(db, project.id, "Включаю тестовый прогон", "test_run"),
                emit_status(db, project.id, "Эмулирую подключение Авито", "test_avito"),
            ]
            if (project.onboarding_status or "") == "awaiting_brief":
                tip = (
                    test_run_banner()
                    + "\n\nОпишите нишу и продукт — заполню поля проекта (онбординг). "
                    "Потом напишите **сделай пост**."
                )
            else:
                tip = (
                    test_run_banner()
                    + "\n\nНастройка уже есть. Напишите **сделай пост** — соберу объявление."
                )
            assistant = Message(
                project_id=project.id,
                role="assistant",
                content=tip,
                attachments=[],
                meta={"test_run": True, "delivery": True},
            )
            db.add(assistant)
            db.add(MetricEvent(project_id=project.id, name="test_run.enabled", value=1))
            db.commit()
            db.refresh(assistant)
            return ChatResponse(
                messages=[MessageOut.model_validate(user_msg)]
                + [MessageOut.model_validate(m) for m in [*statuses, assistant]],
                creative=None,
                onboarding_done=(project.onboarding_status or "") == "done",
            )

        if (project.onboarding_status or "") == "awaiting_brief":
            # Prefix banner once when entering via trigger + brief
            pre: list[Message] = []
            if just_enabled:
                pre.append(emit_status(db, project.id, "Включаю тестовый прогон", "test_run"))
                pre.append(emit_status(db, project.id, "Эмулирую подключение Авито", "test_avito"))
            user_msg, assistant_msgs, done = await run_onboarding(
                db, project, content, images=body.images
            )
            if just_enabled and assistant_msgs:
                # Prepend banner into last assistant-visible flow
                banner = Message(
                    project_id=project.id,
                    role="assistant",
                    content=test_run_banner(),
                    meta={"test_run": True, "banner": True},
                )
                db.add(banner)
                db.commit()
                db.refresh(banner)
                pre.append(banner)
            return ChatResponse(
                messages=[MessageOut.model_validate(user_msg)]
                + [MessageOut.model_validate(m) for m in [*pre, *assistant_msgs]],
                creative=None,
                onboarding_done=done,
            )

        pre_orch = []
        if just_enabled and (project.onboarding_status or "") == "done":
            pre_orch.append(emit_status(db, project.id, "Включаю тестовый прогон", "test_run"))
            pre_orch.append(emit_status(db, project.id, "Эмулирую подключение Авито", "test_avito"))
            if not content.strip():
                content = "сделай пост"

        user_msg, assistant_msgs, creative = await run_orchestrator(
            db,
            project,
            user_text=content or "сделай пост",
            images=body.images,
            revise_of_creative_id=body.revise_of_creative_id,
        )
        return ChatResponse(
            messages=[MessageOut.model_validate(user_msg)]
            + [MessageOut.model_validate(m) for m in [*pre_orch, *assistant_msgs]],
            creative=CreativeOut.model_validate(creative) if creative else None,
            onboarding_done=False,
        )
    except OpenRouterError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Orchestrator failed: {exc}") from exc


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
    if is_test_run(project) and not creative.avito_item_id:
        creative.avito_item_id = f"test-{project_id}-{creative_id}"
    creative.publish_status = "test_published" if is_test_run(project) else "approved"
    if not creative.published_at:
        from app.db import utcnow

        creative.published_at = utcnow()
    db.add(creative)
    db.add(
        MetricEvent(
            project_id=project_id,
            name="creative.approved",
            value=1,
            payload={"note": body.note, "test_run": is_test_run(project)},
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

    msg = (
        "Тестовый прогон: утверждено, публикация эмулирована"
        if is_test_run(project)
        else "Утверждено, фид обновлён"
    )
    return ApproveResponse(
        creative=CreativeOut.model_validate(creative),
        feed_url=feed_url,
        publish_run_id=run.id if run else None,
        message=msg,
    )
