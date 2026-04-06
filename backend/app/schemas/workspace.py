from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    youtube_channel_id: str = Field(..., min_length=1, description="YouTube channel ID (UCxxxxxx) or handle (@name)")


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    youtube_channel_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
