"""Orchestrator: project context + memory + vision + creative + optional images."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import AppSettings, Creative, Message, MetricEvent, Project
from app.services import memory as memory_svc
from app.services.openrouter import (
    OpenRouterError,
    build_vision_user_content,
    chat_completions,
    generate_image,
)


def get_app_settings(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        raise RuntimeError("App settings missing")
    return row


def _parse_json_payload(text: str) -> dict[str, Any]:
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
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {
        "title": "Черновик объявления",
        "description": text[:4000],
        "image_prompt": "Product photo for Avito listing, clean background, high quality",
        "analysis": "",
        "need_images": True,
    }


def _save_image_bytes(data: bytes, suffix: str = ".png") -> str:
    folder = Path(settings.data_dir) / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{suffix}"
    path = folder / name
    path.write_bytes(data)
    return f"/uploads/{name}"


def _normalize_incoming_images(images: list[str]) -> list[str]:
    """Keep data URLs; rewrite relative uploads to absolute file data URLs if small enough."""
    out: list[str] = []
    for img in images:
        if img.startswith("data:") or img.startswith("http://") or img.startswith("https://"):
            out.append(img)
            continue
        if img.startswith("/uploads/"):
            path = Path(settings.data_dir) / "uploads" / Path(img).name
            if path.is_file() and path.stat().st_size < 4_000_000:
                import base64

                b64 = base64.b64encode(path.read_bytes()).decode("ascii")
                mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                out.append(f"data:{mime};base64,{b64}")
    return out


async def run_orchestrator(
    db: Session,
    project: Project,
    *,
    user_text: str,
    images: list[str] | None = None,
    generate_images: bool = True,
    revise_of_creative_id: int | None = None,
) -> tuple[Message, Message, Creative]:
    cfg = get_app_settings(db)
    api_key = cfg.openrouter_api_key or settings.openrouter_api_key
    images = images or []

    user_msg = Message(
        project_id=project.id,
        role="user",
        content=user_text,
        attachments=[{"type": "image", "url": u[:120] + ("…" if len(u) > 120 else "")} for u in images],
        meta={"revise_of": revise_of_creative_id} if revise_of_creative_id else {},
    )
    db.add(user_msg)
    db.add(MetricEvent(project_id=project.id, name="chat.user_message", value=1))
    db.commit()
    db.refresh(user_msg)

    if revise_of_creative_id and user_text.strip():
        memory_svc.remember_revision(db, project.id, user_text)

    mem_block = memory_svc.memories_as_prompt(db, project.id)
    project_block = (
        f"Проект: {project.name}\n"
        f"Тема: {project.theme or '—'}\n"
        f"Идеи: {project.ideas or '—'}\n"
        f"Ограничения: {project.constraints or '—'}"
    )

    history_rows = list(
        db.scalars(
            select(Message)
            .where(Message.project_id == project.id)
            .order_by(Message.id.desc())
            .limit(12)
        )
    )
    history_rows = list(reversed(history_rows))
    history_msgs: list[dict[str, Any]] = []
    for m in history_rows:
        if m.id == user_msg.id:
            continue
        history_msgs.append(
            {
                "role": m.role if m.role in {"user", "assistant"} else "user",
                "content": m.content[:2000],
            }
        )
    history_msgs = history_msgs[-8:]

    vision_notes = ""
    vision_images = _normalize_incoming_images(images)
    vision_model = (project.vision_model or cfg.vision_model or settings.vision_model).strip()
    orch_model_default = (
        project.orchestrator_model or cfg.orchestrator_model or settings.orchestrator_model
    ).strip()
    image_model = (project.image_model or cfg.image_model or settings.image_model).strip()
    vision_system = (
        project.vision_prompt
        or "Опиши товар на фото для объявления Авито: категория, состояние, "
        "цвет, ключевые признаки, дефекты. Кратко, по пунктам, на русском."
    )
    if vision_images:
        try:
            vision_payload = await chat_completions(
                api_key,
                model=vision_model,
                messages=[
                    {"role": "system", "content": vision_system},
                    {
                        "role": "user",
                        "content": build_vision_user_content(
                            "Проанализируй фото товара для объявления.",
                            vision_images,
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=800,
            )
            vision_notes = (
                (vision_payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            )
            db.add(MetricEvent(project_id=project.id, name="vision.ok", value=1))
        except OpenRouterError as exc:
            vision_notes = f"(vision error: {exc})"
            db.add(MetricEvent(project_id=project.id, name="vision.error", value=1, payload={"error": str(exc)}))

    prev_creative = None
    if revise_of_creative_id:
        prev_creative = db.get(Creative, revise_of_creative_id)

    instruction = (
        project.orchestrator_prompt
        or cfg.orchestrator_instruction
        or settings.default_orchestrator_instruction
    )
    system = (
        f"{instruction}\n\n{project_block}\n\n{mem_block}\n\n"
        f"Анализ фото:\n{vision_notes or 'фото не переданы'}"
    )
    if prev_creative:
        system += (
            f"\n\nПредыдущий черновик (нужно учесть правки пользователя):\n"
            f"title={prev_creative.title}\ndescription={prev_creative.description}\n"
            f"image_prompt={prev_creative.image_prompt}"
        )

    user_content: Any
    if vision_images:
        user_content = build_vision_user_content(
            user_text or "Сформируй креатив объявления по фото и настройкам проекта.",
            vision_images,
        )
        orch_model = vision_model or orch_model_default
    else:
        user_content = user_text or "Сформируй креатив объявления по настройкам проекта."
        orch_model = orch_model_default

    messages = [{"role": "system", "content": system}, *history_msgs, {"role": "user", "content": user_content}]
    raw = await chat_completions(api_key, model=orch_model, messages=messages)
    assistant_text = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = _parse_json_payload(assistant_text)

    image_paths: list[str] = []
    need_images = bool(parsed.get("need_images", True)) and generate_images
    image_prompt = str(parsed.get("image_prompt") or "").strip()
    style = (project.image_style_prompt or "").strip()
    if style and image_prompt:
        image_prompt = f"{image_prompt}\n\nStyle: {style}"
    if need_images and image_prompt:
        try:
            blobs = await generate_image(
                api_key,
                model=image_model,
                prompt=image_prompt,
                n=1,
            )
            for blob in blobs:
                image_paths.append(_save_image_bytes(blob))
            db.add(MetricEvent(project_id=project.id, name="image.ok", value=float(len(image_paths))))
        except OpenRouterError as exc:
            db.add(
                MetricEvent(
                    project_id=project.id,
                    name="image.error",
                    value=1,
                    payload={"error": str(exc)[:500]},
                )
            )
            parsed["analysis"] = (str(parsed.get("analysis") or "") + f"\n[image error] {exc}").strip()

    creative = Creative(
        project_id=project.id,
        title=str(parsed.get("title") or "")[:300],
        description=str(parsed.get("description") or ""),
        image_prompt=image_prompt,
        analysis=str(parsed.get("analysis") or vision_notes),
        images=[{"url": p} for p in image_paths],
        status="draft",
    )
    db.add(creative)

    pretty = (
        f"**{creative.title}**\n\n{creative.description}\n\n"
        f"_Анализ:_ {creative.analysis}\n"
        f"_Промпт фото:_ {creative.image_prompt}"
    )
    assistant_msg = Message(
        project_id=project.id,
        role="assistant",
        content=pretty,
        attachments=creative.images,
        meta={"creative_id": None},
    )
    db.add(assistant_msg)
    db.add(MetricEvent(project_id=project.id, name="creative.created", value=1))
    db.commit()
    db.refresh(creative)
    db.refresh(assistant_msg)
    from sqlalchemy.orm.attributes import flag_modified

    assistant_msg.meta = {**(assistant_msg.meta or {}), "creative_id": creative.id}
    flag_modified(assistant_msg, "meta")
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return user_msg, assistant_msg, creative
