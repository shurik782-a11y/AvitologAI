"""Orchestrator: slots + methodology + vision cache + N image briefs + revise same creative."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db import AppSettings, Creative, Message, MetricEvent, Project
from app.services import memory as memory_svc
from app.services.openrouter import (
    OpenRouterError,
    build_vision_user_content,
    chat_completions,
    edit_image,
    generate_image,
)
from app.services.prompts import (
    build_image_generation_prompt,
    compose_image_style,
    compose_orchestrator_system,
    compose_vision_system,
    join_sections,
    project_slots_block,
)
from app.services.status_steps import emit_status, is_status_message


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
        "image_briefs": [],
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


def _wants_new_listing(user_text: str) -> bool:
    t = (user_text or "").lower()
    markers = (
        "новое объявление",
        "другая идея",
        "новую идею",
        "с нуля",
        "новый креатив",
        "переделай объявление полностью",
    )
    return any(m in t for m in markers)


def _text_only_edit(user_text: str, revise: bool) -> bool:
    if not revise:
        return False
    t = (user_text or "").lower()
    if any(w in t for w in ("фото", "картин", "изображен", "visual", "image")):
        return False
    return True


def _photo_budget(project: Project, parsed: dict[str, Any], user_text: str) -> int:
    n = int(getattr(project, "photo_count", None) or settings.photo_count_default)
    # Explicit number in request
    m = re.search(r"(\d+)\s*фото", (user_text or "").lower())
    if m:
        n = int(m.group(1))
    briefs = parsed.get("image_briefs")
    if isinstance(briefs, list) and briefs:
        n = max(n, min(len(briefs), settings.photo_count_max))
    return max(1, min(n, settings.photo_count_max))


def _collect_refs(project: Project, incoming: list[str]) -> list[str]:
    refs = list(incoming)
    extra = project.extra or {}
    for u in extra.get("reference_images") or []:
        if isinstance(u, str) and u not in refs:
            refs.append(u)
    return _normalize_incoming_images(refs[:6])


async def run_orchestrator(
    db: Session,
    project: Project,
    *,
    user_text: str,
    images: list[str] | None = None,
    revise_of_creative_id: int | None = None,
) -> tuple[Message, list[Message], Creative]:
    cfg = get_app_settings(db)
    api_key = cfg.openrouter_api_key or settings.openrouter_api_key
    images = images or []
    status_msgs: list[Message] = []

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

    status_msgs.append(emit_status(db, project.id, "Обрабатываю запрос", "process"))

    prev_creative = db.get(Creative, revise_of_creative_id) if revise_of_creative_id else None
    force_new = _wants_new_listing(user_text)
    if force_new:
        prev_creative = None

    if prev_creative and user_text.strip():
        brief = user_text.strip().replace("\n", " ")
        if len(brief) > 180:
            brief = brief[:177] + "…"
        classified = await memory_svc.classify_and_remember_mistake(
            db,
            project.id,
            user_text,
            prev_title=prev_creative.title or "",
            api_key=api_key,
            model=(
                project.orchestrator_model or cfg.orchestrator_model or settings.orchestrator_model
            ).strip(),
        )
        scope_label = "общая" if classified.get("scope") == "global" else "только этот проект"
        status_msgs.append(
            emit_status(
                db,
                project.id,
                f"Фиксирую ошибку ({scope_label}): {brief}",
                "mistake",
            )
        )
        status_msgs.append(emit_status(db, project.id, "Выполняю правки", "revise"))

    mem_block = memory_svc.memories_as_prompt(db, project.id)
    project_block = project_slots_block(project)

    history_rows = list(
        db.scalars(
            select(Message)
            .where(Message.project_id == project.id)
            .order_by(Message.id.desc())
            .limit(16)
        )
    )
    history_rows = list(reversed(history_rows))
    history_msgs: list[dict[str, Any]] = []
    for m in history_rows:
        if m.id == user_msg.id:
            continue
        if is_status_message(m):
            continue
        history_msgs.append(
            {
                "role": m.role if m.role in {"user", "assistant"} else "user",
                "content": m.content[:1600],
            }
        )
    history_msgs = history_msgs[-6:]

    text_only = _text_only_edit(user_text, bool(prev_creative))
    vision_notes = (project.visual_style_notes or "").strip()
    vision_images = _collect_refs(project, images) if not text_only else []
    run_vision = bool(vision_images) and (
        bool(images) or not (project.visual_style_notes or "").strip()
    )

    vision_model = (project.vision_model or cfg.vision_model or settings.vision_model).strip()
    orch_model = (
        project.orchestrator_model or cfg.orchestrator_model or settings.orchestrator_model
    ).strip()
    image_model = (project.image_model or cfg.image_model or settings.image_model).strip()
    vision_system = compose_vision_system(project_prompt=project.vision_prompt or "")

    if run_vision:
        try:
            vision_payload = await chat_completions(
                api_key,
                model=vision_model,
                messages=[
                    {"role": "system", "content": vision_system},
                    {
                        "role": "user",
                        "content": build_vision_user_content(
                            "Проанализируй фото: факты товара/объекта и визуальный стиль.",
                            vision_images[:4],
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=800,
            )
            vision_notes = (
                (vision_payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            )
            if vision_notes and not vision_notes.startswith("(vision error"):
                # Cache style on project (cost guard)
                style_line = vision_notes[-800:]
                project.visual_style_notes = style_line
                db.add(project)
            db.add(MetricEvent(project_id=project.id, name="vision.ok", value=1))
        except OpenRouterError as exc:
            vision_notes = f"(vision error: {exc})"
            db.add(
                MetricEvent(
                    project_id=project.id,
                    name="vision.error",
                    value=1,
                    payload={"error": str(exc)},
                )
            )

    status_msgs.append(emit_status(db, project.id, "Формирую идею", "idea"))
    if project.competitor_insights:
        status_msgs.append(emit_status(db, project.id, "Учитываю конкурентов", "competitors"))
    status_msgs.append(emit_status(db, project.id, "Даю задание на генерацию", "assign"))
    status_msgs.append(emit_status(db, project.id, "Собираю текст по структуре", "text"))

    instruction = compose_orchestrator_system(
        project_prompt=project.orchestrator_prompt or "",
        global_instruction=cfg.orchestrator_instruction or "",
    )
    system = (
        f"{instruction}\n\n{project_block}\n\n{mem_block}\n\n"
        f"Анализ фото / стиль:\n{vision_notes or 'фото не переданы / кэш пуст'}\n\n"
        "Один JSON-ответ. need_images=false для правок только текста. "
        f"Число image_briefs ориентируй на photo_count={project.photo_count or 1} (max {settings.photo_count_max})."
    )
    if prev_creative:
        prev_meta = prev_creative.meta or {}
        system += (
            f"\n\nПредыдущий черновик (правь ЕГО, не создавай новый id в ответе):\n"
            f"title={prev_creative.title}\n"
            f"description={prev_creative.description}\n"
            f"ad_idea={prev_meta.get('ad_idea') or project.ad_idea}\n"
            f"image_prompt={prev_creative.image_prompt}\n"
            "Учти правки и память mistake/fix_rule."
        )

    if vision_images and not text_only:
        user_content: Any = build_vision_user_content(
            user_text or "Сформируй креатив объявления по фото и настройкам проекта.",
            vision_images[:3],
        )
    else:
        user_content = user_text or "Сформируй креатив объявления по настройкам проекта."

    messages = [
        {"role": "system", "content": system},
        *history_msgs,
        {"role": "user", "content": user_content},
    ]
    raw = await chat_completions(api_key, model=orch_model, messages=messages, max_tokens=3200)
    assistant_text = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = _parse_json_payload(assistant_text)

    sections = parsed.get("sections") if isinstance(parsed.get("sections"), dict) else {}
    description = str(parsed.get("description") or "").strip() or join_sections(sections)
    title = str(parsed.get("title") or "").strip()
    if not title:
        sq = str(parsed.get("search_query") or project.search_query or "").strip()
        off = str(parsed.get("conversion_offer") or project.conversion_offer or "").strip()
        title = f"{sq} {off}".strip() or "Объявление"

    need_images = bool(parsed.get("need_images", True))
    if text_only:
        need_images = False

    image_paths: list[str] = []
    briefs: list[dict[str, Any]] = []
    if isinstance(parsed.get("image_briefs"), list):
        briefs = [b for b in parsed["image_briefs"] if isinstance(b, dict)]
    scene_brief = str(parsed.get("image_prompt") or "").strip()
    if need_images and not briefs and scene_brief:
        briefs = [{"role": "hero", "prompt": scene_brief, "edit_from": "ref" if vision_images else "none"}]

    budget = _photo_budget(project, parsed, user_text) if need_images else 0
    briefs = briefs[:budget]

    style_rules = compose_image_style(
        project_style=project.image_style_prompt or "",
        allow_people=bool(project.allow_people),
        allow_text_overlays=bool(project.allow_text_overlays),
    )
    ref0 = vision_images[0] if vision_images else ""

    if need_images and briefs:
        status_msgs.append(emit_status(db, project.id, "Планирую фото", "plan_images"))
        for i, brief in enumerate(briefs):
            prompt_txt = str(brief.get("prompt") or scene_brief or "").strip()
            if not prompt_txt:
                continue
            edit_from = str(brief.get("edit_from") or "none").lower()
            role = str(brief.get("role") or "photo")
            gen_prompt = build_image_generation_prompt(
                scene_brief=prompt_txt,
                style_rules=style_rules,
                vision_facts=vision_notes,
            )
            use_edit = edit_from == "ref" and bool(ref0)
            status_msgs.append(
                emit_status(
                    db,
                    project.id,
                    "Редактирую референс" if use_edit else f"Генерирую фото ({role})",
                    "image",
                )
            )
            try:
                if use_edit:
                    blobs = await edit_image(
                        api_key, model=image_model, prompt=gen_prompt, source_image=ref0
                    )
                else:
                    blobs = await generate_image(api_key, model=image_model, prompt=gen_prompt, n=1)
                for blob in blobs:
                    image_paths.append(_save_image_bytes(blob))
                db.add(MetricEvent(project_id=project.id, name="image.ok", value=1, payload={"role": role}))
            except OpenRouterError as exc:
                db.add(
                    MetricEvent(
                        project_id=project.id,
                        name="image.error",
                        value=1,
                        payload={"error": str(exc)[:500], "role": role},
                    )
                )
                parsed["analysis"] = (
                    str(parsed.get("analysis") or "") + f"\n[image error {role}] {exc}"
                ).strip()

    status_msgs.append(emit_status(db, project.id, "Формирую публикацию", "compose"))

    price = ""
    if isinstance(parsed.get("price"), (str, int, float)):
        price = str(parsed.get("price"))

    meta = {
        "ad_idea": str(parsed.get("ad_idea") or project.ad_idea or ""),
        "search_query": str(parsed.get("search_query") or project.search_query or ""),
        "conversion_offer": str(parsed.get("conversion_offer") or project.conversion_offer or ""),
        "sections": sections or {},
        "pains": parsed.get("pains") if isinstance(parsed.get("pains"), list) else [],
        "image_briefs": briefs,
        "propose_new_idea": bool(parsed.get("propose_new_idea")),
    }

    hero_prompt = scene_brief or (str(briefs[0].get("prompt")) if briefs else "")

    if prev_creative and not force_new:
        creative = prev_creative
        creative.title = title[:300]
        creative.description = description
        creative.image_prompt = hero_prompt
        creative.analysis = str(parsed.get("analysis") or vision_notes)
        if image_paths:
            creative.images = [{"url": p} for p in image_paths]
        elif text_only:
            pass  # keep previous images
        creative.price = price or creative.price
        creative.status = "draft"
        creative.meta = {**(creative.meta or {}), **meta}
        flag_modified(creative, "meta")
        flag_modified(creative, "images")
        db.add(creative)
        db.add(MetricEvent(project_id=project.id, name="creative.revised", value=1))
    else:
        creative = Creative(
            project_id=project.id,
            title=title[:300],
            description=description,
            image_prompt=hero_prompt,
            analysis=str(parsed.get("analysis") or vision_notes),
            images=[{"url": p} for p in image_paths],
            status="draft",
            price=price,
            publish_status="draft",
            meta=meta,
        )
        db.add(creative)
        db.add(MetricEvent(project_id=project.id, name="creative.created", value=1))

    db.add(
        MetricEvent(
            project_id=project.id,
            name="creative.cost_signals",
            value=float(len(image_paths)),
            payload={
                "vision": int(run_vision),
                "orch": 1,
                "images": len(image_paths),
                "photo_budget": budget,
            },
        )
    )

    idea_line = meta.get("ad_idea") or ""
    propose = meta.get("propose_new_idea")
    pretty = (
        (f"_Идея:_ {idea_line}\n\n" if idea_line else "")
        + f"**{title}**\n\n{description}\n\n"
        + f"_Анализ:_ {creative.analysis}\n"
        + f"_Фото-бриф:_ {hero_prompt or '—'}"
    )
    if propose:
        pretty += "\n\n_Гипотеза:_ можно сделать новое объявление с другой идеей — напишите, если нужно."

    assistant_msg = Message(
        project_id=project.id,
        role="assistant",
        content=pretty,
        attachments=creative.images if isinstance(creative.images, list) else [],
        meta={"need_images": need_images, "delivery": True},
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(creative)
    db.refresh(assistant_msg)
    assistant_msg.meta = {**(assistant_msg.meta or {}), "creative_id": creative.id}
    flag_modified(assistant_msg, "meta")
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return user_msg, [*status_msgs, assistant_msg], creative
