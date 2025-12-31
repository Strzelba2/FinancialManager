"""update market and add instrument_type

Revision ID: e90a6a719b02
Revises: 8079bd290439
Create Date: 2025-12-18 17:45:44.880720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e90a6a719b02'
down_revision: Union[str, Sequence[str], None] = '8079bd290439'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insert_sql = sa.text("""
        INSERT INTO market (mic, name, country, timezone, active, currency)
        VALUES (:mic, :name, :country, :tz, :active, :currency)
        ON CONFLICT (mic) DO UPDATE
        SET name = EXCLUDED.name,
            country = EXCLUDED.country,
            timezone = EXCLUDED.timezone,
            active = EXCLUDED.active,
            currency = EXCLUDED.currency
    """)
    conn = op.get_bind()
    conn.execute(insert_sql, {
        "mic": "STCM",
        "name": "Stooq Commodities",
        "country": "GLOBAL",
        "tz": "UTC",
        "active": True,
        "currency": "USD",
    })

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE instrument_type_enum ADD VALUE IF NOT EXISTS 'COMMODITY';")


def downgrade() -> None:
    # Remove seeded market
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM market WHERE mic = 'STCM'"))

    pass