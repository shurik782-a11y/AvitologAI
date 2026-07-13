"""Onboarding: multi-turn setup on free OpenRouter model → project slots."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db import AppSettings, Message, MetricEvent, Project
from app.services.openrouter import OpenRouterError, chat_completions
from app.services.prompts import ONBOARDING_SEED, ONBOARDING_SYSTEM
from app.services.status_steps import emit_status

__all__ = ["ONBOARDING_SEED", "run_onboarding"]


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
        "need_user_input": True,
        "questions": ["Уточните нишу, идею объявления и сколько фото нужно (1–5)."],
        "assistant_message": "Нужны уточнения по настройке проекта.",
        "done": False,
    }


def _apply_slots(project: Project, data: dict[str, Any]) -> None:
    str_fields = (
        "theme",
        "ideas",
        "constraints",
        "listing_type",
        "advantages",
        "buyer_pains",
        "why_here",
        "ad_idea",
        "search_query",
        "conversion_offer",
        "company_info",
        "orchestrator_prompt",
        "vision_prompt",
        "image_style_prompt",
    )
    for key in str_fields:
        val = data.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s:
            setattr(project, key, s)

    if data.get("photo_count") is not None:
        try:
            n = int(data.get("photo_count"))
            project.photo_count = max(1, min(n, settings.photo_count_max))
        except (TypeError, ValueError):
            pass
    if "allow_people" in data and data["allow_people"] is not None:
        project.allow_people = bool(data["allow_people"])
    if "allow_text_overlays" in data and data["allow_text_overlays"] is not None:
        project.allow_text_overlays = bool(data["allow_text_overlays"])


def _slots_snapshot(project: Project) -> str:
    return (
        f"listing_type={project.listing_type or '—'}\n"
        f"ad_idea={project.ad_idea or '—'}\n"
        f"search_query={project.search_query or '—'}\n"
        f"conversion_offer={project.conversion_offer or '—'}\n"
        f"advantages={project.advantages or '—'}\n"
        f"buyer_pains={project.buyer_pains or '—'}\n"
        f"why_here={project.why_here or '—'}\n"
        f"photo_count={project.photo_count or 1}\n"
        f"allow_people={bool(project.allow_people)}\n"
        f"theme={project.theme or '—'}\n"
        f"constraints={project.constraints or '—'}\n"
        f"competitor_insights={'да' if project.competitor_insights else 'нет'}\n"
    )


def _is_complete(project: Project, data: dict[str, Any], round_idx: int) -> bool:
    if data.get("done") is True and (project.ad_idea or project.theme):
        return True
    if round_idx >= settings.onboarding_max_rounds:
        return bool(project.ad_idea or project.theme or project.ideas)
    has_idea = bool(project.ad_idea or project.ideas)
    has_type = bool(project.listing_type or project.theme)
    has_photos = int(project.photo_count or 0) >= 1
    if data.get("need_user_input") and round_idx < settings.onboarding_max_rounds:
        return False
    return has_idea and has_type and has_photos


async def run_onboarding(
    db: Session,
    project: Project,
    user_text: str,
    images: list[str] | None = None,
) -> tuple[Message, list[Message], bool]:
    """Returns user message, assistant messages, onboarding_done flag."""
    cfg = db.get(AppSettings, 1)
    assert cfg is not None
    api_key = cfg.openrouter_api_key or settings.openrouter_api_key
    model = (settings.onboarding_model or "openrouter/free").strip()
    images = images or []

    extra = dict(project.extra or {})
    round_idx = int(extra.get("onboarding_round") or 0) + 1
    extra["onboarding_round"] = round_idx
    if images:
        refs = list(extra.get("reference_images") or [])
        for u in images[:8]:
            refs.append(u[:500] if isinstance(u, str) else str(u)[:500])
        extra["reference_images"] = refs[-12:]
        extra["reference_received"] = True
    project.extra = extra
    flag_modified(project, "extra")

    user_msg = Message(
        project_id=project.id,
        role="user",
        content=user_text,
        attachments=[{"type": "image", "url": (u[:120] + "…") if len(u) > 120 else u} for u in images],
        meta={"onboarding": True, "round": round_idx},
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    out: list[Message] = []
    out.append(emit_status(db, project.id, "Выделяю основные критерии", "criteria"))

    try:
        raw = await chat_completions(
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": ONBOARDING_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Раунд {round_idx}/{settings.onboarding_max_rounds}.\n"
                        f"Уже заполнено:\n{_slots_snapshot(project)}\n"
                        f"Референс-фото: {'получены' if extra.get('reference_received') else 'ещё нет'}.\n\n"
                        f"Сообщение пользователя:\n{user_text or '(пусто)'}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1800,
        )
        content = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        data = _parse_json(content)
    except OpenRouterError as exc:
        data = {
            "need_user_input": True,
            "questions": ["Повторите описание ниши и идеи объявления."],
            "assistant_message": f"Не удалось разобрать ответ модели ({exc}). Напишите ещё раз кратко.",
            "done": False,
            "theme": user_text[:500] if user_text else "",
        }
        db.add(
            MetricEvent(
                project_id=project.id,
                name="onboarding.error",
                value=1,
                payload={"error": str(exc)[:400]},
            )
        )

    _apply_slots(project, data)

    if data.get("ad_idea") or project.ad_idea:
        out.append(
            emit_status(
                db,
                project.id,
                f"Фиксирую идею: {(project.ad_idea or '')[:200]}",
                "idea",
            )
        )
    if data.get("buyer_pains") or data.get("constraints"):
        out.append(
            emit_status(
                db,
                project.id,
                f"Уточняю боли/ограничения: {(project.buyer_pains or project.constraints or '')[:200]}",
                "constraints",
            )
        )
    if not extra.get("reference_received"):
        out.append(emit_status(db, project.id, "Прошу референс-фото (скрепка)", "refs"))
    if project.competitor_insights:
        out.append(emit_status(db, project.id, "Учитываю insights конкурентов", "competitors"))

    out.append(emit_status(db, project.id, "Прописываю промпты и слоты", "prompts"))

    done = _is_complete(project, data, round_idx)
    # Soft ask for refs but don't block forever
    if done and not extra.get("reference_received") and round_idx < settings.onboarding_max_rounds:
        if data.get("need_user_input") or not user_text.lower().startswith(("без фото", "без референс", "пропусти")):
            # Allow finish if user said skip; else one more nudge only when model asks
            pass

    assistant_text = str(data.get("assistant_message") or "").strip()
    questions = data.get("questions") if isinstance(data.get("questions"), list) else []

    if done:
        project.onboarding_status = "done"
        summary = (
            "Настройка завершена. Записал:\n"
            f"• Тип: {project.listing_type or '—'}\n"
            f"• Идея объявления: {project.ad_idea or '—'}\n"
            f"• Заголовок: {(project.search_query or '').strip()} {(project.conversion_offer or '').strip()}\n"
            f"• Боли: {project.buyer_pains or '—'}\n"
            f"• Фото: {project.photo_count or 1} "
            f"(люди: {'да' if project.allow_people else 'нет'}, "
            f"текст на фото: {'да' if project.allow_text_overlays else 'нет'})\n"
            f"• Референсы: {'есть' if extra.get('reference_received') else 'нет'}\n"
            f"• Конкуренты: {'insights есть' if project.competitor_insights else 'можно импортировать CSV/XLSX в Настройках'}\n\n"
            "Правки — в Настройках или напишите оркестратору. Можно переходить к креативу."
        )
        if assistant_text:
            summary = assistant_text + "\n\n" + summary
        assistant = Message(
            project_id=project.id,
            role="assistant",
            content=summary,
            attachments=[],
            meta={"onboarding": True, "onboarding_done": True},
        )
        db.add(assistant)
        db.add(MetricEvent(project_id=project.id, name="onboarding.done", value=1))
        db.add(project)
        db.commit()
        db.refresh(assistant)
        out.append(assistant)
        return user_msg, out, True

    # Continue onboarding
    project.onboarding_status = "awaiting_brief"
    q_lines = "\n".join(f"• {q}" for q in questions if str(q).strip())
    body = assistant_text or "Нужны уточнения для настройки проекта."
    if q_lines:
        body += "\n\n" + q_lines
    if not extra.get("reference_received"):
        body += "\n\nЕсли есть — пришлите референс-фото товара/объекта (скрепка)."
    body += f"\n\n_Раунд {round_idx}/{settings.onboarding_max_rounds}_"
    assistant = Message(
        project_id=project.id,
        role="assistant",
        content=body,
        attachments=[],
        meta={"onboarding": True, "onboarding_done": False, "round": round_idx},
    )
    db.add(assistant)
    db.add(project)
    db.add(MetricEvent(project_id=project.id, name="onboarding.round", value=float(round_idx)))
    db.commit()
    db.refresh(assistant)
    out.append(assistant)
    return user_msg, out, False
