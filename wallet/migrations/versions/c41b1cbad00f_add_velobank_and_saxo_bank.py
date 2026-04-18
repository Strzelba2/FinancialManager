"""add velobank and saxo bank

Revision ID: c41b1cbad00f
Revises: a06aa6f90230
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from uuid import uuid4


# revision identifiers, used by Alembic.
revision: str = 'c41b1cbad00f'
down_revision: Union[str, None] = 'a06aa6f90230'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BANKS = [
    {"name": "VeloBank", "shortname": "VELO", "bic": "GBGCPLPK"},
    {"name": "Saxo Bank", "shortname": "SAXO", "bic": "SAXODKKK"},
]


def upgrade() -> None:
    conn = op.get_bind()

    stmt = sa.text("""
        INSERT INTO banks (id, name, shortname, bic)
        VALUES (:id, :name, :shortname, :bic)
        ON CONFLICT DO NOTHING
    """)

    for b in BANKS:
        params = {
            "id": uuid4(),
            "name": b["name"],
            "shortname": b["shortname"],
            "bic": b.get("bic"),
        }
        conn.execute(stmt, params)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM banks
            WHERE name = ANY(:names) OR shortname = ANY(:shorts)
        """),
        {
            "names": [b["name"] for b in BANKS],
            "shorts": [b["shortname"] for b in BANKS],
        },
    )
