"""Update tables

Revision ID: 5466688f1268
Revises: 2db43869e26f
Create Date: 2025-11-20 19:28:36.966050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5466688f1268'
down_revision: Union[str, None] = '2db43869e26f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- numeric changes ----------------------------------------------------
    op.alter_column(
        'brokerage_events',
        'quantity',
        existing_type=sa.NUMERIC(precision=20, scale=6),
        type_=sa.Numeric(precision=20, scale=2),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        'brokerage_events',
        'price',
        existing_type=sa.NUMERIC(precision=20, scale=8),
        type_=sa.Numeric(precision=20, scale=2),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        'brokerage_events',
        'split_ratio',
        existing_type=sa.NUMERIC(precision=20, scale=8),
        type_=sa.Numeric(precision=20, scale=2),
        existing_nullable=True,
        nullable=False,
    )

    # --- ENUM currency ------------------------------------------------------
    # 1) ensure enum type exists
    currency_enum = postgresql.ENUM('PLN', 'USD', 'EUR', name='currency_enum')
    bind = op.get_bind()
    currency_enum.create(bind, checkfirst=True)

    # 2) fix any NULL / invalid values before cast
    op.execute(
        """
        UPDATE brokerage_events
        SET currency = 'PLN'
        WHERE currency IS NULL
           OR currency NOT IN ('PLN', 'USD', 'EUR')
        """
    )

    # 3) change column type using explicit USING
    op.execute(
        """
        ALTER TABLE brokerage_events
        ALTER COLUMN currency TYPE currency_enum
        USING currency::currency_enum
        """
    )

    # 4) now enforce NOT NULL on the enum column
    op.alter_column(
        'brokerage_events',
        'currency',
        existing_type=currency_enum,
        nullable=False,
    )

    # --- trade_at -----------------------------------------------------------
    op.alter_column(
        'brokerage_events',
        'trade_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        nullable=False,
    )

    # --- instruments.mic ----------------------------------------------------
    op.add_column(
        'instruments',
        sa.Column('mic', sa.String(length=4), nullable=False),
    )
    op.create_index(
        op.f('ix_instruments_mic'),
        'instruments',
        ['mic'],
        unique=False,
    )


def downgrade() -> None:
    # reverse order

    op.drop_index(op.f('ix_instruments_mic'), table_name='instruments')
    op.drop_column('instruments', 'mic')

    op.alter_column(
        'brokerage_events',
        'trade_at',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        'brokerage_events',
        'split_ratio',
        existing_type=sa.Numeric(precision=20, scale=2),
        type_=sa.NUMERIC(precision=20, scale=8),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        'brokerage_events',
        'currency',
        existing_type=sa.Enum('PLN', 'USD', 'EUR', name='currency_enum'),
        type_=sa.VARCHAR(length=8),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        'brokerage_events',
        'price',
        existing_type=sa.Numeric(precision=20, scale=2),
        type_=sa.NUMERIC(precision=20, scale=8),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        'brokerage_events',
        'quantity',
        existing_type=sa.Numeric(precision=20, scale=2),
        type_=sa.NUMERIC(precision=20, scale=6),
        existing_nullable=False,
        nullable=True,
    )
    # ### end Alembic commands ###
