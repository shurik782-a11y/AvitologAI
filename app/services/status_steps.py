"""Explicit agent status lines shown in project chat."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import Message


def emit_status(db: Session, project_id: int, text: str, step: str) -> Message:
    """Persist a short action status for the user (not for LLM history)."""
    msg = Message(
        project_id=project_id,
        role="assistant",
        content=text.strip(),
        attachments=[],
        meta={"status": True, "step": step},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def is_status_message(msg: Message) -> bool:
    meta = msg.meta or {}
    return bool(meta.get("status"))
