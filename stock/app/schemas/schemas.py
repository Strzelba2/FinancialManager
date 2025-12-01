from pydantic import ConfigDict, BaseModel
from typing import Optional
import uuid

from app.models.base import InstrumentBase, QuoteLatestBase
from app.models.enums import InstrumentType


class InstrumentCreate(InstrumentBase):
    model_config = ConfigDict(from_attributes=False)
    market_id: uuid.UUID
    

class QuoteLatesInput(QuoteLatestBase):
    model_config = ConfigDict(from_attributes=False)
    

class QuoteLatesCreate(QuoteLatestBase):
    model_config = ConfigDict(from_attributes=False)
    
    instrument_id: uuid.UUID
    
    
class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    mic: str
    name: str
    

class InstrumentOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    shortname: str    
    
    
class InstrumentSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID

    isin: Optional[str]   
    symbol: str    
    shortname: str      
    name: Optional[str]   

    type: InstrumentType   
    mic: str 
    
    


    
