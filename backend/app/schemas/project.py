from __future__ import annotations
import uuid
from pydantic import BaseModel, Field, model_validator
from app.models.project import ProjectType, ProjectStatus

_SERIALISED_STORY_BIBLE_KEYS = {"characters", "plot_threads", "timeline"}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: ProjectType
    story_bible: dict | None = None
    episode_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_story_bible(self) -> "ProjectCreate":
        if self.type == ProjectType.serialised and self.story_bible is not None:
            missing = _SERIALISED_STORY_BIBLE_KEYS - self.story_bible.keys()
            if missing:
                raise ValueError(
                    f"story_bible for a serialised project must include keys: {missing}"
                )
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    story_bible: dict | None = None
    status: ProjectStatus | None = None
    episode_count: int | None = Field(default=None, ge=1)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    type: ProjectType
    story_bible: dict | None
    status: ProjectStatus
    episode_count: int | None

    model_config = {"from_attributes": True}
