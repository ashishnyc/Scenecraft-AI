import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    youtube_channel_id: Mapped[str | None] = mapped_column(String(255))
    youtube_oauth_token: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")
    competitor_videos: Mapped[list["CompetitorVideo"]] = relationship("CompetitorVideo", back_populates="workspace", cascade="all, delete-orphan")
    trending_topics: Mapped[list["TrendingTopic"]] = relationship("TrendingTopic", back_populates="workspace", cascade="all, delete-orphan")
    pitches: Mapped[list["Pitch"]] = relationship("Pitch", back_populates="workspace", cascade="all, delete-orphan")
