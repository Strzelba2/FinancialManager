from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, ConfigDict
from decimal import Decimal
import uuid
from typing import Optional, List
from datetime import datetime, date
import json


from utils.money import parse_amount, dec, format_pl_amount
from utils.dates import to_pl_local_parts
from .wallet import Currency


class QuotePayload(BaseModel):
    name: Optional[str] = None
    last_price: Optional[Decimal] = Field(default=None)
    change_pct: Optional[Decimal] = Field(default=None)  
    volume: Optional[int] = Field(default=None)
    last_trade_at: Optional[datetime | str] = Field(default=None)

    @field_validator('last_price', mode='before')
    @classmethod
    def _coerce_last_price(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, Decimal, str)):
            pa = parse_amount(v)
            return pa if pa is not None else dec(v)
        return dec(v)

    @field_validator('change_pct', mode='before')
    @classmethod
    def _coerce_change_pct(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, Decimal, str)):
            pa = parse_amount(v)
            return pa if pa is not None else dec(v)
        return dec(v)

    @field_validator('volume', mode='before')
    @classmethod
    def _coerce_volume(cls, v):
        if v is None:
            return None
        try:
            return int(str(v).strip())
        except Exception:
            return None

    @field_validator('last_trade_at', mode='before')
    @classmethod
    def _coerce_last_trade_at(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        s = str(v).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        return s


class QuoteRow(BaseModel):
    symbol: str
    name: Optional[str] = None
    last_price: Decimal = Decimal("0")
    change_pct: Decimal = Decimal("0")
    volume: int = 0
    last_trade_at: Optional[str] = None 
    last_trade_at_fmt: Optional[str] = None 
    last_trade_date_fmt: Optional[str] = None    
    last_trade_time_fmt: Optional[str] = None
    last_price_fmt: str = "0,00"
    change_pct_fmt: str = "+0,00%"

    @classmethod
    def from_redis(cls, symbol: str, payload: str | dict) -> "QuoteRow":
        data = {}
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except Exception:
                data = {}
        elif isinstance(payload, dict):
            data = payload
        qp = QuotePayload(**data)

        last_price = dec(qp.last_price or 0)
        change_pct = dec(qp.change_pct or 0)
        volume = int(qp.volume or 0)

        iso, pretty, date_fmt, time_fmt = to_pl_local_parts(qp.last_trade_at)

        return cls(
            symbol=symbol,
            name=qp.name,
            last_price=last_price,
            change_pct=change_pct,
            volume=volume,
            last_trade_at=iso,               
            last_trade_at_fmt=pretty,   
            last_trade_date_fmt=date_fmt,
            last_trade_time_fmt=time_fmt,
            last_price_fmt=format_pl_amount(last_price, decimals=2),
            change_pct_fmt=f"{'+' if change_pct >= 0 else ''}{format_pl_amount(change_pct, decimals=2)}%"
                           .replace(" ", ""), 
        )
    
        
class Market(BaseModel):
    symbol: str
    name: Optional[str] = None
   
    
class QuoteBySymbolItem(BaseModel):
    symbol: str
    price: Decimal
    currency: Currency
    
    
class QuotesBySymbolsResponse(BaseModel):
    quotes: List[QuoteBySymbolItem] = Field(default_factory=list)
     

class SyncDailyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: Optional[date] = Field(default=None, alias="from")
    date_to: Optional[date] = Field(default=None, alias="to")

    return_all: bool = False
    overlap_days: int = Field(default=7, ge=0, le=60)

    include_items: bool = False
    
    
class CandleDailyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date_quote: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None
    trade_at: datetime
    

class SyncDailyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    instrument_id: uuid.UUID
    requested_url: str
    fetched_rows: int
    upserted_rows: int
    sync_start: Optional[date] = None
    sync_end: Optional[date] = None


class SyncDailyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sync: SyncDailyResult
    items_included: bool
    returned_count: int
    items: Optional[List[CandleDailyOut]] = None
