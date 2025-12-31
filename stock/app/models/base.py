from sqlmodel import Field, SQLModel, Boolean
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql import func, text
from sqlalchemy.types import DateTime
from pydantic import ConfigDict, field_validator
from .enums import InstrumentType, InstrumentStatus, Currency
from app.validators.validators import (
    Shortname, MICCode, ISINOpt, Name,
    g0int, datetimeUTC, Q2, NonEmptyStrUpperOpt, url_to_str
)


class UUIDMixin(SQLModel, table=False):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=pg.UUID(as_uuid=True),   
        sa_column_kwargs={"server_default": text("gen_random_uuid()")}
    )


class TimestampMixin(SQLModel, table=False):
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),   
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),         
            "nullable": False,
        },
    )
  
    
class MarketBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    mic: MICCode = Field(
        sa_column=sa.Column(sa.String(4), index=True, nullable=False, unique=True),
        description="MIC: 4 uppercase alphanumeric (ISO 10383 operating MICs like XWAR, XLON, XNAS)"
    )
    name: Name = Field(
        sa_column=sa.Column(sa.String(50), nullable=False, unique=True),
        description="market name"
    )
    country: Shortname = Field(
        sa_column=sa.Column(sa.String(12), nullable=False),
        description="country"
    )
    timezone: Name = Field(
        sa_column=sa.Column(sa.String(50), nullable=False),
        description="market timezonet"
    )
    active: bool = Field(
        default=True,
        sa_column=sa.Column(Boolean, nullable=False, server_default="1"),
        description="if market is activated"
    )
    currency: Currency = Field( 
        sa_column=sa.Column(sa.String(3), nullable=False, index=True),
        description="ISO currency code for instruments traded on this market (e.g. PLN, USD).",
    )
    
    
class InstrumentBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    isin: ISINOpt = Field(
        default=None,
        sa_column=sa.Column(sa.String(12), index=True, nullable=True),
        description="ISIN (optional): None allowed; otherwise full ISO-6166 validation."
    ) 
    
    symbol: Shortname = Field(
        sa_column=sa.Column(sa.String(12), nullable=False, unique=True),
        description="instrument symbol"
    )
    shortname: Shortname = Field(
        sa_column=sa.Column(sa.String(12), nullable=False, unique=True),
        description="Short name of instument"
    )
    name: NonEmptyStrUpperOpt = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True),
        description="Full name of instrument"
    )
    type: InstrumentType = Field(
        sa_column=sa.Column(sa.Enum(InstrumentType, name="instrument_type_enum"), nullable=False),
        description="Instument type (e.g., ETF, STOCK, BOND)."
    )  

    status: InstrumentStatus = Field(
        sa_column=sa.Column(sa.Enum(InstrumentStatus, name="instrument_status_enum"), nullable=False),
        description="Instument status (e.g., ACTIVE, INACTIVE)."
    ) 
    historical_source: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True, index=True),
        description="href Data source/provider tag"
    )
    popularity: g0int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, index=True, nullable=False, server_default="0"),
        description="index search frequency"
    )
    last_seen_at: datetimeUTC = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
        description="date of last visit"
    )
    
    @field_validator("historical_source", mode="before")
    @classmethod
    def _val_hist(cls, v):
        return url_to_str(v)
    
    
class QuoteLatestBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)

    last_price: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Last traded price"
    )
    change_pct: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(10, 2), nullable=False, server_default="0"),
        description="Percent change (e.g., 0.0123 for +1.23%)"
    )

    volume: g0int | None = Field(
        default=None,
        sa_column=sa.Column(sa.BigInteger, nullable=True),
    )

    last_trade_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
        description="Timestamp of last trade (UTC)"
    )
    provider: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True, index=True),
        description="Data source/provider tag"
    )
    href: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(64), nullable=True, index=True),
        description="href Data source/provider tag"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True),
                            nullable=False,
                            server_default=func.now(),
                            onupdate=func.now()),
    )
    
    @field_validator("provider", mode="before")
    @classmethod
    def _val_url(cls, v):
        return url_to_str(v)
    
    
class CandleDailyBase(SQLModel):

    date_quote: date = Field(
        sa_column=sa.Column(sa.Date, primary_key=True, index=True),
        description="Session date (UTC calendar)"
    )

    open: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Price Open"
    )
    high: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Price High"
    )
    low: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Price Low"
    )
    close: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Price Close"
    )

    volume: g0int | None = Field(
        default=None,
        sa_column=sa.Column(sa.BigInteger, nullable=True),
    )
    
    trade_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
        description="Timestamp of last trade (UTC)"
    )
