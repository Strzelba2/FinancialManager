"""increase_instrument_shortname_to_40

Revision ID: 9dd9730f9576
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 17:40:09.572712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9dd9730f9576'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('instrument', 'shortname',
               existing_type=sa.VARCHAR(length=12),
               type_=sa.String(length=40),
               existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('instrument', 'shortname',
               existing_type=sa.String(length=40),
               type_=sa.VARCHAR(length=12),
               existing_nullable=False)