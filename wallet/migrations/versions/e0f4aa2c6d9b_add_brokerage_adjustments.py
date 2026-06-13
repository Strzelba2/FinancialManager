"""add brokerage adjustments

Revision ID: e0f4aa2c6d9b
Revises: d4f61a2b9c7e
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0f4aa2c6d9b"
down_revision: Union[str, None] = "d4f61a2b9c7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'DIV'")
    op.execute("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'ADJUSTMENT'")
    op.alter_column(
        "brokerage_events",
        "split_ratio",
        existing_type=sa.Numeric(precision=20, scale=2),
        type_=sa.Numeric(precision=28, scale=10),
        existing_nullable=False,
    )
    op.add_column(
        "brokerage_events",
        sa.Column("note", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brokerage_events", "note")
    op.alter_column(
        "brokerage_events",
        "split_ratio",
        existing_type=sa.Numeric(precision=28, scale=10),
        type_=sa.Numeric(precision=20, scale=2),
        existing_nullable=False,
    )
