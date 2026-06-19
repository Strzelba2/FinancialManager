"""widen brokerage event price scale to 3 decimals

Revision ID: c8e3a7b21f04
Revises: 4f2b8c1d9a0e
Create Date: 2026-06-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e3a7b21f04"
down_revision: Union[str, Sequence[str], None] = "4f2b8c1d9a0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "brokerage_events",
        "price",
        existing_type=sa.Numeric(precision=20, scale=2),
        type_=sa.Numeric(precision=20, scale=3),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )


def downgrade() -> None:
    op.alter_column(
        "brokerage_events",
        "price",
        existing_type=sa.Numeric(precision=20, scale=3),
        type_=sa.Numeric(precision=20, scale=2),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
