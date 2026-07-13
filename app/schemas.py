"""Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    theme: str = ""
    ideas: str = ""
    constraints: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = None
    theme: str | None = None
    ideas: str | None = None
    constraints: str | None = None
    extra: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    theme: str
    ideas: str
    constraints: str
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppSettingsOut(BaseModel):
    openrouter_api_key_set: bool
    openrouter_api_key_masked: str = ""
    orchestrator_model: str
    vision_model: str
    image_model: str
    orchestrator_instruction: str


class AppSettingsUpdate(BaseModel):
    openrouter_api_key: str | None = None
    orchestrator_model: str | None = None
    vision_model: str | None = None
    image_model: str | None = None
    orchestrator_instruction: str | None = None


class ChatRequest(BaseModel):
    content: str = ""
    images: list[str] = Field(default_factory=list)  # data URLs or /uploads paths
    generate_images: bool = True
    revise_of_creative_id: int | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    attachments: list[Any]
    meta: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class CreativeOut(BaseModel):
    id: int
    title: str
    description: str
    image_prompt: str
    analysis: str
    images: list[Any]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    messages: list[MessageOut]
    creative: CreativeOut | None = None


class MemoryOut(BaseModel):
    id: int
    kind: str
    content: str
    hits: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    kind: str = "preference"
    content: str = Field(min_length=1)


class ApproveRequest(BaseModel):
    note: str = ""


class MetricsOut(BaseModel):
    project_id: int | None = None
    totals: dict[str, float]
    recent: list[dict[str, Any]]
