"""create cash holdings table

Revision ID: b6d8f0a2c4e6
Revises: a3c5e7f9b1d2
Create Date: 2026-10-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b6d8f0a2c4e6"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Physical cash may be held in any instrument currency, so the existing
    # instrument_currency_enum (PLN/USD/EUR/GBP/CHF) is reused, not recreated.
    instrument_currency_enum = postgresql.ENUM(
        "PLN", "USD", "EUR", "GBP", "CHF",
        name="instrument_currency_enum",
        create_type=False,
    )

    op.create_table(
        "cash_holdings",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("currency", instrument_currency_enum, nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_cash_holding_amount_nonneg"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_cash_holding_name_not_empty"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_holdings_wallet_id"), "cash_holdings", ["wallet_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cash_holdings_wallet_id"), table_name="cash_holdings")
    op.drop_table("cash_holdings")
