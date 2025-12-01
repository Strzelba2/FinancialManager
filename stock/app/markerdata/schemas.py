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
