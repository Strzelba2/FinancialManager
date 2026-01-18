from typing import Optional, Dict, List
from pydantic import BaseModel, ConfigDict, field_serializer, RootModel, Field
from decimal import Decimal
from datetime import datetime, date
import uuid

from app.models.enums import Currency


class QuotePayloadOut(BaseModel):
    name: Optional[str] = None
    last_price: Optional[Decimal] = None
    change_pct: Optional[Decimal] = None
    volume: Optional[int] = None
    last_trade_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("last_price", "change_pct")
    def _decimal_as_str(self, v: Optional[Decimal], _info):
        return str(v) if v is not None else None

    @field_serializer("last_trade_at")
    def _dt_iso(self, v: Optional[datetime], _info):
        return v.isoformat(timespec="seconds") if v else None


class BulkQuotesOut(RootModel[Dict[str, QuotePayloadOut]]):
    pass


class LatestQuoteBySymbol(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    

class QuotesBySymbolsRequest(BaseModel):
    symbols: List[str] = Field(
        ..., min_length=1, description="Instrument symbols, e.g. PKN, AAPL"
    )
    
    
class SyncDailyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    instrument_id: uuid.UUID
    requested_url: str
    fetched_rows: int
    upserted_rows: int
    sync_start: Optional[date] = None
    sync_end: Optional[date] = None
    

class DailyRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    date_quote: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None
    

class CandleDailyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date_quote: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None
    trade_at: datetime


class SyncDailyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sync: SyncDailyResult
    items_included: bool
    returned_count: int
    items: Optional[List[CandleDailyOut]] = None
    
    
class SyncDailyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: Optional[date] = Field(default=None, alias="from")
    date_to: Optional[date] = Field(default=None, alias="to")

    return_all: bool = False
    overlap_days: int = Field(default=7, ge=0, le=60)

    include_items: bool = False
