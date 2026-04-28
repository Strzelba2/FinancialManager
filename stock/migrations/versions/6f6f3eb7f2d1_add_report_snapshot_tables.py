"""add report snapshot tables

Revision ID: 6f6f3eb7f2d1
Revises: e90a6a719b02
Create Date: 2026-04-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision: str = "6f6f3eb7f2d1"
down_revision: Union[str, Sequence[str], None] = "e90a6a719b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_ai_snapshot",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("asset_class", sa.String(length=24), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("ai_payload", pg.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("usage_prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_output_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="ready", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "asset_class",
            "period",
            "schema_version",
            name="uq_report_ai_snapshot_business_key",
        ),
    )
    op.create_index(
        "ix_report_ai_snapshot_lookup",
        "report_ai_snapshot",
        ["instrument_id", "asset_class", "period", "generated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_ai_snapshot_asset_class"),
        "report_ai_snapshot",
        ["asset_class"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_ai_snapshot_instrument_id"),
        "report_ai_snapshot",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_ai_snapshot_period"),
        "report_ai_snapshot",
        ["period"],
        unique=False,
    )

    op.create_table(
        "report_snapshot",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("asset_class", sa.String(length=24), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("final_payload", pg.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("market_data_as_of", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("ai_snapshot_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["ai_snapshot_id"], ["report_ai_snapshot.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "asset_class",
            "period",
            "schema_version",
            name="uq_report_snapshot_business_key",
        ),
    )
    op.create_index(
        "ix_report_snapshot_lookup",
        "report_snapshot",
        ["instrument_id", "asset_class", "period", "generated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_snapshot_ai_snapshot_id"),
        "report_snapshot",
        ["ai_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_snapshot_asset_class"),
        "report_snapshot",
        ["asset_class"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_snapshot_instrument_id"),
        "report_snapshot",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_snapshot_market_data_as_of"),
        "report_snapshot",
        ["market_data_as_of"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_snapshot_period"),
        "report_snapshot",
        ["period"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_report_snapshot_period"), table_name="report_snapshot")
    op.drop_index(op.f("ix_report_snapshot_market_data_as_of"), table_name="report_snapshot")
    op.drop_index(op.f("ix_report_snapshot_instrument_id"), table_name="report_snapshot")
    op.drop_index(op.f("ix_report_snapshot_asset_class"), table_name="report_snapshot")
    op.drop_index(op.f("ix_report_snapshot_ai_snapshot_id"), table_name="report_snapshot")
    op.drop_index("ix_report_snapshot_lookup", table_name="report_snapshot")
    op.drop_table("report_snapshot")

    op.drop_index(op.f("ix_report_ai_snapshot_period"), table_name="report_ai_snapshot")
    op.drop_index(op.f("ix_report_ai_snapshot_instrument_id"), table_name="report_ai_snapshot")
    op.drop_index(op.f("ix_report_ai_snapshot_asset_class"), table_name="report_ai_snapshot")
    op.drop_index("ix_report_ai_snapshot_lookup", table_name="report_ai_snapshot")
    op.drop_table("report_ai_snapshot")
