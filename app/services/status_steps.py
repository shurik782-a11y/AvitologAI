"""Explicit agent status lines shown in project chat."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Message


def emit_status(db: Session, project_id: int, text: str, step: str) -> Message:
    """Persist a short action status for the user (not for LLM history)."""
    label = (text or "").strip().strip("*").strip()
    # System status lines only: **Шаг** — ad copy must stay plain text without markdown.
    content = f"**{label}**" if label else ""
    msg = Message(
        project_id=project_id,
        role="assistant",
        content=content,
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


def clear_status_messages(db: Session, project_id: int) -> int:
    """Remove finished thinking steps so they do not clutter chat history."""
    rows = list(
        db.scalars(select(Message).where(Message.project_id == project_id))
    )
    ids = [m.id for m in rows if is_status_message(m)]
    if not ids:
        return 0
    db.execute(delete(Message).where(Message.id.in_(ids)))
    db.commit()
    return len(ids)
