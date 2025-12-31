"""added currency to market

Revision ID: 8079bd290439
Revises: dda946e96bdb
Create Date: 2025-12-07 10:25:23.027011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8079bd290439'
down_revision: Union[str, Sequence[str], None] = 'dda946e96bdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'market',
        sa.Column('currency', sa.String(length=3), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE market
            SET currency = CASE mic
                WHEN 'XWAR' THEN 'PLN'
                WHEN 'XNCO' THEN 'PLN'
                WHEN 'XLON' THEN 'GBP'
                WHEN 'XPAR' THEN 'EUR'
                WHEN 'XWBO' THEN 'EUR'
                WHEN 'XETR' THEN 'EUR'
                WHEN 'XSWX' THEN 'CHF'
                WHEN 'XBRU' THEN 'EUR'
                WHEN 'XAMS' THEN 'EUR'
                WHEN 'XMIL' THEN 'EUR'
                ELSE 'EUR'
            END
            WHERE currency IS NULL
            """
        )
    )

    op.alter_column(
        'market',
        'currency',
        existing_type=sa.String(length=3),
        nullable=False,
    )

    op.create_index(
        op.f('ix_market_currency'),
        'market',
        ['currency'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_market_currency'), table_name='market')
    op.drop_column('market', 'currency')
