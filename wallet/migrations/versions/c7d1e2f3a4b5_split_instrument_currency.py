"""split instrument/trade currency from base currency

Introduces a dedicated Postgres enum ``instrument_currency_enum``
(PLN/USD/EUR/GBP/CHF) for the instrument/quote/trade currency, and migrates the
two trade-currency columns (``instruments.currency`` and
``brokerage_events.currency``) onto it. The base ``currency_enum`` (PLN/USD/EUR)
stays for accounts, capital gains, snapshots and all other reporting columns.

Revision ID: c7d1e2f3a4b5
Revises: 8c4a9f2b1d30
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "8c4a9f2b1d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


instrument_currency_enum = postgresql.ENUM(
    "PLN", "USD", "EUR", "GBP", "CHF",
    name="instrument_currency_enum",
    create_type=False,
)
base_currency_enum = postgresql.ENUM(
    "PLN", "USD", "EUR",
    name="currency_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    instrument_currency_enum.create(bind, checkfirst=True)

    op.execute(
        "ALTER TABLE instruments "
        "ALTER COLUMN currency TYPE instrument_currency_enum "
        "USING currency::text::instrument_currency_enum"
    )
    op.execute(
        "ALTER TABLE brokerage_events "
        "ALTER COLUMN currency TYPE instrument_currency_enum "
        "USING currency::text::instrument_currency_enum"
    )


def downgrade() -> None:
    bind = op.get_bind()
    base_currency_enum.create(bind, checkfirst=True)

    op.execute(
        "ALTER TABLE brokerage_events "
        "ALTER COLUMN currency TYPE currency_enum "
        "USING currency::text::currency_enum"
    )
    op.execute(
        "ALTER TABLE instruments "
        "ALTER COLUMN currency TYPE currency_enum "
        "USING currency::text::currency_enum"
    )

    instrument_currency_enum.drop(bind, checkfirst=True)
