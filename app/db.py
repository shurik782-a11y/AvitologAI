"""SQLAlchemy models and session."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
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
    orchestrator_model: Mapped[str] = mapped_column(String(200), default="")
    vision_model: Mapped[str] = mapped_column(String(200), default="")
    image_model: Mapped[str] = mapped_column(String(200), default="")
    orchestrator_prompt: Mapped[str] = mapped_column(Text, default="")
    vision_prompt: Mapped[str] = mapped_column(Text, default="")
    image_style_prompt: Mapped[str] = mapped_column(Text, default="")
    # Listing methodology slots (filled at onboarding; empty = unused)
    listing_type: Mapped[str] = mapped_column(String(32), default="")
    advantages: Mapped[str] = mapped_column(Text, default="")
    buyer_pains: Mapped[str] = mapped_column(Text, default="")
    why_here: Mapped[str] = mapped_column(Text, default="")
    ad_idea: Mapped[str] = mapped_column(Text, default="")
    search_query: Mapped[str] = mapped_column(String(200), default="")
    conversion_offer: Mapped[str] = mapped_column(String(200), default="")
    company_info: Mapped[str] = mapped_column(Text, default="")
    photo_count: Mapped[int] = mapped_column(Integer, default=1)
    allow_people: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_text_overlays: Mapped[bool] = mapped_column(Boolean, default=False)
    competitor_insights: Mapped[str] = mapped_column(Text, default="")
    visual_style_notes: Mapped[str] = mapped_column(Text, default="")
    onboarding_status: Mapped[str] = mapped_column(String(32), default="awaiting_brief")
    avito_feed_token: Mapped[str] = mapped_column(String(64), default="")
    avito_category: Mapped[str] = mapped_column(String(200), default="")
    avito_address: Mapped[str] = mapped_column(String(300), default="")
    avito_contact_phone: Mapped[str] = mapped_column(String(64), default="")
    avito_client_id: Mapped[str] = mapped_column(String(200), default="")
    avito_client_secret: Mapped[str] = mapped_column(Text, default="")
    avito_user_id: Mapped[str] = mapped_column(String(64), default="")
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list[Message]] = relationship(back_populates="project", cascade="all, delete-orphan")
    memories: Mapped[list[Memory]] = relationship(back_populates="project", cascade="all, delete-orphan")
    creatives: Mapped[list[Creative]] = relationship(back_populates="project", cascade="all, delete-orphan")
    publish_runs: Mapped[list[PublishRun]] = relationship(back_populates="project", cascade="all, delete-orphan")
    stat_snapshots: Mapped[list[AvitoStatSnapshot]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[Any]] = mapped_column(JSON, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="messages")


class StoredMedia(Base):
    """Durable image blobs (Postgres survives Railway redeploys; disk is only a cache)."""

    __tablename__ = "stored_media"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(64), default="image/png")
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="memories")


class GlobalMemory(Base):
    """Cross-project mistake/fix patterns (never stores project creatives)."""

    __tablename__ = "global_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[str] = mapped_column(Text, default="")
    images: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    price: Mapped[str] = mapped_column(String(64), default="")
    avito_ad_id: Mapped[str] = mapped_column(String(64), default="")
    avito_item_id: Mapped[str] = mapped_column(String(64), default="")
    publish_status: Mapped[str] = mapped_column(String(64), default="")
    last_feed_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="creatives")
    snapshots: Mapped[list[AvitoStatSnapshot]] = relationship(
        back_populates="creative", cascade="all, delete-orphan"
    )


class PublishRun(Base):
    __tablename__ = "publish_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(64), default="queued")
    feed_url: Mapped[str] = mapped_column(Text, default="")
    upload_id: Mapped[str] = mapped_column(String(128), default="")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="publish_runs")


class AvitoStatSnapshot(Base):
    __tablename__ = "avito_stat_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    creative_id: Mapped[int] = mapped_column(ForeignKey("creatives.id", ondelete="CASCADE"), index=True)
    avito_item_id: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="stat_snapshots")
    creative: Mapped[Creative] = relationship(back_populates="snapshots")


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


PROJECT_COLUMNS: dict[str, str] = {
    "orchestrator_model": "VARCHAR(200) DEFAULT ''",
    "vision_model": "VARCHAR(200) DEFAULT ''",
    "image_model": "VARCHAR(200) DEFAULT ''",
    "orchestrator_prompt": "TEXT DEFAULT ''",
    "vision_prompt": "TEXT DEFAULT ''",
    "image_style_prompt": "TEXT DEFAULT ''",
    "onboarding_status": "VARCHAR(32) DEFAULT 'awaiting_brief'",
    "avito_feed_token": "VARCHAR(64) DEFAULT ''",
    "avito_category": "VARCHAR(200) DEFAULT ''",
    "avito_address": "VARCHAR(300) DEFAULT ''",
    "avito_contact_phone": "VARCHAR(64) DEFAULT ''",
    "avito_client_id": "VARCHAR(200) DEFAULT ''",
    "avito_client_secret": "TEXT DEFAULT ''",
    "avito_user_id": "VARCHAR(64) DEFAULT ''",
    "listing_type": "VARCHAR(32) DEFAULT ''",
    "advantages": "TEXT DEFAULT ''",
    "buyer_pains": "TEXT DEFAULT ''",
    "why_here": "TEXT DEFAULT ''",
    "ad_idea": "TEXT DEFAULT ''",
    "search_query": "VARCHAR(200) DEFAULT ''",
    "conversion_offer": "VARCHAR(200) DEFAULT ''",
    "company_info": "TEXT DEFAULT ''",
    "photo_count": "INTEGER DEFAULT 1",
    "allow_people": "BOOLEAN DEFAULT FALSE",
    "allow_text_overlays": "BOOLEAN DEFAULT FALSE",
    "competitor_insights": "TEXT DEFAULT ''",
    "visual_style_notes": "TEXT DEFAULT ''",
}

CREATIVE_COLUMNS: dict[str, str] = {
    "price": "VARCHAR(64) DEFAULT ''",
    "avito_ad_id": "VARCHAR(64) DEFAULT ''",
    "avito_item_id": "VARCHAR(64) DEFAULT ''",
    "publish_status": "VARCHAR(64) DEFAULT ''",
    "last_feed_error": "TEXT DEFAULT ''",
    # Postgres: TIMESTAMP WITH TIME ZONE; SQLite accepts the same type name
    "published_at": "TIMESTAMP WITH TIME ZONE",
    "meta": "JSON",
}


def init_db() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_columns("projects", PROJECT_COLUMNS)
    _ensure_columns("creatives", CREATIVE_COLUMNS)
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


def _ensure_columns(table: str, cols: dict[str, str]) -> None:
    with engine.begin() as conn:
        existing: set[str] = set()
        if settings.db_url.startswith("sqlite"):
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            existing = {r[1] for r in rows}
        else:
            rows = conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}'"
            ).fetchall()
            existing = {str(r[0]) for r in rows}
        for name, ddl in cols.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
