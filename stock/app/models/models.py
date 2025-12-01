import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from sqlmodel import Field, Relationship
from typing import Optional, List
import uuid
from .base import (
    InstrumentBase, TimestampMixin, UUIDMixin, QuoteLatestBase,
    CandleDailyBase, MarketBase
)


class Market(MarketBase, UUIDMixin, table=True):
    __tablename__ = "market"
    
    instruments: List["Instrument"] = Relationship(back_populates="market")


class Instrument(InstrumentBase, TimestampMixin, UUIDMixin, table=True):
    __tablename__ = "instrument"

    __table_args__ = (
        sa.UniqueConstraint("symbol", name="uq_instrument_symbol"),
        sa.Index("ix_dir_symbol_shortname", "symbol", "shortname"),
    )
    
    market_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("market.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    
    market: Optional["Market"] = Relationship(back_populates="instruments")
    
    candles_daily: List["CandleDaily"] = Relationship(
        back_populates="instrument",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    
    quote_latest: Optional["QuoteLatest"] = Relationship(
        back_populates="instrument",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False},
    )

    
class QuoteLatest(QuoteLatestBase, table=True):
    __tablename__ = "quote_latest"

    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    
    instrument: "Instrument" = Relationship(back_populates="quote_latest")

    
class CandleDaily(CandleDailyBase, table=True):
    __tablename__ = "candle_daily"

    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    
    instrument: "Instrument" = Relationship(back_populates="candles_daily")
    
    __table_args__ = (
        sa.Index("ix_cd_instr_date_quote", "instrument_id", "date_quote"),
    )
