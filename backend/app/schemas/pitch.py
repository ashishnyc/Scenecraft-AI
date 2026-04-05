from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class PitchData(BaseModel):
    """Structured output from the LLM — validated before saving."""
    title: str = Field(..., min_length=3, max_length=512)
    concept_summary: str = Field(..., min_length=50, max_length=1500)
    target_audience_hook: str | None = Field(default=None, max_length=500)
    appeal_score: float | None = Field(default=None, ge=0.0, le=10.0)

    @model_validator(mode="after")
    def concept_word_count(self) -> "PitchData":
        words = len(self.concept_summary.split())
        if words < 10:
            raise ValueError("concept_summary must be at least 10 words")
        return self


class PitchResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    concept_summary: str
    target_audience_hook: str | None
    appeal_score: float | None
    source_topics: list | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PitchListResponse(BaseModel):
    workspace_id: uuid.UUID
    pitches: list[PitchResponse]
