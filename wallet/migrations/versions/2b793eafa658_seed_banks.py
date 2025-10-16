"""seed banks

Revision ID: 2b793eafa658
Revises: 31afab4c74ca
Create Date: 2025-09-29 19:28:50.911203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from uuid import uuid4


# revision identifiers, used by Alembic.
revision: str = '2b793eafa658'
down_revision: Union[str, None] = '31afab4c74ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BANKS = [
    {"name": "mBank",             "shortname": "MBK",  "bic": "BREXPLPW"},
    {"name": "ING Bank Śląski",   "shortname": "ING",  "bic": "INGBPLPW"},
    {"name": "PKO BP",            "shortname": "PKO",  "bic": "BPKOPLPW"},
    {"name": "Santander Polska",  "shortname": "SAN",  "bic": "WBKPPLPP"},
    {"name": "Pekao SA",          "shortname": "PEKAO", "bic": "PKOPPLPW"},
    {"name": "Alior Bank",        "shortname": "ALIOR", "bic": "ALBPPLPW"},
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
