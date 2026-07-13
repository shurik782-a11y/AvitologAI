"""Project + global memory: compact rules, capped prompts, smart scope."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import GlobalMemory, Memory, utcnow
from app.services.openrouter import OpenRouterError, chat_completions

# Prompt budget: keep orchestrator context small and high-signal
_MAX_PROJECT_RULES = 10
_MAX_GLOBAL_RULES = 12
_MAX_PROMPT_CHARS = 2200
_RULE_KIND = "rule"


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:400]


def _fingerprint(text: str) -> str:
    return hashlib.sha1(_norm_key(text).encode("utf-8")).hexdigest()[:16]


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
    # Soft-dedupe by fingerprint prefix in content
    fp = _fingerprint(content_norm)
    near = db.scalars(
        select(Memory).where(
            Memory.project_id == project_id,
            Memory.kind == kind,
            Memory.content.contains(f"#{fp}"),
        )
    ).first()
    if near:
        near.hits += 1
        near.content = content_norm if f"#{fp}" in content_norm else f"{content_norm} #{fp}"
        near.updated_at = utcnow()
        db.add(near)
        db.commit()
        db.refresh(near)
        return near
    row = Memory(
        project_id=project_id,
        kind=kind,
        content=f"{content_norm} #{fp}" if kind == _RULE_KIND else content_norm,
        hits=1,
    )
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
    fp = _fingerprint(content_norm)
    near = db.scalars(
        select(GlobalMemory).where(
            GlobalMemory.kind == kind,
            GlobalMemory.content.contains(f"#{fp}"),
        )
    ).first()
    if near:
        near.hits += 1
        near.content = content_norm if f"#{fp}" in content_norm else f"{content_norm} #{fp}"
        near.updated_at = utcnow()
        db.add(near)
        db.commit()
        db.refresh(near)
        return near
    row = GlobalMemory(
        kind=kind,
        content=f"{content_norm} #{fp}" if kind == _RULE_KIND else content_norm,
        hits=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remember_revision(db: Session, project_id: int, revision_text: str) -> Memory | None:
    """Store only durable preferences / frequent actions — not every one-off fix."""
    text = revision_text.strip()
    lower = text.lower()
    kind = None
    if any(w in lower for w in ("всегда", "никогда", "предпочитаю", "обычно", "часто")):
        kind = "preference"
    elif any(w in lower for w in ("добавь", "убери", "короче", "длиннее", "цена", "заголовок")):
        kind = "frequent_action"
    if not kind:
        return None
    return upsert_memory(db, project_id, kind, text[:400])


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


def _heuristic_scope(revision_text: str) -> tuple[str, bool]:
    """Return (scope, confident). Skip LLM when confident."""
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
        return "project", True
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
        return "global", True
    return "project", False


def _compact_rule(summary: str) -> str:
    s = re.sub(r"\s+", " ", summary.strip())[:280]
    return f"avoid→fix: {s}"


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
    One compact rule per mistake (not duplicate mistake+fix_rule prose).
    LLM classify only when heuristic is unsure — saves tokens.
    """
    text = revision_text.strip()[:1000]
    scope, confident = _heuristic_scope(text)
    summary = text
    reason = "heuristic"

    if not confident and api_key and model:
        system = (
            "Классифицируй правку к объявлению Авито. "
            "scope=global — универсально для всех проектов; scope=project — ниша/бренд/товар. "
            "summary — одна короткая формулировка правила (что избегать / как исправить). "
            'JSON: {"scope":"global"|"project","summary":"...","reason":"..."}'
        )
        try:
            raw = await chat_completions(
                api_key,
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"Черновик: {prev_title or '—'}\nПравка: {text}",
                    },
                ],
                temperature=0.1,
                max_tokens=220,
            )
            content = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            data = _parse_scope_json(content)
            s = str(data.get("scope") or "").strip().lower()
            if s in {"global", "project"}:
                scope = s
            summary = str(data.get("summary") or text).strip()[:280] or text
            reason = str(data.get("reason") or reason).strip()[:200]
        except OpenRouterError:
            pass

    rule = _compact_rule(summary)
    if scope == "global":
        upsert_global_memory(db, _RULE_KIND, rule)
    else:
        upsert_memory(db, project_id, _RULE_KIND, rule)
    remember_revision(db, project_id, text)
    return {"scope": scope, "summary": summary, "reason": reason}


def _strip_fp(content: str) -> str:
    return re.sub(r"\s*#[0-9a-f]{8,16}\s*$", "", content).strip()


def memories_as_prompt(db: Session, project_id: int) -> str:
    """Compact high-signal rules only; capped size for model cost/latency."""
    project_rows = [
        m
        for m in list_memories(db, project_id, limit=_MAX_PROJECT_RULES * 2)
        if m.kind in {_RULE_KIND, "preference", "frequent_action", "mistake", "fix_rule"}
    ][:_MAX_PROJECT_RULES]
    global_rows = [
        m
        for m in list_global_memories(db, limit=_MAX_GLOBAL_RULES * 2)
        if m.kind in {_RULE_KIND, "mistake", "fix_rule"}
    ][:_MAX_GLOBAL_RULES]

    parts: list[str] = []
    budget = _MAX_PROMPT_CHARS

    def _add_block(title: str, rows: list[Any]) -> None:
        nonlocal budget
        if not rows or budget < 80:
            return
        lines: list[str] = []
        used = len(title) + 2
        for m in rows:
            line = f"- {_strip_fp(m.content)}"
            if used + len(line) + 1 > budget:
                break
            lines.append(line)
            used += len(line) + 1
        if lines:
            block = title + "\n" + "\n".join(lines)
            parts.append(block)
            budget -= len(block) + 2

    _add_block("Глобальные правила (не повторять):", global_rows)
    _add_block("Правила проекта (не повторять):", project_rows)

    if not parts:
        return "Память пуста."
    return "\n\n".join(parts)
