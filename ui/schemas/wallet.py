from typing import Optional, List
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict
from enum import StrEnum
from utils.utils import parse_date
import uuid


class Currency(StrEnum):
    PLN = "PLN"
    USD = "USD"
    EUR = "EUR"
    
    
class AccountType(StrEnum):
    CURRENT = "Konto bankowe" 
    SAVINGS = "Konto Oszczędnościowe"  
    BROKERAGE = "Konto Maklerskie"
    CREDIT = "Karta kredytowa"
    
    
class AccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    account_type: str
    currency: Currency
    available: Optional[Decimal] = None    
    blocked: Optional[Decimal] = None


class WalletListItem(BaseModel):
    id: uuid.UUID
    name: str
    accounts: Optional[List[AccountListItem]] = Field(default_factory=list)
    
    
class WalletCreationResponse(WalletListItem):
    pass


class ClientWalletSyncResponse(BaseModel):
    first_name: str
    user_id: str
    wallets: Optional[List[WalletListItem]] = Field(default_factory=list)
    banks: Optional[List] = Field(default_factory=list)


class AccountCreationResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    name: Optional[str] = None
   
    
class TransactionCreationRow(BaseModel):
    """Row parsed from CSV with strict-ish validation and normalization.
    - `type` is normalized to upper-case and limited to allowed values.
    - `amount` accepts EU formats (comma decimal) and coerces to Decimal(2dp).
    """
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    date: date
    amount: Decimal
    description: str
    amount_after: Decimal

    @field_validator('amount', mode='before')
    @classmethod
    def _parse_amount(cls, v: str | float | int) -> Decimal:
        s = v
        if isinstance(v, (int, float)):
            s = str(v)
        if isinstance(v, str):
            s = v.strip().replace(' ', '')
            if s.count(',') == 1 and s.count('.') == 0:
                s = s.replace(',', '.')
        try:
            return Decimal(str(s)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f'Invalid amount: {v!r}') from e
        
    @field_validator('date', mode='before')
    @classmethod
    def _coerce_date(cls, v):
        # accept datetime/date/str and normalize to date
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # your parse_date_iso from earlier:
            parsed = parse_date(v)
            if parsed:
                return date.fromisoformat(parsed)
        raise ValueError(f'invalid date: {v!r}')

