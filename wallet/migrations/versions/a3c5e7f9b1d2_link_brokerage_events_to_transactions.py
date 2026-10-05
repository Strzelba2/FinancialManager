"""link brokerage events to cash transactions

Revision ID: a3c5e7f9b1d2
Revises: d2a4f6b8c0e1
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision: str = "a3c5e7f9b1d2"
down_revision: Union[str, Sequence[str], None] = "d2a4f6b8c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Existing cash settlements were created with the description
# "<BUY|SELL|DIV> <symbol> <quantity> @ <price>" on a deposit account linked to the
# brokerage account and dated exactly at the event trade_at. Only unambiguous
# one-to-one matches are linked; anything else stays unlinked.
BACKFILL_SQL = r"""
WITH trade_transactions AS (
    SELECT
        t.id,
        t.account_id,
        t.date_transaction,
        regexp_match(
            t.description,
            '^(BUY|SELL|DIV) (\S+) ([0-9]+(?:\.[0-9]+)?) @ ([0-9]+(?:\.[0-9]+)?)$'
        ) AS parts
    FROM transactions AS t
    WHERE t.description ~ '^(BUY|SELL|DIV) '
),
candidates AS (
    SELECT be.id AS event_id, tt.id AS transaction_id
    FROM brokerage_events AS be
    JOIN instruments AS i ON i.id = be.instrument_id
    JOIN brokerage_deposit_links AS l ON l.brokerage_account_id = be.brokerage_account_id
    JOIN trade_transactions AS tt ON tt.account_id = l.deposit_account_id
    WHERE be.kind IN ('TRADE_BUY', 'TRADE_SELL', 'DIV')
      AND be.transaction_id IS NULL
      AND tt.parts IS NOT NULL
      AND tt.date_transaction = be.trade_at
      AND tt.parts[1] = CASE be.kind
            WHEN 'TRADE_BUY' THEN 'BUY'
            WHEN 'TRADE_SELL' THEN 'SELL'
            ELSE 'DIV'
          END
      AND upper(tt.parts[2]) = upper(i.symbol)
      AND CAST(tt.parts[3] AS numeric) = be.quantity
      AND CAST(tt.parts[4] AS numeric) = be.price
),
unique_pairs AS (
    SELECT c.event_id, c.transaction_id
    FROM candidates AS c
    WHERE (SELECT count(*) FROM candidates AS c2 WHERE c2.event_id = c.event_id) = 1
      AND (SELECT count(*) FROM candidates AS c3 WHERE c3.transaction_id = c.transaction_id) = 1
)
UPDATE brokerage_events AS be
SET transaction_id = u.transaction_id
FROM unique_pairs AS u
WHERE be.id = u.event_id
"""


def upgrade() -> None:
    op.add_column(
        "brokerage_events",
        sa.Column("transaction_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_brokerage_events_transaction_id",
        "brokerage_events",
        ["transaction_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_brokerage_events_transaction_id",
        "brokerage_events",
        "transactions",
        ["transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_constraint("fk_brokerage_events_transaction_id", "brokerage_events", type_="foreignkey")
    op.drop_index("ix_brokerage_events_transaction_id", table_name="brokerage_events")
    op.drop_column("brokerage_events", "transaction_id")
