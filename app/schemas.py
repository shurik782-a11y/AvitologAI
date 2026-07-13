"""Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


LISTING_SLOT_KEYS = (
    "listing_type",
    "advantages",
    "buyer_pains",
    "why_here",
    "ad_idea",
    "search_query",
    "conversion_offer",
    "company_info",
    "photo_count",
    "allow_people",
    "allow_text_overlays",
    "competitor_insights",
    "visual_style_notes",
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    theme: str = ""
    ideas: str = ""
    constraints: str = ""
    orchestrator_model: str = ""
    vision_model: str = ""
    image_model: str = ""
    orchestrator_prompt: str = ""
    vision_prompt: str = ""
    image_style_prompt: str = ""
    listing_type: str = ""
    advantages: str = ""
    buyer_pains: str = ""
    why_here: str = ""
    ad_idea: str = ""
    search_query: str = ""
    conversion_offer: str = ""
    company_info: str = ""
    photo_count: int = 1
    allow_people: bool = False
    allow_text_overlays: bool = False
    competitor_insights: str = ""
    visual_style_notes: str = ""
    avito_category: str = ""
    avito_address: str = ""
    avito_contact_phone: str = ""
    avito_client_id: str = ""
    avito_client_secret: str = ""
    avito_user_id: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = None
    theme: str | None = None
    ideas: str | None = None
    constraints: str | None = None
    orchestrator_model: str | None = None
    vision_model: str | None = None
    image_model: str | None = None
    orchestrator_prompt: str | None = None
    vision_prompt: str | None = None
    image_style_prompt: str | None = None
    listing_type: str | None = None
    advantages: str | None = None
    buyer_pains: str | None = None
    why_here: str | None = None
    ad_idea: str | None = None
    search_query: str | None = None
    conversion_offer: str | None = None
    company_info: str | None = None
    photo_count: int | None = None
    allow_people: bool | None = None
    allow_text_overlays: bool | None = None
    competitor_insights: str | None = None
    visual_style_notes: str | None = None
    avito_category: str | None = None
    avito_address: str | None = None
    avito_contact_phone: str | None = None
    avito_client_id: str | None = None
    avito_client_secret: str | None = None
    avito_user_id: str | None = None
    extra: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    theme: str
    ideas: str
    constraints: str
    orchestrator_model: str = ""
    vision_model: str = ""
    image_model: str = ""
    orchestrator_prompt: str = ""
    vision_prompt: str = ""
    image_style_prompt: str = ""
    listing_type: str = ""
    advantages: str = ""
    buyer_pains: str = ""
    why_here: str = ""
    ad_idea: str = ""
    search_query: str = ""
    conversion_offer: str = ""
    company_info: str = ""
    photo_count: int = 1
    allow_people: bool = False
    allow_text_overlays: bool = False
    competitor_insights: str = ""
    visual_style_notes: str = ""
    onboarding_status: str = "awaiting_brief"
    avito_feed_token: str = ""
    avito_category: str = ""
    avito_address: str = ""
    avito_contact_phone: str = ""
    avito_client_id: str = ""
    avito_user_id: str = ""
    avito_client_secret_set: bool = False
    feed_url: str = ""
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
    default_orchestrator_model: str = ""
    default_vision_model: str = ""
    default_image_model: str = ""


class AppSettingsUpdate(BaseModel):
    openrouter_api_key: str | None = None
    orchestrator_model: str | None = None
    vision_model: str | None = None
    image_model: str | None = None
    orchestrator_instruction: str | None = None


class ChatRequest(BaseModel):
    content: str = ""
    images: list[str] = Field(default_factory=list)
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
    price: str = ""
    avito_ad_id: str = ""
    avito_item_id: str = ""
    publish_status: str = ""
    last_feed_error: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    published_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    messages: list[MessageOut]
    creative: CreativeOut | None = None
    onboarding_done: bool = False


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
    trigger_upload: bool = True


class ApproveResponse(BaseModel):
    creative: CreativeOut
    feed_url: str = ""
    publish_run_id: int | None = None
    message: str = ""


class MetricsOut(BaseModel):
    project_id: int | None = None
    totals: dict[str, float]
    recent: list[dict[str, Any]]


class BillingSummary(BaseModel):
    available: bool
    remaining: float | None = None
    usage_monthly: float | None = None
    label: str = ""
    error: str = ""


class PublishRunOut(BaseModel):
    id: int
    status: str
    feed_url: str
    upload_id: str
    report: dict[str, Any]
    error: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicationMetricOut(BaseModel):
    creative_id: int
    title: str
    avito_item_id: str = ""
    avito_ad_id: str = ""
    publish_status: str = ""
    status: str = ""
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    has_snapshot: bool = False


class StatSnapshotOut(BaseModel):
    creative_id: int
    avito_item_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime | None = None
    message: str = ""


class CompetitorsImportResult(BaseModel):
    rows_read: int
    rows_used: int
    competitor_insights: str
    message: str = ""
