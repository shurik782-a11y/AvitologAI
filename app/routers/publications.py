"""Project publications + Avito upload."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Creative, Message, MetricEvent, Project, PublishRun, get_db
from app.schemas import CreativeOut, PublishRunOut
from app.services import avito_autoload
from app.services.avito_autoload import AvitoError
from app.services.avito_feed import build_feed_xml, feed_public_url, write_feed_cache

router = APIRouter()


def project_to_feed_url(project: Project) -> str:
    return feed_public_url(project)


@router.get("/{project_id}/publications", response_model=list[CreativeOut])
def list_publications(project_id: int, db: Session = Depends(get_db)) -> list[Creative]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return list(
        db.scalars(
            select(Creative)
            .where(Creative.project_id == project_id, Creative.status == "approved")
            .order_by(Creative.id.desc())
        )
    )


@router.get("/{project_id}/publish-runs", response_model=list[PublishRunOut])
def list_runs(project_id: int, db: Session = Depends(get_db)) -> list[PublishRun]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return list(
        db.scalars(
            select(PublishRun).where(PublishRun.project_id == project_id).order_by(PublishRun.id.desc()).limit(20)
        )
    )


@router.post("/{project_id}/publish", response_model=PublishRunOut)
async def trigger_publish(project_id: int, db: Session = Depends(get_db)) -> PublishRun:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return await _run_publish(db, project)


async def _run_publish(db: Session, project: Project) -> PublishRun:
    from app.services.test_run import is_test_run

    if not project.avito_feed_token:
        project.avito_feed_token = secrets.token_urlsafe(16)
        db.add(project)
        db.commit()
        db.refresh(project)

    xml = build_feed_xml(db, project)
    write_feed_cache(project, xml)
    feed_url = feed_public_url(project)
    run = PublishRun(project_id=project.id, status="feed_ready", feed_url=feed_url, report={})
    db.add(run)
    db.commit()
    db.refresh(run)

    if is_test_run(project):
        run.status = "test_emulated"
        run.report = {
            "test_run": True,
            "hint": "Тестовый прогон: выгрузка в кабинет Авито не выполнялась (эмуляция).",
        }
        run.upload_id = f"test-upload-{project.id}-{run.id}"
    elif project.avito_client_id and project.avito_client_secret:
        try:
            token = await avito_autoload.get_token(project.avito_client_id, project.avito_client_secret)
            await avito_autoload.ensure_autoload_profile(project, feed_url, token)
            result = await avito_autoload.trigger_upload(token)
            run.status = "upload_triggered"
            run.report = result
            run.upload_id = str(result.get("upload_id") or result.get("id") or "")
        except AvitoError as exc:
            run.status = "upload_error"
            run.error = str(exc)
    else:
        run.status = "feed_only"
        run.report = {"hint": "Скопируйте feed_url в кабинет Автозагрузки Авито"}

    db.add(run)
    db.add(
        MetricEvent(
            project_id=project.id,
            name="publish.run",
            value=1,
            payload={"status": run.status, "test_run": is_test_run(project)},
        )
    )
    db.commit()
    db.refresh(run)
    return run


def approve_and_publish_sync_message(
    db: Session, project: Project, creative: Creative, feed_url: str, run: PublishRun | None
) -> list[Message]:
    from app.services.status_steps import emit_status
    from app.services.test_run import is_test_run

    if is_test_run(project):
        emit_status(db, project.id, "Эмулирую публикацию на Авито", "publish_test")
        ready = Message(
            project_id=project.id,
            role="assistant",
            content=(
                f"Тестовый прогон: объявление «{creative.title or creative.id}» утверждено.\n"
                f"Публикация эмулирована (как будто Авито подключён). "
                f"Статус: {run.status if run else 'test_emulated'}.\n"
                f"Память правок и обучение сохранены. Feed (локальный): {feed_url}"
            ),
            meta={
                "creative_id": creative.id,
                "approved": True,
                "test_run": True,
                "feed_url": feed_url,
                "delivery": True,
            },
        )
    else:
        emit_status(db, project.id, "Отправляю на публикацию", "publish")
        detail = (
            f"Статус подгрузки: {run.status}"
            if run
            else "Фид обновлён — подгрузку можно запустить в разделе Публикации."
        )
        ready = Message(
            project_id=project.id,
            role="assistant",
            content=(
                f"Готово: объявление «{creative.title or creative.id}» добавлено в XML-фид.\n"
                f"{detail}\nFeed: {feed_url}"
            ),
            meta={"creative_id": creative.id, "approved": True, "feed_url": feed_url, "delivery": True},
        )
    db.add(ready)
    db.commit()
    db.refresh(ready)
    from app.services.status_steps import clear_status_messages

    clear_status_messages(db, project.id)
    return [ready]
