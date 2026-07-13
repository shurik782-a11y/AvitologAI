"""Test-run mode: emulate Avito publish flow; real onboarding/creatives/memory."""
from __future__ import annotations

import re
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db import Project

TRIGGER = "тестовый прогон"
_TRIGGER_RE = re.compile(r"^\s*тестовый\s+прогон\b[^\S\n]*[:\-–—]?\s*", re.IGNORECASE)


def match_test_run_trigger(text: str) -> tuple[bool, str]:
    """If message starts with «тестовый прогон», return (True, remainder)."""
    raw = text or ""
    m = _TRIGGER_RE.match(raw)
    if not m:
        return False, raw
    return True, raw[m.end() :].strip()


def is_test_run(project: Project) -> bool:
    extra = project.extra or {}
    return bool(extra.get("test_run"))


def enable_test_run(db: Session, project: Project) -> Project:
    extra = dict(project.extra or {})
    extra["test_run"] = True
    project.extra = extra
    flag_modified(project, "extra")
    _ensure_demo_avito(project)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _ensure_demo_avito(project: Project) -> None:
    """Fill minimal Avito feed fields so UI/feed behave as connected (demo only)."""
    extra = dict(project.extra or {})
    touched = False
    if not (project.avito_category or "").strip():
        project.avito_category = "Тестовая категория"
        touched = True
    if not (project.avito_address or "").strip():
        project.avito_address = "Москва (тест)"
        touched = True
    if not (project.avito_contact_phone or "").strip():
        project.avito_contact_phone = "+79990000000"
        touched = True
    if touched:
        extra["test_run_demo_avito"] = True
        project.extra = extra
        flag_modified(project, "extra")


def is_make_post_request(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    markers = (
        "сделай пост",
        "сделай объявление",
        "создай пост",
        "создай объявление",
        "сгенерируй пост",
        "сгенерируй объявление",
        "сделай креатив",
    )
    return any(t == m or t.startswith(m) for m in markers)


def test_run_system_note() -> str:
    return (
        "РЕЖИМ «ТЕСТОВЫЙ ПРОГОН» АКТИВЕН.\n"
        "- Считай, что Авито уже «подключён»; не проси Client ID/Secret/кабинет.\n"
        "- Не советуй реальную настройку Автозагрузки и сторонние сервисы.\n"
        "- Работай как в бою: слоты, текст, фото, правки. Память правок — настоящая.\n"
        "- Публикация будет эмулирована приложением после «Утвердить».\n"
        "- Запрос «сделай пост» / «сделай объявление» = полный креатив по слотам проекта."
    )


def test_run_banner() -> str:
    return (
        "🧪 **Тестовый прогон включён**\n"
        "Эмулирую работу с подключённым Авито. Онбординг и креативы — настоящие; "
        "публикация после «Утвердить» — имитация (без реальной выгрузки в кабинет). "
        "Правки и обучение памяти сохраняются.\n\n"
        "Дальше: завершите настройку (если ещё идёт), затем напишите **сделай пост**."
    )
