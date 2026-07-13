"""Public Avito XML feed (token-gated, no Telegram admin auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import Project, get_db
from app.services.avito_feed import build_feed_xml, write_feed_cache

router = APIRouter()


@router.get("/projects/{project_id}/avito-feed.xml")
def get_feed(
    project_id: int,
    token: str = Query(""),
    db: Session = Depends(get_db),
) -> Response:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.avito_feed_token or token != project.avito_feed_token:
        raise HTTPException(403, "Bad feed token")
    xml = build_feed_xml(db, project)
    write_feed_cache(project, xml)
    return Response(content=xml, media_type="application/xml; charset=utf-8")
