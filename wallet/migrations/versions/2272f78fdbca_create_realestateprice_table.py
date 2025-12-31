"""Create realestatePrice table

Revision ID: 2272f78fdbca
Revises: b8938a94bf1e
Create Date: 2025-12-16 20:09:41.618278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2272f78fdbca'
down_revision: Union[str, None] = 'b8938a94bf1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    property_type_enum = postgresql.ENUM(
        "APARTMENT", "LAND", "HAUSE",
        name="propertyt_type_enum",
        create_type=False,
    )
    currency_enum = postgresql.ENUM(
        "PLN", "USD", "EUR",
        name="currency_enum",
        create_type=False,
    )

    # create only if missing
    property_type_enum.create(bind, checkfirst=True)
    currency_enum.create(bind, checkfirst=True)

    op.create_table(
        "real_estate_prices",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("type", property_type_enum, nullable=False),
        sa.Column("currency", currency_enum, nullable=False),
        sa.Column("avg_price_per_m2", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.CheckConstraint("avg_price_per_m2 >= 0", name="ck_re_price_m2_nonneg"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_re_price_lookup_latest",
        "real_estate_prices",
        ["type", "country", "city", "currency", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_real_estate_prices_city"), "real_estate_prices", ["city"], unique=False)
    op.create_index(op.f("ix_real_estate_prices_country"), "real_estate_prices", ["country"], unique=False)
    op.create_index(op.f("ix_real_estate_prices_currency"), "real_estate_prices", ["currency"], unique=False)
    op.create_index(op.f("ix_real_estate_prices_type"), "real_estate_prices", ["type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(op.f("ix_real_estate_prices_type"), table_name="real_estate_prices")
    op.drop_index(op.f("ix_real_estate_prices_currency"), table_name="real_estate_prices")
    op.drop_index(op.f("ix_real_estate_prices_country"), table_name="real_estate_prices")
    op.drop_index(op.f("ix_real_estate_prices_city"), table_name="real_estate_prices")
    op.drop_index("ix_re_price_lookup_latest", table_name="real_estate_prices")
    op.drop_table("real_estate_prices")

    property_type_enum = postgresql.ENUM(
        "APARTMENT", "LAND", "HAUSE",
        name="propertyt_type_enum",
        create_type=False,
    )
    currency_enum = postgresql.ENUM(
        "PLN", "USD", "EUR",
        name="currency_enum",
        create_type=False,
    )
    currency_enum.drop(bind, checkfirst=True)
    property_type_enum.drop(bind, checkfirst=True)
    # ### end Alembic commands ###
