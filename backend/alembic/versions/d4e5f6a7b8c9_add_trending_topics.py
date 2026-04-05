"""Add trending_topics table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trending_topics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(512), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),   # google_trends | reddit | news
        sa.Column("score", sa.Float, nullable=False, default=0.0),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_trending_topics_workspace_id", "trending_topics", ["workspace_id"])
    op.create_index("ix_trending_topics_score", "trending_topics", ["workspace_id", "score"])


def downgrade() -> None:
    op.drop_table("trending_topics")
