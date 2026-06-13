"""add brokerage conversions

Revision ID: f2b7c9d4e1a6
Revises: e0f4aa2c6d9b
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision: str = "f2b7c9d4e1a6"
down_revision: Union[str, None] = "e0f4aa2c6d9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'CONVERSION'")
    op.add_column(
        "brokerage_events",
        sa.Column("target_instrument_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_brokerage_events_target_instrument_id",
        "brokerage_events",
        ["target_instrument_id"],
    )
    op.create_foreign_key(
        "fk_brokerage_events_target_instrument_id",
        "brokerage_events",
        "instruments",
        ["target_instrument_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_brokerage_events_target_instrument_id", "brokerage_events", type_="foreignkey")
    op.drop_index("ix_brokerage_events_target_instrument_id", table_name="brokerage_events")
    op.drop_column("brokerage_events", "target_instrument_id")
