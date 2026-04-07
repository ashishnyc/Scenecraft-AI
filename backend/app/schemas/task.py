from __future__ import annotations
import uuid
from decimal import Decimal
from pydantic import BaseModel, Field
from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    concept_brief: str | None = None
    creator_notes: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    concept_brief: str | None = None
    creator_notes: str | None = None
    script: dict | None = None
    brief_history: list | None = None


class TaskTransitionRequest(BaseModel):
    status: TaskStatus
    changed_scene_numbers: list[int] | None = None  # SA-28: selective audio re-generation


class TaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: TaskStatus
    concept_brief: str | None
    creator_notes: str | None
    script: dict | None
    final_video_url: str | None
    youtube_video_id: str | None
    total_cost_usd: Decimal | None
    brief_history: list | None

    model_config = {"from_attributes": True}
