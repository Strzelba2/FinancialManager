"""seed PLNC market

Revision ID: b7c3d9e1f2a4
Revises: 9dd9730f9576
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c3d9e1f2a4"
down_revision: Union[str, Sequence[str], None] = "9dd9730f9576"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insert_sql = sa.text(
        """
        INSERT INTO market (mic, name, country, timezone, active, currency)
        VALUES (:mic, :name, :country, :tz, :active, :currency)
        ON CONFLICT (mic) DO UPDATE
        SET name = EXCLUDED.name,
            country = EXCLUDED.country,
            timezone = EXCLUDED.timezone,
            active = EXCLUDED.active,
            currency = EXCLUDED.currency
        """
    )
    conn = op.get_bind()
    conn.execute(
        insert_sql,
        {
            "mic": "PLNC",
            "name": "PLN Currency",
            "country": "GLOBAL",
            "tz": "Europe/Warsaw",
            "active": True,
            "currency": "PLN",
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM market WHERE mic = 'PLNC'"))
