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
    

class BrokerageEventKind(StrEnum):
    BUY = 'BUY'
    SELL = 'SELL'
   
    
class CapitalGainKind(StrEnum):
    DEPOSIT_INTEREST = "Zysk z Odsetek"  
    BROKER_REALIZED_PNL = "Zysk z Sprzedaży"
    BROKER_DIVIDEND = "Dywidenda"  
    TRANSACTION = "Zwykła transakcja"
    
    
class AccountType(StrEnum):
    CURRENT = "Konto bankowe" 
    SAVINGS = "Konto Oszczędnościowe"  
    BROKERAGE = "Konto Maklerskie"
    CREDIT = "Karta kredytowa"
  
    
class Bank(BaseModel):
    id: uuid.UUID
    name: str
    shortname: str


class Transaction(BaseModel):
    amount: Decimal
    description: str
    balance_before: Decimal
    balance_after:  Decimal
    date_transaction: datetime 
    account_id: uuid.UUID

    
class TransactionRow(BaseModel):
    date_transaction: str
    amount: Decimal
    description: str
    balance_after: Decimal
    account_name: str | None = None
    currency: Currency | None = None

    
class AccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    bank_id: uuid.UUID
    account_type: str
    currency: Currency
    available: Optional[Decimal] = None    
    blocked: Optional[Decimal] = None
    last_transactions: List[Transaction]
    

class BrokerageAccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    

class WalletListItem(BaseModel):
    id: uuid.UUID
    name: str
    accounts: Optional[List[AccountListItem]] = Field(default_factory=list)
    brokerage_accounts: list[BrokerageAccountListItem] = Field(default_factory=list)
    
    
class WalletCreationResponse(WalletListItem):
    pass

 
class ClientWalletSyncResponse(BaseModel):
    first_name: str
    user_id: str
    wallets: Optional[List[WalletListItem]] = Field(default_factory=list)
    banks: Optional[List[Bank]] = Field(default_factory=list)


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
    capital_gain_kind: Optional[str] = None

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
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            parsed = parse_date(v)
            if parsed:
                return date.fromisoformat(parsed)
        raise ValueError(f'invalid date: {v!r}')
    
    
class BrokerageEventImportRow(BaseModel):
    trade_at: datetime
    instrument_symbol: str
    instrument_mic: str
    instrument_name: Optional[str] = None

    kind: BrokerageEventKind
    quantity: Decimal
    price: Decimal
    currency: Currency
    split_ratio: Decimal = 0


class BrokerageEventsImportRequest(BaseModel):
    brokerage_account_id: uuid.UUID
    events: List[BrokerageEventImportRow]

