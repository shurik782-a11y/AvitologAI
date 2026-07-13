"""Onboarding: first chat setup → project fields with explicit status steps."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db import AppSettings, Message, MetricEvent, Project
from app.services.openrouter import OpenRouterError, chat_completions
from app.services.status_steps import emit_status

ONBOARDING_SEED = (
    "Давайте выполним настройку\n\n"
    "Опишите свободным текстом нишу, тон объявлений, идеи и ограничения — "
    "я разложу это по полям проекта (их можно потом править в Настройках)."
)


def _parse_json(text: str) -> dict[str, Any]:
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
    return {
        "theme": text[:500],
        "ideas": "",
        "constraints": "",
        "orchestrator_prompt": "",
        "vision_prompt": "",
        "image_style_prompt": "",
    }


async def run_onboarding(
    db: Session, project: Project, user_text: str
) -> tuple[Message, list[Message]]:
    """Returns user message and all new assistant messages (statuses + summary)."""
    cfg = db.get(AppSettings, 1)
    assert cfg is not None
    api_key = cfg.openrouter_api_key or settings.openrouter_api_key
    model = (project.orchestrator_model or cfg.orchestrator_model or settings.orchestrator_model).strip()

    user_msg = Message(
        project_id=project.id,
        role="user",
        content=user_text,
        attachments=[],
        meta={"onboarding": True},
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    out: list[Message] = []
    out.append(emit_status(db, project.id, "Выделяю основные критерии", "criteria"))

    system = (
        "Ты настраиваешь проект AvitologAI. Из текста пользователя извлеки поля для объявлений Авито. "
        "Ответь строго JSON без markdown: "
        '{"theme":"...","ideas":"...","constraints":"...","orchestrator_prompt":"...",'
        '"vision_prompt":"...","image_style_prompt":"..."}.'
    )
    try:
        raw = await chat_completions(
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text or "Настрой проект по умолчанию для товаров на Авито."},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        content = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        data = _parse_json(content)
    except OpenRouterError as exc:
        data = {
            "theme": user_text[:500],
            "ideas": "",
            "constraints": "",
            "orchestrator_prompt": "",
            "vision_prompt": "",
            "image_style_prompt": "",
        }
        db.add(
            MetricEvent(
                project_id=project.id,
                name="onboarding.error",
                value=1,
                payload={"error": str(exc)[:400]},
            )
        )

    theme = str(data.get("theme") or "").strip()
    ideas = str(data.get("ideas") or "").strip()
    constraints = str(data.get("constraints") or "").strip()
    orch = str(data.get("orchestrator_prompt") or "").strip()
    vision = str(data.get("vision_prompt") or "").strip()
    style = str(data.get("image_style_prompt") or "").strip()

    out.append(
        emit_status(
            db,
            project.id,
            f"Фиксирую идею: {ideas or theme or 'по вашему описанию'}"[:400],
            "idea",
        )
    )
    if theme:
        project.theme = theme
    if ideas:
        project.ideas = ideas

    out.append(
        emit_status(
            db,
            project.id,
            f"Устанавливаю ограничения: {constraints or 'без жёстких ограничений'}"[:400],
            "constraints",
        )
    )
    if constraints:
        project.constraints = constraints

    out.append(emit_status(db, project.id, "Прописываю промпты", "prompts"))
    if orch:
        project.orchestrator_prompt = orch
    if vision:
        project.vision_prompt = vision
    if style:
        project.image_style_prompt = style

    project.onboarding_status = "done"
    db.add(project)

    summary = (
        "Настройка завершена. Записал:\n"
        f"• Тема: {project.theme or '—'}\n"
        f"• Идеи: {project.ideas or '—'}\n"
        f"• Ограничения: {project.constraints or '—'}\n\n"
        "Их можно править в Настройках. Можно переходить к креативу."
    )
    assistant = Message(
        project_id=project.id,
        role="assistant",
        content=summary,
        attachments=[],
        meta={"onboarding": True, "onboarding_done": True},
    )
    db.add(assistant)
    db.add(MetricEvent(project_id=project.id, name="onboarding.done", value=1))
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant)
    out.append(assistant)
    return user_msg, out
