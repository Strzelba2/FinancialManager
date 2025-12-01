from pydantic import BaseModel, AnyUrl
from zoneinfo import ZoneInfo

from app.models.enums import InstrumentType


class MarketConfig(BaseModel):
    id: str                    
    base_url: AnyUrl      
    start_path: str      
    mic: str   
    instrument_type: InstrumentType              
    row_selector: str = 'tr[id^="r_"]'
    help_selector: str = 'td a[href="pomoc/"]'
    time_zone: ZoneInfo = ZoneInfo("Europe/Warsaw")