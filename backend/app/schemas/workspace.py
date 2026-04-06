from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    youtube_channel_id: str | None = None
    style_guide: dict | None = None
    competitor_channels: list | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    style_guide: dict | None = None
    competitor_channels: list | None = None


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    youtube_channel_id: str | None
    style_guide: dict | None
    competitor_channels: list | None
    created_at: datetime

    model_config = {"from_attributes": True}
