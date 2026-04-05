from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from app.models.character import RoleType, CastingRole, CastingStatus


class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role_type: RoleType
    personality_prompt: str | None = None
    backstory: str | None = None
    age: int | None = Field(default=None, ge=0)
    voice_profile_id: str | None = None


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role_type: RoleType | None = None
    personality_prompt: str | None = None
    backstory: str | None = None
    age: int | None = Field(default=None, ge=0)
    voice_profile_id: str | None = None
    lora_model_url: str | None = None


class AppearanceVersionCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    image_url: str | None = None


class CharacterResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    role_type: RoleType
    personality_prompt: str | None
    backstory: str | None
    age: int | None
    lora_model_url: str | None
    voice_profile_id: str | None
    visual_references: dict | None
    appearance_state: dict | None
    engagement_stats: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Casting schemas ───────────────────────────────────────────────────────────

class CastingCreate(BaseModel):
    character_id: uuid.UUID
    role: CastingRole
    character_arc_notes: str | None = None
    first_episode: int | None = Field(default=None, ge=1)
    appearance_override: dict[str, Any] | None = None


class CastingUpdate(BaseModel):
    role: CastingRole | None = None
    character_arc_notes: str | None = None
    status: CastingStatus | None = None
    appearance_override: dict[str, Any] | None = None


class CastingResponse(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    project_id: uuid.UUID
    role: CastingRole
    character_arc_notes: str | None
    first_episode: int | None
    status: CastingStatus
    appearance_override: dict | None
    character: CharacterResponse

    model_config = {"from_attributes": True}


# ── Analytics schema ──────────────────────────────────────────────────────────

class CharacterAnalytics(BaseModel):
    character_id: uuid.UUID
    name: str
    total_appearances: int
    total_views: int
    avg_views_per_appearance: float
    top_project_id: str | None
    engagement_breakdown: dict[str, Any]
