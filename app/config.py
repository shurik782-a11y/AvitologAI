"""Application settings from environment."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AvitologAI"
    data_dir: str = "data"
    database_url: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Fast / free orchestrator defaults (overridable in app settings UI)
    orchestrator_model: str = "openrouter/free"
    vision_model: str = "openrouter/free"
    image_model: str = "black-forest-labs/flux.2-flex"
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    public_base_url: str = ""
    # Comma-separated Telegram user IDs allowed into the WebApp/API
    admin_ids: str = ""
    # Built-in agent instructions live in app.services.prompts (never shown in UI).
    # Kept for backward-compatible seeding of AppSettings; runtime ignores legacy defaults.
    default_orchestrator_instruction: str = ""

    @property
    def db_url(self) -> str:
        if self.database_url:
            url = self.database_url.strip()
            # Railway / Heroku often give postgres:// — SQLAlchemy needs postgresql://
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://") :]
            # Prefer psycopg v3 driver when available
            if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        path = Path(self.data_dir) / "avitolog.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"


settings = Settings()
