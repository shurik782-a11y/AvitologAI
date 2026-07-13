"""SQLAlchemy models and session."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    openrouter_api_key: Mapped[str] = mapped_column(Text, default="")
    orchestrator_model: Mapped[str] = mapped_column(String(200), default="openrouter/free")
    vision_model: Mapped[str] = mapped_column(String(200), default="openrouter/free")
    image_model: Mapped[str] = mapped_column(String(200), default="black-forest-labs/flux.2-flex")
    orchestrator_instruction: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    theme: Mapped[str] = mapped_column(Text, default="")
    ideas: Mapped[str] = mapped_column(Text, default="")
    constraints: Mapped[str] = mapped_column(Text, default="")
    # Per-project model overrides (empty = inherit env / app defaults)
    orchestrator_model: Mapped[str] = mapped_column(String(200), default="")
    vision_model: Mapped[str] = mapped_column(String(200), default="")
    image_model: Mapped[str] = mapped_column(String(200), default="")
    orchestrator_prompt: Mapped[str] = mapped_column(Text, default="")
    vision_prompt: Mapped[str] = mapped_column(Text, default="")
    image_style_prompt: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list[Message]] = relationship(back_populates="project", cascade="all, delete-orphan")
    memories: Mapped[list[Memory]] = relationship(back_populates="project", cascade="all, delete-orphan")
    creatives: Mapped[list[Creative]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[Any]] = mapped_column(JSON, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))  # preference | edit_pattern | frequent_action
    content: Mapped[str] = mapped_column(Text)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="memories")


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[str] = mapped_column(Text, default="")
    images: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft | approved | revised
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="creatives")


class MetricEvent(Base):
    __tablename__ = "metric_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float] = mapped_column(Float, default=1.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


connect_args: dict[str, Any] = {}
if settings.db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.db_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _sqlite_fk(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
    if settings.db_url.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_project_columns()
    with SessionLocal() as db:
        row = db.get(AppSettings, 1)
        if row is None:
            db.add(
                AppSettings(
                    id=1,
                    openrouter_api_key=settings.openrouter_api_key,
                    orchestrator_model=settings.orchestrator_model,
                    vision_model=settings.vision_model,
                    image_model=settings.image_model,
                    orchestrator_instruction=settings.default_orchestrator_instruction,
                )
            )
            db.commit()


def _ensure_project_columns() -> None:
    """Add new project columns on existing DBs (create_all does not alter)."""
    cols = {
        "orchestrator_model": "VARCHAR(200) DEFAULT ''",
        "vision_model": "VARCHAR(200) DEFAULT ''",
        "image_model": "VARCHAR(200) DEFAULT ''",
        "orchestrator_prompt": "TEXT DEFAULT ''",
        "vision_prompt": "TEXT DEFAULT ''",
        "image_style_prompt": "TEXT DEFAULT ''",
    }
    with engine.begin() as conn:
        existing: set[str] = set()
        if settings.db_url.startswith("sqlite"):
            rows = conn.exec_driver_sql("PRAGMA table_info(projects)").fetchall()
            existing = {r[1] for r in rows}
        else:
            rows = conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'projects'"
            ).fetchall()
            existing = {str(r[0]) for r in rows}
        for name, ddl in cols.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE projects ADD COLUMN {name} {ddl}")


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
