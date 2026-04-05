import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Pitch(Base):
    __tablename__ = "pitches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    concept_summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience_hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    appeal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_topics: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_llm_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    originality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    similar_videos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="pitches")
