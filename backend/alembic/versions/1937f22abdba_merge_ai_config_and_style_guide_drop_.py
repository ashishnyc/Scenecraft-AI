"""merge ai_config and style_guide drop heads

Revision ID: 1937f22abdba
Revises: 0116d371f3b1, h8i9j0k1l2m3
Create Date: 2026-04-07 12:46:46.490471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1937f22abdba'
down_revision: Union[str, Sequence[str], None] = ('0116d371f3b1', 'h8i9j0k1l2m3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
