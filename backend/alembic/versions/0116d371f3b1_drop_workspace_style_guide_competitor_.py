"""drop_workspace_style_guide_competitor_channels

Revision ID: 0116d371f3b1
Revises: g7b8c9d0e1f2
Create Date: 2026-04-06 14:39:57.819686

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0116d371f3b1'
down_revision: Union[str, Sequence[str], None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('workspaces', 'style_guide')
    op.drop_column('workspaces', 'competitor_channels')


def downgrade() -> None:
    op.add_column('workspaces', op.Column('competitor_channels', postgresql.JSONB(), nullable=True))
    op.add_column('workspaces', op.Column('style_guide', postgresql.JSONB(), nullable=True))
