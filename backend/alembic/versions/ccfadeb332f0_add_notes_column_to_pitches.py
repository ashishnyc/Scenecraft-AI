"""Add notes column to pitches

Revision ID: ccfadeb332f0
Revises: f6a7b8c9d0e1
Create Date: 2026-04-05 10:47:21.806251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ccfadeb332f0'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pitches', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('pitches', 'notes')
