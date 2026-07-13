"""Project memory: learn from edits and frequent actions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Memory, utcnow


def list_memories(db: Session, project_id: int, limit: int = 30) -> list[Memory]:
    return list(
        db.scalars(
            select(Memory)
            .where(Memory.project_id == project_id)
            .order_by(Memory.hits.desc(), Memory.updated_at.desc())
            .limit(limit)
        )
    )


def upsert_memory(db: Session, project_id: int, kind: str, content: str) -> Memory:
    content_norm = content.strip()
    existing = db.scalars(
        select(Memory).where(
            Memory.project_id == project_id,
            Memory.kind == kind,
            Memory.content == content_norm,
        )
    ).first()
    if existing:
        existing.hits += 1
        existing.updated_at = utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = Memory(project_id=project_id, kind=kind, content=content_norm, hits=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remember_revision(db: Session, project_id: int, revision_text: str) -> Memory:
    """Store free-form revision as edit_pattern / preference."""
    text = revision_text.strip()
    kind = "edit_pattern"
    lower = text.lower()
    if any(w in lower for w in ("всегда", "никогда", "предпочитаю", "обычно", "часто")):
        kind = "preference"
    if any(w in lower for w in ("добавь", "убери", "короче", "длиннее", "цена", "заголовок")):
        kind = "frequent_action"
    return upsert_memory(db, project_id, kind, text[:1000])


def remember_mistake(
    db: Session,
    project_id: int,
    revision_text: str,
    *,
    prev_title: str = "",
) -> tuple[Memory, Memory]:
    """Remember what was wrong and the fix rule so future creatives avoid it."""
    text = revision_text.strip()[:1000]
    mistake = upsert_memory(
        db,
        project_id,
        "mistake",
        f"Что было не так{f' ({prev_title})' if prev_title else ''}: {text}",
    )
    fix = upsert_memory(
        db,
        project_id,
        "fix_rule",
        f"Правка и почему: {text}",
    )
    remember_revision(db, project_id, text)
    return mistake, fix


def memories_as_prompt(db: Session, project_id: int) -> str:
    rows = list_memories(db, project_id)
    if not rows:
        return "Память проекта пуста."
    lines = [f"- [{m.kind} ×{m.hits}] {m.content}" for m in rows]
    return (
        "Память проекта (учитывай при генерации; mistake/fix_rule — не повторять):\n"
        + "\n".join(lines)
    )
