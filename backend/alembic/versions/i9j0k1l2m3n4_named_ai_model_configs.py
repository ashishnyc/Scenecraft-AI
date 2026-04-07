"""Named AI model configs + simplify workspace_ai_configs

Revision ID: i9j0k1l2m3n4
Revises: 1937f22abdba
Create Date: 2026-04-07

Migrates existing workspace_ai_configs rows into named model configs called
"Default", then rewires workspace_ai_configs to reference them by ID.
"""
from typing import Sequence, Union
import uuid as _uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, Sequence[str], None] = '1937f22abdba'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the new named configs table
    op.create_table(
        'workspace_ai_model_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', UUID(as_uuid=True),
                  sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(255), nullable=False),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Migrate existing workspace_ai_configs rows into named "Default" configs
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, workspace_id, provider, model, base_url, api_key_encrypted FROM workspace_ai_configs")
    ).fetchall()

    config_id_map = {}  # old workspace_ai_configs.id → new model_config.id
    for row in rows:
        new_id = _uuid.uuid4()
        config_id_map[str(row.id)] = str(new_id)
        conn.execute(sa.text("""
            INSERT INTO workspace_ai_model_configs
              (id, workspace_id, name, provider, model, base_url, api_key_encrypted, is_default)
            VALUES
              (:id, :ws_id, 'Default', :provider, :model, :base_url, :api_key, true)
        """), {
            'id': str(new_id),
            'ws_id': str(row.workspace_id),
            'provider': row.provider or 'ollama',
            'model': row.model or 'kimi-k2.5:cloud',
            'base_url': row.base_url,
            'api_key': row.api_key_encrypted,
        })

    # 3. Add new columns to workspace_ai_configs
    op.add_column('workspace_ai_configs',
        sa.Column('default_config_id', UUID(as_uuid=True),
                  sa.ForeignKey('workspace_ai_model_configs.id', ondelete='SET NULL'), nullable=True)
    )

    # 4. Populate default_config_id from the mapping
    for old_id, new_config_id in config_id_map.items():
        conn.execute(sa.text(
            "UPDATE workspace_ai_configs SET default_config_id = :cfg_id, feature_overrides = '{}' WHERE id = :id"
        ), {'cfg_id': new_config_id, 'id': old_id})

    # 5. Drop old columns
    op.drop_column('workspace_ai_configs', 'provider')
    op.drop_column('workspace_ai_configs', 'model')
    op.drop_column('workspace_ai_configs', 'base_url')
    op.drop_column('workspace_ai_configs', 'api_key_encrypted')


def downgrade() -> None:
    op.add_column('workspace_ai_configs', sa.Column('provider', sa.String(50), nullable=True))
    op.add_column('workspace_ai_configs', sa.Column('model', sa.String(255), nullable=True))
    op.add_column('workspace_ai_configs', sa.Column('base_url', sa.String(500), nullable=True))
    op.add_column('workspace_ai_configs', sa.Column('api_key_encrypted', sa.Text(), nullable=True))
    op.drop_column('workspace_ai_configs', 'default_config_id')
    op.drop_table('workspace_ai_model_configs')
