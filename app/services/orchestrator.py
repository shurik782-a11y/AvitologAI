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
from app.services.media_store import persist_attachment_list, persist_data_url
from app.services.status_steps import clear_status_messages, emit_status, is_status_message
from app.services.test_run import is_make_post_request, is_test_run, test_run_system_note


def get_app_settings(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        raise RuntimeError("App settings missing")
    return row


def _coerce_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str):
                    parts.append(t)
                elif part.get("type") == "text" and isinstance(part.get("content"), str):
                    parts.append(part["content"])
        return "\n".join(parts)
    return str(content)


def _extract_balanced_object(text: str) -> str | None:
    """Return first top-level {...} with string-aware brace matching."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _loads_json_object(raw: str) -> dict[str, Any] | None:
    s = (raw or "").strip()
    if not s:
        return None
    candidates = [s]
    # trailing commas before } or ]
    fixed = re.sub(r",\s*([}\]])", r"\1", s)
    if fixed != s:
        candidates.append(fixed)
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _parse_json_payload(text: Any) -> dict[str, Any]:
    text = _coerce_message_content(text)
    text = text.lstrip("\ufeff").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    data = _loads_json_object(text)
    if data is not None:
        return data

    extracted = _extract_balanced_object(text)
    if extracted:
        data = _loads_json_object(extracted)
        if data is not None:
            return data

    # Do NOT dump English chain-of-thought into description
    return {
        "title": "",
        "description": "",
        "sections": {},
        "image_prompt": "",
        "image_briefs": [],
        "analysis": "",
        "need_images": True,
        "parse_error": True,
    }


def _looks_like_leak(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    markers = (
        "i need to",
        "json object",
        "project details",
        "search_query",
        "conversion_offer",
        "image_briefs",
        "need_images",
        "let me ",
        "compose the",
        "produce the",
        "strictly one json",
    )
    if any(m in low for m in markers):
        return True
    latin = sum(1 for c in t if ("a" <= c.lower() <= "z"))
    cyr = sum(1 for c in t if "а" <= c.lower() <= "я" or c.lower() == "ё")
    if latin > 80 and latin > cyr * 2:
        return True
    return False


def _ru_field(text: str, *, fallback: str = "") -> str:
    t = (text or "").strip()
    if not t or _looks_like_leak(t):
        return fallback
    return t



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


def _strip_title_spam(text: str) -> str:
    """Remove CTA/delivery spam that must not appear in Avito titles."""
    t = (text or "").strip()
    if not t:
        return ""
    banned = (
        r"купить\s+онлайн(?:\s+с\s+(?:быстрой\s+)?доставкой)?",
        r"с\s+быстрой\s+доставкой",
        r"онлайн\s+с\s+доставкой",
        r"купить\s+онлайн",
        r"с\s+доставкой",
        r"быстрая\s+доставка",
        r"закажите\s+сейчас",
        r"недорого",
    )
    for pat in banned:
        t = re.sub(pat, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;-–—")
    return t


def _strip_md_markup(text: str) -> str:
    """Remove markdown bold/italic from user-facing ad copy (not system UI)."""
    t = text or ""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", t)
    return t


def _capitalize_orthography(text: str) -> str:
    """Capitalize start of text, paragraphs, and sentences after .!?…"""
    t = text or ""
    if not t:
        return t

    def _cap_first_alpha(s: str) -> str:
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + ch.upper() + s[i + 1 :]
        return s

    parts = t.split("\n\n")
    out: list[str] = []
    for para in parts:
        p = _cap_first_alpha(para)

        def _repl(m: re.Match[str]) -> str:
            return m.group(1) + m.group(2).upper()

        p = re.sub(r"([.!?…]\s+)([a-zа-яё])", _repl, p, flags=re.IGNORECASE)
        out.append(p)
    return "\n\n".join(out)


def _polish_user_text(text: str, *, fallback: str = "") -> str:
    t = _strip_md_markup(_ru_field(text, fallback=fallback))
    return _capitalize_orthography(t) if t else fallback


def _polish_title(parsed: dict[str, Any], project: Project) -> str:
    title = _strip_title_spam(_ru_field(str(parsed.get("title") or "")))
    sq = _strip_title_spam(
        _ru_field(str(parsed.get("search_query") or getattr(project, "search_query", "") or ""))
    )
    off = _strip_title_spam(
        _ru_field(
            str(parsed.get("conversion_offer") or getattr(project, "conversion_offer", "") or "")
        )
    )
    # Drop CTA-ish conversion offers entirely
    off_l = off.lower()
    if any(w in off_l for w in ("купить", "онлайн", "доставк", "заказ")):
        off = ""
    bad = (
        len(title) > 50
        or title.count(" ") > 7
        or "купить" in title.lower()
        or "онлайн" in title.lower()
        or "доставк" in title.lower()
        or (len(title) > 12 and title == title.lower())
    )
    if (not title or bad) and (sq or off):
        title = f"{sq} {off}".strip()
    title = _strip_title_spam(_strip_md_markup(title))
    if not title:
        title = sq or "Объявление"
    title = _capitalize_orthography(title)
    if len(title) > 50:
        title = title[:50].rstrip(" ,;-–—")
    return title


def _clean_sections(sections: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(sections, dict):
        return out
    for k, v in sections.items():
        s = _polish_user_text(str(v or ""))
        if s:
            out[str(k)] = s
    return out


def _normalize_paragraphs(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _polish_description(description: str, sections: dict) -> str:
    joined = _normalize_paragraphs(join_sections(sections))
    if joined:
        return _polish_user_text(joined) or joined
    desc = _normalize_paragraphs(_polish_user_text(description))
    return desc or "Не удалось собрать текст. Напишите правку или «сделай пост» ещё раз."


def _text_only_edit(user_text: str, revise: bool) -> bool:
    if not revise:
        return False
    t = (user_text or "").lower()
    if any(w in t for w in ("фото", "картин", "изображен", "visual", "image")):
        return False
    return True


_WORD_PHOTO_COUNT = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
}


def _photo_budget(project: Project, parsed: dict[str, Any], user_text: str) -> int:
    """Exact N from project or explicit user request (not inflated by soft LLM brief count)."""
    n = int(getattr(project, "photo_count", None) or settings.photo_count_default)
    t = (user_text or "").lower()
    m = re.search(r"(\d+)\s*(?:фото|кадр(?:а|ов)?|изображен\w*|pictures?|photos?)", t)
    if m:
        n = int(m.group(1))
    else:
        for word, num in _WORD_PHOTO_COUNT.items():
            if re.search(rf"\b{word}\s+(?:фото|кадр|изображен)", t):
                n = num
                break
    return max(1, min(n, settings.photo_count_max))


_BRIEF_ROLES = ("hero", "pain", "proof")
_ROLE_ANGLES = {
    "hero": "primary hero angle, full product clearly visible",
    "pain": "alternate angle addressing buyer doubts (detail, fit, or quality)",
    "proof": "proof shot: material, construction, or use-detail close-up",
}


def _pad_image_briefs(
    briefs: list[dict[str, Any]],
    budget: int,
    *,
    scene_brief: str,
    has_ref: bool,
) -> list[dict[str, Any]]:
    """Ensure exactly `budget` briefs with non-empty prompts."""
    base = ""
    for b in briefs:
        p = str(b.get("prompt") or "").strip()
        if p:
            base = p
            break
    if not base:
        base = (scene_brief or "").strip() or (
            "Product listing photo matching source facts; clear commercial Avito shot"
        )
    out: list[dict[str, Any]] = []
    for b in briefs[:budget]:
        role = str(b.get("role") or "hero").strip() or "hero"
        prompt = str(b.get("prompt") or "").strip() or base
        edit_from = "ref" if has_ref else str(b.get("edit_from") or "none").lower()
        if has_ref:
            edit_from = "ref"
        out.append({"role": role, "prompt": prompt, "edit_from": edit_from})
    while len(out) < budget:
        i = len(out)
        role = _BRIEF_ROLES[i % len(_BRIEF_ROLES)]
        angle = _ROLE_ANGLES[role]
        out.append(
            {
                "role": role,
                "prompt": (
                    f"{base}. Shot {i + 1}/{budget}: {angle}. "
                    "SAME product identity (color, material, silhouette, matching pair). "
                    "Do not invent a different item."
                ),
                "edit_from": "ref" if has_ref else "none",
            }
        )
    return out


def _bytes_to_data_url(data: bytes, *, mime: str = "image/png") -> str:
    import base64

    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


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
        attachments=persist_attachment_list(images, max_n=8),
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
        "Ответь СТРОГО одним JSON. Все тексты для объявления — на русском. "
        "Без рассуждений и без английского вне image_prompt. "
        "need_images=false для правок только текста. "
        f"Число image_briefs РОВНО photo_count={project.photo_count or 1} "
        f"(или явное число из запроса; max {settings.photo_count_max}). "
        "Не меньше. Один и тот же товар на всех кадрах."
    )
    if is_test_run(project):
        system = test_run_system_note() + "\n\n" + system
    if is_make_post_request(user_text):
        system += (
            "\n\nПользователь запросил пост/объявление — сгенерируй полный креатив по слотам проекта "
            "(need_images=true, если не сказано «без фото»)."
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

    async def _orch_call(
        msgs: list[dict[str, Any]],
        *,
        temperature: float,
        use_json_format: bool,
    ) -> tuple[dict[str, Any], str]:
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "model": orch_model,
            "messages": msgs,
            "max_tokens": 3200,
            "temperature": temperature,
        }
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}
        raw_resp = await chat_completions(**kwargs)
        choice = (raw_resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = _coerce_message_content(msg.get("content"))
        return raw_resp, text

    json_format_ok = True
    try:
        raw, assistant_text = await _orch_call(messages, temperature=0.15, use_json_format=True)
    except OpenRouterError as exc:
        err = str(exc).lower()
        unsupported = any(
            x in err
            for x in (
                "response_format",
                "json_object",
                "not support",
                "unsupported",
                "invalid schema",
            )
        )
        if unsupported:
            json_format_ok = False
            prompt_only = list(messages)
            prompt_only[0] = {
                "role": "system",
                "content": system
                + "\n\nКРИТИЧНО: верни ТОЛЬКО один валидный JSON-объект. Без markdown и без текста вокруг.",
            }
            raw, assistant_text = await _orch_call(
                prompt_only, temperature=0.15, use_json_format=False
            )
        else:
            raise

    parsed = _parse_json_payload(assistant_text)

    if parsed.get("parse_error"):
        repair_msgs = [
            {
                "role": "system",
                "content": (
                    "Ты исправляешь ответ в валидный JSON для объявления Авито. "
                    "Верни СТРОГО один JSON-объект со полями: "
                    "ad_idea, title, search_query, conversion_offer, description, sections, "
                    "pains, analysis, need_images, image_prompt, image_briefs, propose_new_idea, price. "
                    "Человеческие тексты — на русском. Без рассуждений и markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Исправь ответ модели в валидный JSON по схеме. "
                    "Вот сырой ответ (обрезан):\n\n"
                    + (assistant_text or "")[:2500]
                ),
            },
        ]
        try:
            _, repaired_text = await _orch_call(
                repair_msgs, temperature=0.1, use_json_format=json_format_ok
            )
            repaired = _parse_json_payload(repaired_text)
            if not repaired.get("parse_error"):
                parsed = repaired
                assistant_text = repaired_text
            else:
                db.add(
                    MetricEvent(
                        project_id=project.id,
                        name="orch.parse_error",
                        value=1,
                        payload={"preview": (assistant_text or "")[:400], "repaired": False},
                    )
                )
        except OpenRouterError as exc:
            db.add(
                MetricEvent(
                    project_id=project.id,
                    name="orch.parse_error",
                    value=1,
                    payload={
                        "preview": (assistant_text or "")[:400],
                        "repair_error": str(exc)[:200],
                    },
                )
            )

    sections = _clean_sections(parsed.get("sections") if isinstance(parsed.get("sections"), dict) else {})
    description = _polish_description(
        str(parsed.get("description") or "").strip(),
        sections,
    )
    title = _polish_title(parsed, project)
    analysis = _polish_user_text(str(parsed.get("analysis") or ""), fallback="")
    if not analysis:
        analysis = _polish_user_text(vision_notes, fallback="")
    ad_idea = _polish_user_text(str(parsed.get("ad_idea") or project.ad_idea or ""))

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
    if need_images:
        briefs = _pad_image_briefs(
            briefs,
            budget,
            scene_brief=scene_brief,
            has_ref=bool(vision_images),
        )
    else:
        briefs = []

    style_rules = compose_image_style(
        project_style=project.image_style_prompt or "",
        allow_people=bool(project.allow_people),
        allow_text_overlays=bool(project.allow_text_overlays),
    )
    ref0 = vision_images[0] if vision_images else ""
    hero_source: str | None = None

    if need_images and briefs:
        status_msgs.append(emit_status(db, project.id, "Планирую фото", "plan_images"))
        total = len(briefs)
        for i, brief in enumerate(briefs):
            prompt_txt = str(brief.get("prompt") or scene_brief or "").strip()
            if not prompt_txt:
                prompt_txt = (
                    scene_brief
                    or "Product listing photo matching source facts; clear commercial Avito shot"
                )
            role = str(brief.get("role") or "photo")
            gen_prompt = build_image_generation_prompt(
                scene_brief=prompt_txt,
                style_rules=style_rules,
                vision_facts=vision_notes,
                shot_index=i + 1,
                shot_total=total,
            )
            # Prefer ref for first shot; later shots edit from hero (same product) then ref
            source = None
            if i == 0 and ref0:
                source = ref0
            elif hero_source:
                source = hero_source
            elif ref0:
                source = ref0
            use_edit = bool(source)
            status_msgs.append(
                emit_status(
                    db,
                    project.id,
                    "Редактирую референс" if use_edit else f"Генерирую фото ({role})",
                    "image",
                )
            )
            try:
                if use_edit and source:
                    blobs = await edit_image(
                        api_key, model=image_model, prompt=gen_prompt, source_image=source
                    )
                else:
                    blobs = await generate_image(api_key, model=image_model, prompt=gen_prompt, n=1)
                for blob in blobs:
                    image_paths.append(_save_image_bytes(blob))
                    if i == 0 and not hero_source:
                        hero_source = _bytes_to_data_url(blob)
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

    offer_clean = _strip_title_spam(
        _ru_field(str(parsed.get("conversion_offer") or project.conversion_offer or ""))
    )
    if any(w in offer_clean.lower() for w in ("купить", "онлайн", "доставк", "заказ")):
        offer_clean = ""

    meta = {
        "ad_idea": ad_idea,
        "search_query": _strip_title_spam(
            _ru_field(str(parsed.get("search_query") or project.search_query or ""))
        ),
        "conversion_offer": offer_clean,
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
        creative.analysis = analysis
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
            analysis=analysis,
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

    # User-facing ad copy: plain text (no **); system statuses use ** separately
    pretty_parts = [title, "", description]
    if analysis:
        pretty_parts.extend(["", analysis])
    pretty = _polish_user_text("\n".join(pretty_parts))
    if meta.get("propose_new_idea"):
        pretty += "\n\nМожно сделать вариант с другой идеей — напишите, если нужно."
    parse_failed = bool(parsed.get("parse_error"))
    if parse_failed:
        pretty = (
            "Не удалось собрать текст объявления. "
            "Напишите правку или «сделай пост» ещё раз."
        )
        creative.meta = {**(creative.meta or {}), "failed": True, "parse_error": True}
        flag_modified(creative, "meta")
        db.add(creative)
        db.commit()
        db.refresh(creative)

    assistant_msg = Message(
        project_id=project.id,
        role="assistant",
        content=pretty,
        attachments=(
            []
            if parse_failed
            else (creative.images if isinstance(creative.images, list) else [])
        ),
        meta={
            "need_images": need_images if not parse_failed else False,
            "delivery": True,
            "parse_error": parse_failed,
            "failed": parse_failed,
        },
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(creative)
    db.refresh(assistant_msg)
    if not parse_failed:
        assistant_msg.meta = {**(assistant_msg.meta or {}), "creative_id": creative.id}
        flag_modified(assistant_msg, "meta")
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
    clear_status_messages(db, project.id)
    return user_msg, [assistant_msg], None if parse_failed else creative
