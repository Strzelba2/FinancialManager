"""create cash holding monthly snapshots

Revision ID: c8e0a2b4d6f8
Revises: b6d8f0a2c4e6
Create Date: 2026-10-04 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c8e0a2b4d6f8"
down_revision: Union[str, Sequence[str], None] = "b6d8f0a2c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshot values keep the original cash currency (PLN/USD/EUR/GBP/CHF) and are
    # converted with the FX table of the same month when read.
    instrument_currency_enum = postgresql.ENUM(
        "PLN", "USD", "EUR", "GBP", "CHF",
        name="instrument_currency_enum",
        create_type=False,
    )

    op.create_table(
        "cash_holding_monthly_snapshots",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("currency", instrument_currency_enum, nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=2), server_default="0", nullable=False),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("cash_holding_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cash_holding_id"], ["cash_holdings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cash_holding_id", "month_key", name="uq_cash_monthly_snapshot"),
    )
    op.create_index(
        op.f("ix_cash_holding_monthly_snapshots_month_key"),
        "cash_holding_monthly_snapshots",
        ["month_key"],
    )
    op.create_index(
        op.f("ix_cash_holding_monthly_snapshots_wallet_id"),
        "cash_holding_monthly_snapshots",
        ["wallet_id"],
    )
    op.create_index(
        op.f("ix_cash_holding_monthly_snapshots_cash_holding_id"),
        "cash_holding_monthly_snapshots",
        ["cash_holding_id"],
    )
    op.create_index("ix_cash_wallet_month", "cash_holding_monthly_snapshots", ["wallet_id", "month_key"])


def downgrade() -> None:
    op.drop_index("ix_cash_wallet_month", table_name="cash_holding_monthly_snapshots")
    op.drop_index(op.f("ix_cash_holding_monthly_snapshots_cash_holding_id"), table_name="cash_holding_monthly_snapshots")
    op.drop_index(op.f("ix_cash_holding_monthly_snapshots_wallet_id"), table_name="cash_holding_monthly_snapshots")
    op.drop_index(op.f("ix_cash_holding_monthly_snapshots_month_key"), table_name="cash_holding_monthly_snapshots")
    op.drop_table("cash_holding_monthly_snapshots")
