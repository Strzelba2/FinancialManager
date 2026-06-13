"""change price columns from Numeric(x,2) to Numeric(x,3)

Revision ID: a1b2c3d4e5f6
Revises: 6c1a2b3d4e5f
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '6c1a2b3d4e5f'
branch_labels = None
depends_on = None

_TABLES_20 = [
    ('quote_latest', 'last_price'),
    ('candle_daily', 'open'),
    ('candle_daily', 'high'),
    ('candle_daily', 'low'),
    ('candle_daily', 'close'),
]

def upgrade() -> None:
    for table, col in _TABLES_20:
        op.alter_column(table, col, type_=sa.Numeric(20, 3), existing_nullable=False)


def downgrade() -> None:
    for table, col in _TABLES_20:
        op.alter_column(table, col, type_=sa.Numeric(20, 2), existing_nullable=False)
