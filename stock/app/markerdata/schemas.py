from pydantic import BaseModel, ConfigDict
from typing import Optional
from decimal import Decimal
from datetime import datetime


class IndexRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str
    name: str
    last_price: Optional[Decimal] = None
    change_pct: Optional[Decimal] = None  
    volume: Optional[int] = None
    last_trade_at: Optional[datetime] = None  
    href: Optional[str] = None              
    provider: str


class QuoteSourcePage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    symbol: str
    source_url: str
    last_price: Decimal
    change_pct: Decimal
    volume: Optional[int] = None
    last_trade_at: datetime
