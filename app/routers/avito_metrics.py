"""Avito publication metrics — refresh only on demand."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import AvitoStatSnapshot, Creative, Project, get_db, utcnow
from app.schemas import PublicationMetricOut, StatSnapshotOut
from app.services import avito_autoload
from app.services.avito_autoload import AvitoError

router = APIRouter()


@router.get("/projects/{project_id}/metrics/publications", response_model=list[PublicationMetricOut])
def list_metric_publications(project_id: int, db: Session = Depends(get_db)) -> list[PublicationMetricOut]:
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    creatives = list(
        db.scalars(
            select(Creative)
            .where(Creative.project_id == project_id, Creative.status == "approved")
            .order_by(Creative.id.desc())
        )
    )
    out: list[PublicationMetricOut] = []
    for c in creatives:
        snap = db.scalars(
            select(AvitoStatSnapshot)
            .where(AvitoStatSnapshot.creative_id == c.id)
            .order_by(AvitoStatSnapshot.id.desc())
            .limit(1)
        ).first()
        out.append(
            PublicationMetricOut(
                creative_id=c.id,
                title=c.title,
                avito_item_id=c.avito_item_id,
                avito_ad_id=c.avito_ad_id,
                publish_status=c.publish_status,
                status=c.status,
                fetched_at=snap.fetched_at if snap else None,
                has_snapshot=bool(snap),
            )
        )
    return out


@router.get(
    "/projects/{project_id}/metrics/publications/{creative_id}",
    response_model=StatSnapshotOut,
)
def get_snapshot(project_id: int, creative_id: int, db: Session = Depends(get_db)) -> StatSnapshotOut:
    creative = db.get(Creative, creative_id)
    if not creative or creative.project_id != project_id:
        raise HTTPException(404, "Creative not found")
    snap = db.scalars(
        select(AvitoStatSnapshot)
        .where(AvitoStatSnapshot.creative_id == creative_id)
        .order_by(AvitoStatSnapshot.id.desc())
        .limit(1)
    ).first()
    if not snap:
        return StatSnapshotOut(
            creative_id=creative_id,
            avito_item_id=creative.avito_item_id,
            payload={},
            fetched_at=None,
            message="Ещё не обновляли — нажмите «Обновить»",
        )
    return StatSnapshotOut(
        creative_id=creative_id,
        avito_item_id=snap.avito_item_id,
        payload=snap.payload,
        fetched_at=snap.fetched_at,
        message="",
    )


@router.post(
    "/projects/{project_id}/metrics/publications/{creative_id}/refresh",
    response_model=StatSnapshotOut,
)
async def refresh_snapshot(project_id: int, creative_id: int, db: Session = Depends(get_db)) -> StatSnapshotOut:
    project = db.get(Project, project_id)
    creative = db.get(Creative, creative_id)
    if not project or not creative or creative.project_id != project_id:
        raise HTTPException(404, "Not found")
    if not creative.avito_item_id:
        raise HTTPException(
            400,
            "Нет avito_item_id у публикации. Укажите ID объявления Авито после выгрузки или дождитесь отчёта Автозагрузки.",
        )
    if not project.avito_client_id or not project.avito_client_secret or not project.avito_user_id:
        raise HTTPException(400, "Заполните Avito client_id, client_secret и user_id в настройках проекта")

    try:
        token = await avito_autoload.get_token(project.avito_client_id, project.avito_client_secret)
        info = await avito_autoload.get_item_info(token, project.avito_user_id, creative.avito_item_id)
        stats = await avito_autoload.get_item_stats(token, project.avito_user_id, [creative.avito_item_id])
        payload = {"item": info, "stats": stats}
    except AvitoError as exc:
        raise HTTPException(400, str(exc)) from exc

    snap = AvitoStatSnapshot(
        project_id=project_id,
        creative_id=creative_id,
        avito_item_id=creative.avito_item_id,
        payload=payload,
        fetched_at=utcnow(),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return StatSnapshotOut(
        creative_id=creative_id,
        avito_item_id=snap.avito_item_id,
        payload=snap.payload,
        fetched_at=snap.fetched_at,
        message="Обновлено",
    )
