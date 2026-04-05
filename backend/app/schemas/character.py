from __future__ import annotations
import uuid
from pydantic import BaseModel, Field
from app.models.character import RoleType


class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role_type: RoleType
    personality_prompt: str | None = None
    backstory: str | None = None
    age: int | None = Field(default=None, ge=0)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role_type: RoleType | None = None
    personality_prompt: str | None = None
    backstory: str | None = None
    age: int | None = Field(default=None, ge=0)


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

    model_config = {"from_attributes": True}
