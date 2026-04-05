from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class ChannelInsight(BaseModel):
    channel_id: str
    video_count: int
    avg_views: float | None
    avg_likes: float | None
    avg_comments: float | None
    last_scraped: datetime | None
    top_videos: list[dict[str, Any]]


class CompetitorInsightsResponse(BaseModel):
    workspace_id: uuid.UUID
    channels: list[ChannelInsight]
