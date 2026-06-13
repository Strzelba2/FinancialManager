"""add instrument quote source

Revision ID: 4f3d2a1b8c90
Revises: 9b2a4f6c1d77
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f3d2a1b8c90"
down_revision: Union[str, None] = "9b2a4f6c1d77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instrument",
        sa.Column("quote_source", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_instrument_quote_source",
        "instrument",
        ["quote_source"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_quote_source", table_name="instrument")
    op.drop_column("instrument", "quote_source")
