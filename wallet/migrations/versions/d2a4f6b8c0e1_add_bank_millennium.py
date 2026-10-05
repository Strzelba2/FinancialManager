"""add Bank Millennium

Revision ID: d2a4f6b8c0e1
Revises: c8e3a7b21f04
Create Date: 2026-08-09 12:00:00.000000

"""
from typing import Sequence, Union
from uuid import UUID

import sqlalchemy as sa
from alembic import op


revision: str = "d2a4f6b8c0e1"
down_revision: Union[str, Sequence[str], None] = "c8e3a7b21f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BANK_ID = UUID("b4908c27-8059-4ea4-9c3e-65f53b4bf372")
BANK = {
    "name": "Bank Millennium",
    "shortname": "MIL",
    "bic": "BIGBPLPW",
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO banks (id, name, shortname, bic)
            VALUES (:id, :name, :shortname, :bic)
            ON CONFLICT DO NOTHING
            """
        ),
        {"id": BANK_ID, **BANK},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM banks
            WHERE id = :id
              AND name = :name
              AND shortname = :shortname
            """
        ),
        {"id": BANK_ID, **BANK},
    )
