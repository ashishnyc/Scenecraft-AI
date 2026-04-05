"""Add originality fields to pitches table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pitches", sa.Column("originality_score", sa.Float, nullable=True))
    op.add_column("pitches", sa.Column("similar_videos", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("pitches", "similar_videos")
    op.drop_column("pitches", "originality_score")
