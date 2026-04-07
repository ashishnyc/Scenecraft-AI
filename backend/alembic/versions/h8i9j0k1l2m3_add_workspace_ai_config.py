"""Add workspace_ai_configs table

Revision ID: h8i9j0k1l2m3
Revises: ccfadeb332f0
Create Date: 2026-04-07

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'ccfadeb332f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspace_ai_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('provider', sa.String(50), nullable=False, server_default='ollama'),
        sa.Column('model', sa.String(255), nullable=False, server_default='kimi-k2.5:cloud'),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('feature_overrides', JSONB(), nullable=False, server_default='{}'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('workspace_ai_configs')
