"""Add competitor_videos table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitor_videos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.String(255), nullable=False),
        sa.Column("video_id", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("view_count", sa.BigInteger, nullable=True),
        sa.Column("like_count", sa.BigInteger, nullable=True),
        sa.Column("comment_count", sa.BigInteger, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_competitor_videos_workspace_id", "competitor_videos", ["workspace_id"])
    op.create_index("ix_competitor_videos_channel_id", "competitor_videos", ["channel_id"])
    op.create_unique_constraint(
        "uq_competitor_videos_workspace_video",
        "competitor_videos",
        ["workspace_id", "video_id"],
    )


def downgrade() -> None:
    op.drop_table("competitor_videos")
