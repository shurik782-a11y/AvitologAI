"""Simple metrics aggregation."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import MetricEvent, get_db
from app.schemas import MetricsOut

router = APIRouter()


@router.get("", response_model=MetricsOut)
def metrics(project_id: int | None = None, db: Session = Depends(get_db)) -> MetricsOut:
    q = select(MetricEvent).order_by(MetricEvent.id.desc()).limit(500)
    if project_id is not None:
        q = q.where(MetricEvent.project_id == project_id)
    rows = list(db.scalars(q))
    totals: dict[str, float] = defaultdict(float)
    for r in rows:
        totals[r.name] += r.value
    recent = [
        {
            "id": r.id,
            "name": r.name,
            "value": r.value,
            "project_id": r.project_id,
            "created_at": r.created_at.isoformat(),
            "payload": r.payload,
        }
        for r in rows[:40]
    ]
    return MetricsOut(project_id=project_id, totals=dict(totals), recent=recent)
