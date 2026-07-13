"""Project + global memory: learn from edits; scope mistakes smartly."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import GlobalMemory, Memory, utcnow
from app.services.openrouter import OpenRouterError, chat_completions


def list_memories(db: Session, project_id: int, limit: int = 30) -> list[Memory]:
    return list(
        db.scalars(
            select(Memory)
            .where(Memory.project_id == project_id)
            .order_by(Memory.hits.desc(), Memory.updated_at.desc())
            .limit(limit)
        )
    )


def list_global_memories(db: Session, limit: int = 40) -> list[GlobalMemory]:
    return list(
        db.scalars(
            select(GlobalMemory)
            .order_by(GlobalMemory.hits.desc(), GlobalMemory.updated_at.desc())
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


def upsert_global_memory(db: Session, kind: str, content: str) -> GlobalMemory:
    content_norm = content.strip()
    existing = db.scalars(
        select(GlobalMemory).where(
            GlobalMemory.kind == kind,
            GlobalMemory.content == content_norm,
        )
    ).first()
    if existing:
        existing.hits += 1
        existing.updated_at = utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = GlobalMemory(kind=kind, content=content_norm, hits=1)
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


def _parse_scope_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"scope": "project", "summary": text[:500], "reason": "fallback"}


def _heuristic_scope(revision_text: str) -> str:
    """Prefer global for generic style/copy rules; project for niche-specific notes."""
    lower = revision_text.lower()
    project_markers = (
        "бренд",
        "наш",
        "наша",
        "этой ниш",
        "этого товар",
        "артикул",
        "sku",
        "модель ",
        "только для",
        "в этом проекте",
    )
    if any(m in lower for m in project_markers):
        return "project"
    global_markers = (
        "короче",
        "длиннее",
        "заголовок",
        "кликбейт",
        "эмодзи",
        "цена",
        "без картин",
        "всегда",
        "никогда",
        "тон",
        "грамматик",
        "орфограф",
        "caps",
        "капс",
    )
    if any(m in lower for m in global_markers):
        return "global"
    return "project"


async def classify_and_remember_mistake(
    db: Session,
    project_id: int,
    revision_text: str,
    *,
    prev_title: str = "",
    api_key: str = "",
    model: str = "",
) -> dict[str, Any]:
    """
    Decide global vs project scope, store mistake + fix_rule.
    Returns {scope, summary, reason}.
    """
    text = revision_text.strip()[:1000]
    scope = _heuristic_scope(text)
    summary = text
    reason = "heuristic"

    if api_key and model:
        system = (
            "Классифицируй правку пользователя к объявлению Авито. "
            "scope=global — универсальная ошибка стиля/структуры/языка, полезная во всех проектах. "
            "scope=project — специфично для ниши, бренда, конкретного товара или проекта. "
            "Ответь строго JSON: "
            '{"scope":"global"|"project","summary":"кратко что было не так","reason":"почему такой scope"}.'
        )
        try:
            raw = await chat_completions(
                api_key,
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": (
                            f"Заголовок черновика: {prev_title or '—'}\n"
                            f"Правка пользователя: {text}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=400,
            )
            content = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            data = _parse_scope_json(content)
            s = str(data.get("scope") or "").strip().lower()
            if s in {"global", "project"}:
                scope = s
            summary = str(data.get("summary") or text).strip()[:500] or text
            reason = str(data.get("reason") or reason).strip()[:300]
        except OpenRouterError:
            pass

    mistake_line = f"Что было не так{f' ({prev_title})' if prev_title else ''}: {summary}"
    fix_line = f"Правка и почему: {summary}"

    if scope == "global":
        upsert_global_memory(db, "mistake", mistake_line)
        upsert_global_memory(db, "fix_rule", fix_line)
    else:
        upsert_memory(db, project_id, "mistake", mistake_line)
        upsert_memory(db, project_id, "fix_rule", fix_line)

    remember_revision(db, project_id, text)
    return {"scope": scope, "summary": summary, "reason": reason}


def memories_as_prompt(db: Session, project_id: int) -> str:
    project_rows = list_memories(db, project_id)
    global_rows = list_global_memories(db)
    parts: list[str] = []
    if global_rows:
        lines = [f"- [{m.kind} ×{m.hits}] {m.content}" for m in global_rows]
        parts.append(
            "Глобальные ошибки/правила (для всех проектов — не повторять):\n" + "\n".join(lines)
        )
    if project_rows:
        lines = [f"- [{m.kind} ×{m.hits}] {m.content}" for m in project_rows]
        parts.append(
            "Память этого проекта (mistake/fix_rule — не повторять):\n" + "\n".join(lines)
        )
    if not parts:
        return "Память проекта и глобальный пул пусты."
    return "\n\n".join(parts)
