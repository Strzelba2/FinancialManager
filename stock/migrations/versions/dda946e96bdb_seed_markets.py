"""Seed Markets

Revision ID: dda946e96bdb
Revises: c7455a2394cf
Create Date: 2025-11-13 17:38:38.846138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dda946e96bdb'
down_revision: Union[str, Sequence[str], None] = 'c7455a2394cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MARKETS = [
    # mic,        name,                          country, timezone,        active
    ("XWAR",     "GPW (Warsaw Stock Exchange)",  "PL",    "Europe/Warsaw",  True),
    ("XNCO",     "NEWCONNECT (GPW)",             "PL",    "Europe/Warsaw",  True),
    ("XLON",     "London Stock Exchange",        "GB",    "Europe/London",  True),
    ("XPAR",     "Euronext Paris",               "FR",    "Europe/Paris",   True),
    ("XWBO",     "Wiener Börse (Vienna)",        "AT",    "Europe/Vienna",  True),
    ("XETR",     "Xetra (Deutsche Börse)",       "DE",    "Europe/Berlin",  True),
    ("XSWX",     "SIX Swiss Exchange",           "CH",    "Europe/Zurich",  True),
    ("XBRU",     "Euronext Brussels",            "BE",    "Europe/Brussels",True),
    ("XAMS",     "Euronext Amsterdam",           "NL",    "Europe/Amsterdam", True),
    ("XMIL",     "Borsa Italiana (Milan)",       "IT",    "Europe/Rome",    True),
]

def upgrade() -> None:
    # ensure pgcrypto for gen_random_uuid() if you use server-side UUIDs
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # optional: normalize MICs to uppercase on insert
    insert_sql = sa.text("""
        INSERT INTO market (mic, name, country, timezone, active)
        VALUES (:mic, :name, :country, :tz, :active)
        ON CONFLICT (mic) DO UPDATE
        SET name = EXCLUDED.name,
            country = EXCLUDED.country,
            timezone = EXCLUDED.timezone,
            active = EXCLUDED.active
    """)

    conn = op.get_bind()
    for mic, name, country, tz, active in MARKETS:
        conn.execute(
            insert_sql,
            {"mic": mic.upper(), "name": name, "country": country, "tz": tz, "active": active},
        )

def downgrade() -> None:
    # remove only what we seeded (safe even if renamed thanks to mic key)
    delete_sql = sa.text("DELETE FROM market WHERE mic = :mic")
    conn = op.get_bind()
    for mic, *_ in MARKETS:
        conn.execute(delete_sql, {"mic": mic.upper()})