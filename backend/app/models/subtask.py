import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Text, Numeric, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.postgres import Base


class SubtaskType(str, enum.Enum):
    ideation = "ideation"
    script = "script"
    audio_preview = "audio_preview"
    review = "review"
    scene_plan = "scene_plan"
    visual_gen = "visual_gen"
    audio_gen = "audio_gen"
    assembly = "assembly"
    final_review = "final_review"
    metadata = "metadata"
    publish = "publish"


class SubtaskStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    waiting_review = "waiting_review"


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[SubtaskType] = mapped_column(Enum(SubtaskType), nullable=False)
    status: Mapped[SubtaskStatus] = mapped_column(Enum(SubtaskStatus), default=SubtaskStatus.queued, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    output_artifacts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="subtasks")
    review_actions: Mapped[list["ReviewAction"]] = relationship("ReviewAction", back_populates="subtask")
