from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class TrendingTopicResponse(BaseModel):
    id: uuid.UUID
    topic: str
    source: str
    score: float
    raw_data: dict[str, Any] | None
    detected_at: datetime

    model_config = {"from_attributes": True}


class TrendsResponse(BaseModel):
    workspace_id: uuid.UUID
    topics: list[TrendingTopicResponse]
