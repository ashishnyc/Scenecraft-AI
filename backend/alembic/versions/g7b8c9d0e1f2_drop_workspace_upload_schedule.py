"""Drop upload_schedule column from workspaces

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-06

Upload scheduling is handled at the task level (ready state triggers upload),
not at the workspace/channel level.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "g7b8c9d0e1f2"
down_revision = "ccfadeb332f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspaces", "upload_schedule")


def downgrade() -> None:
    op.add_column("workspaces", sa.Column("upload_schedule", JSONB, nullable=True))
