from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from app.models.subtask import SubtaskStatus, SubtaskType


class SubtaskCreate(BaseModel):
    type: SubtaskType
    depends_on: list[str] = Field(default_factory=list)  # list of subtask UUID strings


class SubtaskUpdate(BaseModel):
    status: SubtaskStatus | None = None
    output_artifacts: dict | None = None
    cost_usd: Decimal | None = None
    error_log: str | None = None


class SubtaskResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    type: SubtaskType
    status: SubtaskStatus
    depends_on: list[str] | None
    started_at: datetime | None
    completed_at: datetime | None
    cost_usd: Decimal | None
    output_artifacts: dict | None
    error_log: str | None

    model_config = {"from_attributes": True}
