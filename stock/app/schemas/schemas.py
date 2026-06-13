from pydantic import ConfigDict, BaseModel
from typing import Optional
import uuid

from app.models.base import InstrumentBase, MarketBase, QuoteLatestBase
from app.models.enums import InstrumentType, Currency


class MarketCreate(MarketBase):
    model_config = ConfigDict(from_attributes=False)


class InstrumentCreate(InstrumentBase):
    model_config = ConfigDict(from_attributes=False)
    market_id: uuid.UUID


class InstrumentManualCreate(InstrumentBase):
    model_config = ConfigDict(from_attributes=False)

    market_id: Optional[uuid.UUID] = None
    market_mic: Optional[str] = None
    currency: Optional[Currency] = None


class InstrumentRead(InstrumentBase):
    model_config = ConfigDict(from_attributes=True)

    market_id: uuid.UUID
    mic: str
    currency: Currency


class QuoteLatesInput(QuoteLatestBase):
    model_config = ConfigDict(from_attributes=False)


class QuoteLatesCreate(QuoteLatestBase):
    model_config = ConfigDict(from_attributes=False)

    instrument_id: uuid.UUID


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    mic: str
    name: str
    country: str
    timezone: str
    active: bool
    currency: Currency


class InstrumentOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    shortname: str


class QuoteSourceInstrumentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    symbol: str
    shortname: str
    quote_source: str
    mic: str


class InstrumentSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID

    isin: Optional[str]
    symbol: str
    shortname: str
    name: Optional[str]

    type: InstrumentType
    mic: str
