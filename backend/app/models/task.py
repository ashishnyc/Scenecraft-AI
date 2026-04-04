import uuid
from decimal import Decimal
from sqlalchemy import String, Text, Numeric, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.postgres import Base


class TaskStatus(str, enum.Enum):
    idea = "idea"
    approved = "approved"
    scripting = "scripting"
    audio_preview = "audio_preview"
    script_review = "script_review"
    producing = "producing"
    final_review = "final_review"
    scheduled = "scheduled"
    published = "published"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.idea, nullable=False)
    concept_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    script: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performance_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="tasks")
    subtasks: Mapped[list["Subtask"]] = relationship("Subtask", back_populates="task", cascade="all, delete-orphan")
    review_actions: Mapped[list["ReviewAction"]] = relationship("ReviewAction", back_populates="task", cascade="all, delete-orphan")
