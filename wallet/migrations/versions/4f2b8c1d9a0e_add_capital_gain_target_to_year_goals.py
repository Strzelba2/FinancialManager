"""add capital gain target to year goals

Revision ID: 4f2b8c1d9a0e
Revises: c7d1e2f3a4b5
Create Date: 2026-06-13 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f2b8c1d9a0e"
down_revision: Union[str, Sequence[str], None] = "c7d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "year_goals",
        sa.Column(
            "capital_gain_target_year",
            sa.Numeric(precision=20, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("year_goals", "capital_gain_target_year")
