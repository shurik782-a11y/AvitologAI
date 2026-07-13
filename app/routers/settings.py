"""Global app settings (OpenRouter + models + orchestrator instruction)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import AppSettings, get_db, utcnow
from app.schemas import AppSettingsOut, AppSettingsUpdate

router = APIRouter()


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"


@router.get("", response_model=AppSettingsOut)
def get_settings(db: Session = Depends(get_db)) -> AppSettingsOut:
    row = db.get(AppSettings, 1)
    assert row is not None
    key = row.openrouter_api_key or settings.openrouter_api_key
    return AppSettingsOut(
        openrouter_api_key_set=bool(key),
        openrouter_api_key_masked=_mask(key),
        orchestrator_model=row.orchestrator_model or settings.orchestrator_model,
        vision_model=row.vision_model or settings.vision_model,
        image_model=row.image_model or settings.image_model,
        orchestrator_instruction=row.orchestrator_instruction
        or settings.default_orchestrator_instruction,
        default_orchestrator_model=settings.orchestrator_model,
        default_vision_model=settings.vision_model,
        default_image_model=settings.image_model,
    )


@router.put("", response_model=AppSettingsOut)
def update_settings(body: AppSettingsUpdate, db: Session = Depends(get_db)) -> AppSettingsOut:
    row = db.get(AppSettings, 1)
    assert row is not None
    data = body.model_dump(exclude_unset=True)
    if "openrouter_api_key" in data and data["openrouter_api_key"] is not None:
        val = data["openrouter_api_key"].strip()
        if val and not val.startswith("•"):
            row.openrouter_api_key = val
    for field in ("orchestrator_model", "vision_model", "image_model", "orchestrator_instruction"):
        if field in data and data[field] is not None:
            setattr(row, field, data[field])
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    return get_settings(db)
