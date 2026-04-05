"""Add pitches table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pitches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("concept_summary", sa.Text, nullable=False),
        sa.Column("target_audience_hook", sa.Text, nullable=True),
        sa.Column("appeal_score", sa.Float, nullable=True),
        sa.Column("source_topics", JSONB, nullable=True),   # trending topic IDs used
        sa.Column("raw_llm_output", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pitches_workspace_id", "pitches", ["workspace_id"])
    op.create_index("ix_pitches_status", "pitches", ["workspace_id", "status"])


def downgrade() -> None:
    op.drop_table("pitches")
