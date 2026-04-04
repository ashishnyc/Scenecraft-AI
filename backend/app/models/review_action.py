import uuid
from datetime import datetime
from sqlalchemy import Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.postgres import Base


class ReviewActionType(str, enum.Enum):
    approve = "approve"
    reject = "reject"
    request_changes = "request_changes"


class ReviewAction(Base):
    __tablename__ = "review_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    subtask_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[ReviewActionType] = mapped_column(Enum(ReviewActionType), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="review_actions")
    subtask: Mapped["Subtask"] = relationship("Subtask", back_populates="review_actions")
