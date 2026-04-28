import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from sqlmodel import Field, Relationship
from typing import Optional, List
import uuid
from .base import (
    InstrumentBase, TimestampMixin, UUIDMixin, QuoteLatestBase,
    CandleDailyBase, MarketBase, InstrumentSyncStateBase,
    ReportAiSnapshotBase, ReportSnapshotBase,
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
 
    
class InstrumentSyncState(InstrumentSyncStateBase, table=True):
    __tablename__ = "instrument_sync_state"

    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )


class ReportAiSnapshot(ReportAiSnapshotBase, TimestampMixin, UUIDMixin, table=True):
    __tablename__ = "report_ai_snapshot"

    __table_args__ = (
        sa.UniqueConstraint(
            "instrument_id",
            "asset_class",
            "period",
            "schema_version",
            name="uq_report_ai_snapshot_business_key",
        ),
        sa.Index(
            "ix_report_ai_snapshot_lookup",
            "instrument_id",
            "asset_class",
            "period",
            "generated_at",
        ),
    )

    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    instrument: Optional["Instrument"] = Relationship()


class ReportSnapshot(ReportSnapshotBase, TimestampMixin, UUIDMixin, table=True):
    __tablename__ = "report_snapshot"

    __table_args__ = (
        sa.UniqueConstraint(
            "instrument_id",
            "asset_class",
            "period",
            "schema_version",
            name="uq_report_snapshot_business_key",
        ),
        sa.Index(
            "ix_report_snapshot_lookup",
            "instrument_id",
            "asset_class",
            "period",
            "generated_at",
        ),
    )

    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instrument.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    ai_snapshot_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_ai_snapshot.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )

    instrument: Optional["Instrument"] = Relationship()
    ai_snapshot: Optional["ReportAiSnapshot"] = Relationship()
