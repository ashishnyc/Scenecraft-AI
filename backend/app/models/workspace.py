import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    youtube_channel_id: Mapped[str | None] = mapped_column(String(255))
    youtube_oauth_token: Mapped[str | None] = mapped_column(String, nullable=True)
    style_guide: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    upload_schedule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    competitor_channels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")
