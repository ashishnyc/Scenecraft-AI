"""Instagram content models (SA-65–67)."""
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class PostStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    posted = "posted"
    failed = "failed"


class PostType(str, enum.Enum):
    image = "image"
    carousel = "carousel"
    reel = "reel"
    story = "story"


class CommentReplyStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    posted = "posted"


class InstagramPost(Base):
    __tablename__ = "instagram_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    post_type: Mapped[PostType] = mapped_column(Enum(PostType), nullable=False, default=PostType.image)
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), nullable=False, default=PostStatus.draft)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    media_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    instagram_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engagement_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comments: Mapped[list["InstagramComment"]] = relationship("InstagramComment", back_populates="post", cascade="all, delete-orphan")


class InstagramComment(Base):
    __tablename__ = "instagram_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instagram_posts.id", ondelete="CASCADE"), nullable=False)
    instagram_comment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    author_username: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_status: Mapped[CommentReplyStatus] = mapped_column(Enum(CommentReplyStatus), nullable=False, default=CommentReplyStatus.pending)
    generated_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped["InstagramPost"] = relationship("InstagramPost", back_populates="comments")
