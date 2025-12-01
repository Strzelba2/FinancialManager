from typing import Optional, Dict
from pydantic import BaseModel, ConfigDict, field_serializer, RootModel
from decimal import Decimal
from datetime import datetime


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
