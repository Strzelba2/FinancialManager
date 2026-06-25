"""seed GLIX market

Revision ID: c4e6f8a1b2d3
Revises: b7c3d9e1f2a4
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4e6f8a1b2d3"
down_revision: Union[str, Sequence[str], None] = "b7c3d9e1f2a4"
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
            "mic": "GLIX",
            "name": "Global Indexes",
            "country": "GLOBAL",
            "tz": "Europe/Warsaw",
            "active": True,
            "currency": "PLN",
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM market WHERE mic = 'GLIX'"))
