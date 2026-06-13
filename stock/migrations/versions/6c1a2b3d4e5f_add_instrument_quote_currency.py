"""add instrument quote currency

Revision ID: 6c1a2b3d4e5f
Revises: 4f3d2a1b8c90
Create Date: 2026-06-06 15:45:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c1a2b3d4e5f"
down_revision: Union[str, None] = "4f3d2a1b8c90"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "instrument",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.create_index(op.f("ix_instrument_currency"), "instrument", ["currency"], unique=False)

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE instrument AS i
            SET currency = m.currency
            FROM market AS m
            WHERE i.market_id = m.id
              AND m.mic IN ('XWAR', 'XNCO', 'STCM', 'MCRO')
              AND i.currency IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_instrument_currency"), table_name="instrument")
    op.drop_column("instrument", "currency")
