from pydantic import BaseModel, AnyUrl
from zoneinfo import ZoneInfo
from typing import Optional

from app.models.enums import InstrumentType


class TableLayout(BaseModel):
    min_cols: int

    symbol_col: int = 0
    name_col: int = 1
    price_col: int = 2
    change_pct_col: int = 3

    volume_col: Optional[int] = 5    
    time_col: int = 6    


class MarketConfig(BaseModel):
    id: str                    
    base_url: AnyUrl      
    start_path: str      
    mic: str   
    instrument_type: InstrumentType              
    row_selector: str = 'tr[id^="r_"]'
    help_selector: str = 'td a[href="pomoc/"]'
    time_zone: ZoneInfo = ZoneInfo("Europe/Warsaw")
    
    layout: TableLayout