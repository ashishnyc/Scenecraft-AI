import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.postgres import Base


class ProjectType(str, enum.Enum):
    serialised = "serialised"
    anthology = "anthology"


class ProjectStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    paused = "paused"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ProjectType] = mapped_column(Enum(ProjectType), nullable=False)
    story_bible: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.active, nullable=False)
    episode_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    character_castings: Mapped[list["CharacterCasting"]] = relationship("CharacterCasting", back_populates="project", cascade="all, delete-orphan")
