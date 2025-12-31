from typing import Optional, List, Dict
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
    SPLIT = "SPLIT"
    DIV = "DIV"
   
    
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
 
    
class PropertyType(StrEnum):
    APARTMENT = "APARTMENT",
    LAND = "LAND",
    HAUSE = "HAUSE"
  
    
class MetalType(StrEnum):
    GOLD = "GOLD"
    SILVER = "SILVER"
    PLATINUM = "PLATINUM"
    PALLADIUM = "PALLADIUM"

 
class Bank(BaseModel):
    id: uuid.UUID
    name: str
    shortname: str


class Transaction(BaseModel):
    id: uuid.UUID
    amount: Decimal
    description: str
    balance_before: Decimal
    balance_after:  Decimal
    date_transaction: datetime 
    account_id: uuid.UUID
    category: Optional[str]
    status: Optional[str]
    
    
class TransactionRowOut(Transaction):
    account_name: str
    ccy: str  


class TransactionPageOut(BaseModel):
    items: List[TransactionRowOut]
    total: int
    page: int
    size: int
    sum_by_ccy: dict[str, Decimal] = {}
    
    
class TransactionUpdate(BaseModel):
    
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    category: Optional[str] = None
    status: Optional[str] = None
    
    
class TransactionPatchIn(TransactionUpdate):
    id: str


class BatchUpdateTransactionsRequest(BaseModel):
    items: List[TransactionPatchIn] = Field(min_length=1)


class BatchUpdateError(BaseModel):
    id: uuid.UUID
    detail: str


class BatchUpdateTransactionsResponse(BaseModel):
    updated: int
    failed: List[BatchUpdateError] = []

    
class TransactionRow(BaseModel):
    date_transaction: str
    amount: Decimal
    description: str
    balance_after: Decimal
    account_name: Optional[str] = None
    currency: Optional[Currency] = None
    category: Optional[str] = None
    status: Optional[str] = None
    
    
class YearGoalOut(BaseModel):
    id: uuid.UUID
    wallet_id: uuid.UUID
    year: int
    rev_target_year: Decimal
    exp_budget_year: Decimal
    currency: Currency

    
class AccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    bank_id: uuid.UUID
    account_type: str
    currency: Currency
    available: Optional[Decimal] = None    
    blocked: Optional[Decimal] = None
    last_transactions: List[Transaction]
    
    
class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    currency: str
    

class BrokerageAccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    totals_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    

class PositionPerformance(BaseModel):
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    price: Decimal
    currency: Currency
    value: Decimal   
    cost: Decimal    
    pnl_amount: Decimal   
    pnl_pct: Decimal  
   
    
class BrokerageEventListItem(BaseModel):
    date: datetime 
    sym: str          
    type: BrokerageEventKind  
    qty: Decimal
    price: Decimal
    value: Optional[Decimal] = None   
    ccy: Currency
    account: str
    
    
class RealEstateItem(BaseModel):
    id: uuid.UUID
    name: str
    country: Optional[str] = None
    city: Optional[str] = None
    type: PropertyType
    area_m2: Optional[Decimal] = None
    purchase_price: Decimal
    purchase_currency: Optional[Currency] = None
    price: Optional[Decimal] = None


class MetalHoldingItem(BaseModel):
    id: uuid.UUID
    metal: MetalType
    grams: Decimal
    cost_basis: Decimal
    cost_currency: Optional[Currency] = None
    price: Optional[Decimal] = None     
    price_currency: Optional[Currency] = None
    

class DebtItem(BaseModel):
    id: uuid.UUID
    name: str
    lander: str
    amount: Decimal
    currency: Currency
    interest_rate_pct: Decimal
    monthly_payment: Decimal
    end_date: datetime 
    
    
class RecurringExpenseItem(BaseModel):
    id: uuid.UUID
    name: str
    category: Optional[str] = None
    amount: Decimal
    currency: Currency
    due_day: int
    account: Optional[str] = None
    note: Optional[str] = None
    
    
class DashFlowMonthItem(BaseModel):
    month: str  
    income_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    expense_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    capital_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    

class WalletListItem(BaseModel):
    id: uuid.UUID
    name: str
    accounts: Optional[List[AccountListItem]] = Field(default_factory=list)
    brokerage_accounts: list[BrokerageAccountListItem] = Field(default_factory=list)
    
    last_brokerage_events: List[BrokerageEventListItem] = Field(default_factory=list)
    top_losers: List[PositionPerformance] = Field(default_factory=list)
    top_gainers: List[PositionPerformance] = Field(default_factory=list)
    
    capital_gains_deposit_ytd: Dict[Currency, Decimal] = Field(default_factory=dict)
    capital_gains_broker_ytd: Dict[Currency, Decimal] = Field(default_factory=dict)
    capital_gains_real_estate_ytd: Dict[Currency, Decimal] = Field(default_factory=dict)
    capital_gains_metal_ytd: Dict[Currency, Decimal] = Field(default_factory=dict)
    
    real_estates: List[RealEstateItem] = Field(default_factory=list)
    metal_holdings: List[MetalHoldingItem] = Field(default_factory=list)
    
    debts: List[DebtItem] = Field(default_factory=list)
    
    recurring_expenses_top: List[RecurringExpenseItem] = Field(default_factory=list)
    
    income_ytd_by_currency: Dict[Currency, Decimal] = {}
    expense_ytd_by_currency: Dict[Currency, Decimal] = {}
    
    year_goal: Optional[YearGoalOut] = None
    
    dash_flow_8m: List[DashFlowMonthItem] = Field(default_factory=list)
    
    
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
    category: Optional[str] = None
    status: Optional[str] = None
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


class RealEstateOut(BaseModel):
    id: uuid.UUID
    wallet_id: uuid.UUID
    name: str
    country: Optional[str] = None
    city: Optional[str] = None
    type: PropertyType
    area_m2: Optional[Decimal] = None
    purchase_price: Decimal
    purchase_currency: Optional[Currency] = None
    
    
class RealEstatePriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    country: Optional[str] = None
    city: Optional[str] = None
    type: PropertyType
    currency: Currency
    avg_price_per_m2: Decimal
    

class MetalHoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wallet_id: uuid.UUID
    metal: MetalType
    grams: Decimal
    cost_basis: Decimal
    cost_currency: Optional[Currency] = None
    quote_symbol: Optional[str] = None    
    
    
class DebtOut (BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    wallet_id: uuid.UUID
    name: str
    lander: str 
    amount: Decimal
    currency: Currency 
    interest_rate_pct: Decimal
    monthly_payment: Decimal
    end_date: datetime 


class RecurringExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    wallet_id: uuid.UUID
    name: str
    category: str
    amount: Decimal
    currency: Currency 
    due_day: int
    account: Optional[str] 
    note: Optional[str]
    
    
class UserNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    text: str
    
    
class SellMetalRequest(BaseModel):
    deposit_account_id: uuid.UUID
    grams_sold: Decimal
    proceeds_amount: Decimal
    proceeds_currency: str
    occurred_at: Optional[datetime] = None
    create_transaction: bool = False


class SellRealEstateRequest(BaseModel):
    deposit_account_id: uuid.UUID
    proceeds_amount: Decimal
    proceeds_currency: str
    occurred_at: Optional[datetime] = None
    create_transaction: bool = False
    
    
class BrokerageEventRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brokerage_account_id: uuid.UUID
    instrument_id: uuid.UUID

    brokerage_account_name: str
    instrument_symbol: str
    instrument_name: Optional[str] = None

    kind: str                 
    quantity: Decimal
    price: Decimal
    currency: str            
    split_ratio: Decimal
    trade_at: datetime


class BrokerageEventPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BrokerageEventRowOut]
    total: int
    page: int
    size: int
    sum_by_ccy: dict[str, Decimal] = {}    


class BrokerageEventPatch(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    kind: Optional[str] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    split_ratio: Optional[Decimal] = None


class BatchUpdateBrokerageEventsRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    items: list[BrokerageEventPatch] = Field(min_length=1)
    
    
class HoldingRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_name: str

    instrument_id: uuid.UUID
    instrument_symbol: str
    instrument_name: str
    instrument_currency: str 

    quantity: Decimal
    avg_cost: Decimal
    
    

