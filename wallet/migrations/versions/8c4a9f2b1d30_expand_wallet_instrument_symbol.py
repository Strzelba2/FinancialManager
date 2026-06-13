"""expand wallet instrument symbol

Revision ID: 8c4a9f2b1d30
Revises: 7b9c2d4e8f10
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4a9f2b1d30"
down_revision: Union[str, None] = "7b9c2d4e8f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "instruments",
        "symbol",
        existing_type=sa.String(length=5),
        type_=sa.String(length=12),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "instruments",
        "symbol",
        existing_type=sa.String(length=12),
        type_=sa.String(length=5),
        existing_nullable=True,
    )
