"""add bossa bank

Revision ID: 7b9c2d4e8f10
Revises: f2b7c9d4e1a6
Create Date: 2026-06-04 18:45:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "7b9c2d4e8f10"
down_revision: Union[str, None] = "f2b7c9d4e1a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BANKS = [
    {"name": "Dom Maklerski BOŚ / bossa.pl", "shortname": "BOSSA", "bic": None},
]


def upgrade() -> None:
    conn = op.get_bind()
    stmt = sa.text(
        """
        INSERT INTO banks (id, name, shortname, bic)
        VALUES (:id, :name, :shortname, :bic)
        ON CONFLICT DO NOTHING
        """
    )

    for bank in BANKS:
        conn.execute(
            stmt,
            {
                "id": uuid4(),
                "name": bank["name"],
                "shortname": bank["shortname"],
                "bic": bank["bic"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM banks
            WHERE name = ANY(:names) OR shortname = ANY(:shorts)
            """
        ),
        {
            "names": [bank["name"] for bank in BANKS],
            "shorts": [bank["shortname"] for bank in BANKS],
        },
    )
