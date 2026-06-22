from pydantic import BaseModel, Field, ConfigDict, field_serializer
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any
from .schemas import (
    AccountType, TransactionRead, HoldingRead,
    BrokerageEventRead, BrokerageEventUpdate, TransactionBatchUpdate, YearGoalRead,
    )
from app.models.enums import BrokerageEventKind, Currency, InstrumentCurrency, PropertyType, MetalType
import uuid


def _serialize_decimals(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_serialize_decimals(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_serialize_decimals(item) for item in value)
    if isinstance(value, dict):
        return {key: _serialize_decimals(item) for key, item in value.items()}
    return value


class DecimalResponseModel(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimal_fields(self, value: Any) -> Any:
        return _serialize_decimals(value)


class AccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    bank_id: uuid.UUID
    account_type: AccountType
    currency: Currency
    available: Optional[Decimal] = None    
    blocked: Optional[Decimal] = None
    last_transactions: List[TransactionRead] = []
 
    
class BrokerageAccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    totals_by_currency: Dict[InstrumentCurrency, Decimal] = Field(default_factory=dict)


class PositionPerformance(BaseModel):
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    price: Decimal
    currency: InstrumentCurrency
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
    ccy: InstrumentCurrency
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
    tax_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    capital_by_currency: Dict[Currency, Decimal] = Field(default_factory=dict)
    

class MonthlySeriesOut(BaseModel):
    months: List[str]            
    values: List[Optional[float]]  


class CpiMonthlyOut(BaseModel):
    months: List[str]
    index_by_month: Dict[str, float] 


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
    
    year_goal: Optional[YearGoalRead] = None
    
    dash_flow_8m: List[DashFlowMonthItem] = Field(default_factory=list)
    
    assets_8m: Optional[MonthlySeriesOut] = None
    

class LastFavoriteObservedItem(BaseModel):
    sym: str
    pl_pct: Decimal = Decimal("0")
    pl_abs: Decimal = Decimal("0")
    currency: InstrumentCurrency
    
    
class LastPriceAlertObservedItem(BaseModel):
    id: uuid.UUID
    sym: str

    enabled: bool = True
    one_shot: bool = False

    below_price: Optional[Decimal] = None
    above_price: Optional[Decimal] = None

    current_price: Optional[Decimal] = None
    currency: Optional[Currency] = None

    created_at: Optional[datetime] = None
    last_triggered: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class WalletUserResponse(BaseModel):
    first_name: str
    user_id: str
    wallets: Optional[List[WalletListItem]] = Field(default_factory=list)
    banks: Optional[List] = Field(default_factory=list)
    assets_8m_total: Optional[MonthlySeriesOut] = None
    cpi_8m: Optional[CpiMonthlyOut] = None
    
    last_favorite_items: List[LastFavoriteObservedItem] = Field(default_factory=list)
    last_price_alerts: list[LastPriceAlertObservedItem] = Field(default_factory=list)
    
    
class WalletResponse(WalletListItem):
    pass

    
class AccountCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    account_type: str
   
    
class BrokerageEventWithHoldingRead(BrokerageEventRead):
    holding: Optional[HoldingRead]
    

class BrokerageEventImportRowResult(BaseModel):
    row: int
    status: str
    message: Optional[str] = None
    brokerage_event_id: Optional[uuid.UUID] = None
    transaction_id: Optional[uuid.UUID] = None
    instrument_symbol: Optional[str] = None
    instrument_name: Optional[str] = None
    kind: Optional[BrokerageEventKind] = None
    trade_at: Optional[datetime] = None
    currency: Optional[Currency] = None
    quantity: Optional[Decimal] = None
    held_quantity: Optional[Decimal] = None
    missing_quantity: Optional[Decimal] = None
    reason_code: Optional[str] = None


class BrokerageEventsImportSummary(BaseModel):
    total: int = 0
    created: int
    cash_transactions_created: int = 0
    skipped_duplicates: int = 0
    needs_review: int = 0
    failed: int
    errors: list[str] = []
    rows: list[BrokerageEventImportRowResult] = []


class BrokerageCashLinkResult(BaseModel):
    currency: Currency
    deposit_account_id: uuid.UUID
    created: bool = False
    name: Optional[str] = None
 
    
class QuoteBySymbolItem(BaseModel):
    symbol: str
    price: Decimal
    currency: InstrumentCurrency
    change_pct: Decimal


class QuotesBySymbolsResponse(BaseModel):
    quotes: List[QuoteBySymbolItem] = Field(default_factory=list)
    
    
class TransactionRowOut(TransactionRead):
    account_name: str
    ccy: str  


class TransactionPageOut(BaseModel):
    items: List[TransactionRowOut]
    total: int
    page: int
    size: int
    sum_by_ccy: dict[str, Decimal] = {}


class TransactionPatchIn(TransactionBatchUpdate):
    id: uuid.UUID


class BatchUpdateTransactionsRequest(BaseModel):
    items: List[TransactionPatchIn] = Field(min_length=1)


class BatchUpdateError(BaseModel):
    id: uuid.UUID
    detail: str


class BatchUpdateTransactionsResponse(BaseModel):
    updated: int
    failed: List[BatchUpdateError] = []
    

class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    currency: str
    
    
class SellMetalIn(BaseModel):
    deposit_account_id: uuid.UUID
    grams_sold: Decimal
    proceeds_amount: Decimal
    proceeds_currency: str
    occurred_at: datetime | None = None
    create_transaction: bool = False


class SellRealEstateIn(BaseModel):
    deposit_account_id: uuid.UUID
    proceeds_amount: Decimal
    proceeds_currency: str
    occurred_at: datetime | None = None
    create_transaction: bool = False
    
    
class BrokerageEventRowOut(BrokerageEventRead):

    brokerage_account_id: uuid.UUID
    instrument_id: uuid.UUID

    brokerage_account_name: str
    instrument_symbol: str
    instrument_name: Optional[str] = None


class BrokerageEventPageOut(BaseModel):

    items: list[BrokerageEventRowOut]
    total: int
    page: int
    size: int
    sum_by_ccy: dict[str, Decimal] = {}   


class BrokerageEventPatch(BrokerageEventUpdate):
    id: uuid.UUID


class BatchUpdateBrokerageEventsRequest(BaseModel):
    items: list[BrokerageEventPatch] = Field(min_length=1)
    
    
class HoldingRowOut(HoldingRead):

    account_name: str

    instrument_symbol: str
    instrument_mic: str
    instrument_name: str
    instrument_currency: str 


class DepositSnapshotItem(DecimalResponseModel):
    ccy: str
    available: Decimal    
   
 
class WalletManagerDepositAccountOut(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    ccy: str
    available: Decimal
    tx_per_month: int = 0
    health: Dict[str, Any] = Field(default_factory=dict)
    snapshots: Dict[str, DepositSnapshotItem] = Field(default_factory=dict)   


class CashAccountOut(DecimalResponseModel):
    deposit_account_id: str
    name: str
    ccy: str
    available: Decimal


class PositionOut(DecimalResponseModel):
    symbol: str
    mic: str
    value: Decimal
    value_default_ccy: Decimal
    currency: str
    pnl_pct: Decimal
  
  
class BrokerageSnapshotItem(DecimalResponseModel):
    ccy: str
    cash: Decimal
    stocks: Decimal
      

class WalletManagerBrokerageAccountOut(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    ccy: str
    cash_account: CashAccountOut | None = None
    cash_accounts: List[CashAccountOut] = Field(default_factory=list)
    positions: List[PositionOut] = Field(default_factory=list)
    positions_count: int = 0
    positions_value: Decimal = Decimal("0")
    events_per_month: int = 0
    health: Dict[str, Any] = Field(default_factory=dict)
    snapshots: Dict[str, BrokerageSnapshotItem] = Field(default_factory=dict)
  
  
class MetalItems(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    name: str  
    quantity: Decimal
    qty_unit: str = "g"
    value: Decimal
    ccy: str
    
    
class RealEstateItems(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    name: str  
    city: str
    value: Decimal
    ccy: str   
    

class AssetSummaryMetalOut(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    count: int
    value: Decimal
    ccy: str
    items: List[MetalItems] = Field(default_factory=list)
    health: Dict[str, Any] = Field(default_factory=dict)
    

class AssetSummaryRealEstateOut(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    count: int
    value: Decimal
    ccy: str
    items: List[RealEstateItems] = Field(default_factory=list)
    health: Dict[str, Any] = Field(default_factory=dict)
  

class WalletSnapshotItem(DecimalResponseModel):
    ccy: str
    cash_deposit: Decimal
    cash_broker: Decimal
    stocks: Decimal
    metals: Decimal
    real_estate: Decimal
      
      
class WalletManagerWalletOut(DecimalResponseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    base_ccy: str
    health: Dict[str, Any] = Field(default_factory=dict)

    deposit_accounts: List[WalletManagerDepositAccountOut] = Field(default_factory=list)
    brokerage_accounts: List[WalletManagerBrokerageAccountOut] = Field(default_factory=list)

    metals: AssetSummaryMetalOut = Field(default_factory=lambda: AssetSummaryMetalOut(count=0, 
                                                                                      value=Decimal("0"), 
                                                                                      ccy="PLN", 
                                                                                      items=[], 
                                                                                      health={})
                                         )
    real_estate: AssetSummaryRealEstateOut = Field(default_factory=lambda: AssetSummaryRealEstateOut(count=0, 
                                                                                                     value=Decimal("0"), 
                                                                                                     ccy="PLN", 
                                                                                                     items=[],
                                                                                                     health={}))

    snapshots: Dict[str, WalletSnapshotItem] = Field(default_factory=dict)

    fx_by_month: Dict[str, Dict[str, Decimal]] = Field(default_factory=dict)
    
    
class CreateMonthlySnapshotIn(BaseModel):
    month_key: Optional[str] = None
    currency_rate: Dict[str, Decimal]  
    
    
class WalletManagerTreeIn(BaseModel):
    months: int = Field(default=2, ge=1, le=24)
    currency_rate: dict[str, Decimal] = Field(default_factory=dict)


class CreateMonthlySnapshotOut(BaseModel):
    ok: bool
    month_key: str
    fx_saved: bool
    dep_upserted: int
    bro_upserted: int
    metal_upserted: int
    re_upserted: int
    
    
class WalletRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class WalletOut(BaseModel):
    id: uuid.UUID
    name: str
    

class SyncDailyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: Optional[date] = Field(default=None, alias="from")
    date_to: Optional[date] = Field(default=None, alias="to")

    return_all: bool = False
    overlap_days: int = Field(default=7, ge=0, le=60)

    include_items: bool = False
    
    
class CandleDailyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date_quote: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None
    trade_at: datetime
    

class SyncDailyResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    instrument_id: uuid.UUID
    requested_url: str
    fetched_rows: int
    upserted_rows: int
    sync_start: Optional[date] = None
    sync_end: Optional[date] = None


class SyncDailyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sync: SyncDailyResult
    items_included: bool
    returned_count: int
    items: Optional[List[CandleDailyOut]] = None
    
    
class StockInstrumentRead(BaseModel):
    """Instrument payload returned from stock-service resolve endpoint."""
    model_config = ConfigDict(from_attributes=True)

    mic: str
    symbol: str
    shortname: str
    name: Optional[str] = None

    currency: str
    type: str
    status: str


class InstrumentNameSyncResponse(BaseModel):
    symbol: str
    mic: str
    name: str
    created: bool
