from sqlmodel import Field, SQLModel, Boolean
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, Any
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql import func, text
from sqlalchemy.types import DateTime
from pydantic import ConfigDict, field_validator
from .enums import InstrumentType, InstrumentStatus, Currency, ReportAssetClass
from app.validators.validators import (
    Shortname, Shortname40, MICCode, ISINOpt, Name,
    g0int, datetimeUTC, Q2, Q3, NonEmptyStrUpperOpt, url_to_str
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
    shortname: Shortname40 = Field(
        sa_column=sa.Column(sa.String(40), nullable=False, unique=True),
        description="Short name of instument"
    )
    name: NonEmptyStrUpperOpt = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True),
        description="Full name of instrument"
    )
    currency: Optional[Currency] = Field(
        default=None,
        sa_column=sa.Column(sa.String(3), nullable=True, index=True),
        description="Quote currency for this instrument. Falls back only for legacy seeded instruments.",
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
    quote_source: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True, index=True),
        description="Full quote page URL used for manually managed instruments.",
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

    @field_validator("quote_source", mode="before")
    @classmethod
    def _val_quote(cls, v):
        return url_to_str(v)
    
    
class QuoteLatestBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)

    last_price: Q3 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 3), nullable=False, server_default="0"),
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

    open: Q3 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 3), nullable=False, server_default="0"),
        description="Price Open"
    )
    high: Q3 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 3), nullable=False, server_default="0"),
        description="Price High"
    )
    low: Q3 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 3), nullable=False, server_default="0"),
        description="Price Low"
    )
    close: Q3 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 3), nullable=False, server_default="0"),
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
    
    
class InstrumentSyncStateBase(SQLModel):

    daily_last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    daily_last_attempt_end: Optional[date] = Field(
        default=None,
        sa_column=sa.Column(sa.Date, nullable=True),
    )
    daily_last_success_at: Optional[datetime] = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    daily_last_success_end: Optional[date] = Field(
        default=None,
        sa_column=sa.Column(sa.Date, nullable=True),
    )

    daily_last_requested_url: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
    )
    
    daily_last_fetched_rows: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )
    daily_last_upserted_rows: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
    )

    daily_last_error: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Last error message from daily sync (if any).",
    )


class ReportAiSnapshotBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)

    asset_class: ReportAssetClass = Field(
        sa_column=sa.Column(sa.String(24), nullable=False, index=True),
        description="Asset class handled by the report schema, e.g. equity.",
    )
    period: str = Field(
        sa_column=sa.Column(sa.String(16), nullable=False, index=True),
        description="Quarterly period key, e.g. 2025-Q1.",
    )
    schema_version: int = Field(
        default=1,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="1"),
        description="Version of the stored AI schema.",
    )
    ai_payload: dict[str, Any] = Field(
        sa_column=sa.Column(pg.JSONB, nullable=False),
        description="Validated AI payload used to build the final report.",
    )
    model: str = Field(
        sa_column=sa.Column(sa.String(128), nullable=False),
        description="OpenAI model id used to generate the AI payload.",
    )
    prompt_version: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False),
        description="Prompt version identifier used for generation.",
    )
    prompt_hash: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False),
        description="Stable hash of the prompt body.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=func.now()),
        description="UTC timestamp when the AI payload was generated.",
    )
    valid_until: date = Field(
        sa_column=sa.Column(sa.Date, nullable=False),
        description="Date until which the AI payload is considered fresh.",
    )
    usage_prompt_tokens: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Prompt/input token count reported by OpenAI.",
    )
    usage_output_tokens: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Output token count reported by OpenAI.",
    )
    status: str = Field(
        default="ready",
        sa_column=sa.Column(sa.String(24), nullable=False, server_default="ready"),
        description="Generation status, e.g. ready or failed.",
    )
    last_error: Optional[str] = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Last generation error if the refresh failed.",
    )


class ReportSnapshotBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)

    asset_class: ReportAssetClass = Field(
        sa_column=sa.Column(sa.String(24), nullable=False, index=True),
        description="Asset class handled by the final report schema, e.g. equity.",
    )
    period: str = Field(
        sa_column=sa.Column(sa.String(16), nullable=False, index=True),
        description="Quarterly period key, e.g. 2025-Q1.",
    )
    schema_version: int = Field(
        default=1,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="1"),
        description="Version of the stored final report schema.",
    )
    final_payload: dict[str, Any] = Field(
        sa_column=sa.Column(pg.JSONB, nullable=False),
        description="Validated final report JSON returned to the UI.",
    )
    market_data_as_of: date = Field(
        sa_column=sa.Column(sa.Date, nullable=False, index=True),
        description="Freshness date for deterministic market data used in the report.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=func.now()),
        description="UTC timestamp when the final report payload was assembled.",
    )
    valid_until: date = Field(
        sa_column=sa.Column(sa.Date, nullable=False),
        description="Date until which the final snapshot is considered fresh.",
    )
