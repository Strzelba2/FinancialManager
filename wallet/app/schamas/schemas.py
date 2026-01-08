from sqlmodel import SQLModel, Field
from pydantic import ConfigDict, BaseModel
from typing import Optional, Annotated, List
from datetime import datetime
import uuid

from app.models.base import (UserBase, UUIDMixin, TimestampMixin, PartialUpdateMixin,  BankBase,
                             AccountBase, BrokerageAccountBase, DepositAccountBalanceBase,
                             InstrumentBase, HoldingBase, TransactionBase, RealEstateBase, 
                             MetalHoldingBase, WalletBase, BrokerageDepositLinkBase,
                             BrokerageEventBase, CapitalGainBase, RealEstatePriceBase,
                             DebtBase, RecurringExpenseBase, UserNoteBase, YearGoalBase,
                             DepositAccountMonthlySnapshotBase, BrokerageAccountMonthlySnapshotBase,
                             MetalHoldingMonthlySnapshotBase, RealEstateMonthlySnapshotBase)

from app.validators.validators import (
    Username12, EmailLower, FirstNameOpt, NonEmptyStr, Shortname, BICOpt, Q2OptNonNeg,
    Q2,  Q6Pos, AreaQ2OptPos, CountryISO2Opt, CityOpt, NoneIfEmpty, IBANOpt
)

from app.models.enums import (
    AccountType, Currency, InstrumentType,  MetalType,
    PropertyType, CapitalGainKind, BrokerageEventKind
    )


class UserCreate(UserBase):
    model_config = ConfigDict(from_attributes=False)


class UserRead(UserBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    
class UserUpdate(SQLModel):
    model_config = ConfigDict(from_attributes=False)
    
    username: Optional[Username12] = None
    email: Optional[EmailLower] = None
    first_name: FirstNameOpt = None
    
    __update_require_any__ = {"username", "email", "first_name"}
    
    
class BankCreate(BankBase):
    model_config = ConfigDict(from_attributes=False)   
    
    
class BankRead(BankBase, UUIDMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    
class BankUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    shortname: Optional[Shortname] = None
    bic: BICOpt = None 

    __update_require_any__ = {"name", "shortname", "bic"}
    
    
class DepositAccountCreate(AccountBase):
    model_config = ConfigDict(from_attributes=False)

    wallet_id: uuid.UUID
    bank_id: uuid.UUID
   
    
class AccountCreation (SQLModel):
    model_config = ConfigDict(from_attributes=False)
    
    name: str
    account_type: AccountType 
    currency: Currency
    account_number: str
    bank_id: uuid.UUID
    iban: IBANOpt = None


class DepositAccountRead(AccountBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    wallet_id: uuid.UUID
    bank_id: uuid.UUID
    
    
class DepositAccountUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    account_type: Optional[AccountType] = None
    currency: Optional[Currency] = None
    
    __update_require_any__ = {"name", "account_type", "currency"}
    
    
class BrokerageAccountCreate(BrokerageAccountBase):
    model_config = ConfigDict(from_attributes=False)
    
    wallet_id: uuid.UUID
    bank_id: uuid.UUID
    
    
class BrokerageAccountRead(BrokerageAccountBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    wallet_id: uuid.UUID
    bank_id: uuid.UUID
    
    
class BrokerageAccountUpdate(PartialUpdateMixin):
    
    name: Optional[NonEmptyStr] = None
    bank_id: Optional[uuid.UUID] = None
    
    __update_require_any__ = {"name", "bank_id"}
    

class BrokerageEventCreate(BrokerageEventBase):
    model_config = ConfigDict(from_attributes=False)
    
    brokerage_account_id: uuid.UUID
    instrument_symbol: str
    instrument_mic: str  

    instrument_name: str 
 
    
class BrokerageEventImportRow(BrokerageEventBase):
    model_config = ConfigDict(from_attributes=False)
    
    instrument_symbol: str
    instrument_mic: str
    instrument_name: Optional[str] = None


class BrokerageEventsImportRequest(BaseModel):

    brokerage_account_id: uuid.UUID
    events: List[BrokerageEventImportRow]
 
    
class CapitalGainCreate(CapitalGainBase):
    model_config = ConfigDict(from_attributes=False)
    
    deposit_account_id: uuid.UUID
    transaction_id: uuid.UUID
    

class BrokerageEventRead(BrokerageEventBase, UUIDMixin):
    model_config = ConfigDict(from_attributes=False)
    
    brokerage_account_id: uuid.UUID
    instrument_id: uuid.UUID
   
    
class BrokerageEventUpdate(PartialUpdateMixin):
    
    kind: Optional[BrokerageEventKind] = None
    quantity: Optional[Q2] = None
    price: Optional[Q2] = None
    currency: Optional[Currency] = None
    split_ratio: Optional[Q2] = None
    trade_at: Optional[datetime] = None  
    
    __update_require_any__ = {"kind", "quantity", "price", "currency", "split_ratio", "trade_at"}
    
    
class BrokerageDepositLinkCreate(BrokerageDepositLinkBase):
    model_config = ConfigDict(from_attributes=False)

    brokerage_account_id: uuid.UUID
    deposit_account_id: uuid.UUID
    
    
class BrokerageDepositLinkRead(BrokerageDepositLinkBase):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    brokerage_account_id: uuid.UUID
    deposit_account_id: uuid.UUID
    
    
class BrokerageDepositLinkUpdate(PartialUpdateMixin):

    currency: Optional[Currency] = None
    deposit_account_id: Optional[uuid.UUID] = None

    __update_require_any__ = {"currency", "deposit_account_id"}
    
    
class DepositAccountBalanceCreate(DepositAccountBalanceBase):

    model_config = ConfigDict(from_attributes=False)

    account_id: uuid.UUID
    
    
class DepositAccountBalanceRead(DepositAccountBalanceBase, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False) 
    
    account_id: uuid.UUID
    
    
class HoldingCreate(HoldingBase):
    model_config = ConfigDict(from_attributes=False)

    account_id: uuid.UUID
    instrument_id: uuid.UUID
    
    
class HoldingRead(HoldingBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    account_id: uuid.UUID
    instrument_id: uuid.UUID
    
    
class HoldingUpdate(PartialUpdateMixin):

    quantity: Q2OptNonNeg = None
    avg_cost: Q2OptNonNeg = None
    
    __update_require_any__ = {"quantity", "avg_cost"}
    
    
class InstrumentCreate(InstrumentBase):
    model_config = ConfigDict(from_attributes=False)
    
    sync_at: Optional[datetime] = None
    
    
class InstrumentRead(InstrumentBase, UUIDMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    
class InstrumentUpdate(PartialUpdateMixin):

    symbol: Optional[Shortname] = None
    name:   Optional[NonEmptyStr] = None
    type:   Optional[InstrumentType] = None
    currency: Optional[Currency] = None
    sync_at: Optional[datetime] = None
    
    __update_require_any__ = {"symbol", "name", "type", "currency", "sync_at"}
    
    
class TransactionCreate(TransactionBase):
    model_config = ConfigDict(from_attributes=False)
    
    account_id: uuid.UUID
   
    
class TransactionIn(SQLModel):
    model_config = ConfigDict(from_attributes=False)
    date: datetime                               
    amount: Q2                          
    description: Optional[str] = None
    amount_after: Optional[Q2] = None
    category: Optional[str] = None
    status: Optional[str] = None
    capital_gain_kind: Optional[CapitalGainKind] = None


class CreateTransactionsRequest(SQLModel):
    model_config = ConfigDict(from_attributes=False)
    account_id: uuid.UUID
    transactions: Annotated[List[TransactionIn], Field(min_length=1)]
    
    
class TransactionRead(TransactionBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    account_id: uuid.UUID
    
    
class TransactionUpdate(PartialUpdateMixin):
    
    amount: Optional[Q2] = None
    description: NoneIfEmpty = None
    balance_before: Optional[Q2] = None
    balance_after: Optional[Q2] = None
    category: NoneIfEmpty = None
    status: NoneIfEmpty = None
    
    __update_require_any__ = {
                              "amount", 
                              "description", 
                              "balance_before", 
                              "balance_after",
                              "category",
                              "status"
                              }
    
    
class MetalHoldingCreate(MetalHoldingBase):
    model_config = ConfigDict(from_attributes=False)

    wallet_id: uuid.UUID
    
    
class MetalHoldingRead(MetalHoldingBase, UUIDMixin, TimestampMixin): 
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    wallet_id: uuid.UUID
    
    
class MetalHoldingUpdate(PartialUpdateMixin):
    
    metal: Optional[MetalType] = None
    grams: Optional["Q6Pos"] = None         
    cost_basis: Optional["Q2"] = None        
    cost_currency: Optional[Currency] = None
    
    __update_require_any__ = {"metal", "grams", "cost_basis", "cost_currency"}
    
    
class RealEstatePriceCreate(RealEstatePriceBase):
    model_config = ConfigDict(from_attributes=False)
    
    
class RealEstatePriceRead(RealEstatePriceBase):
    model_config = ConfigDict(from_attributes=True)
    
    
class RealEstateCreate(RealEstateBase):
    model_config = ConfigDict(from_attributes=False)

    wallet_id: uuid.UUID
       
    
class RealEstateRead(RealEstateBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    wallet_id: uuid.UUID
    
    
class RealEstateUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    country: CountryISO2Opt = None
    city: CityOpt = None
    type: Optional[PropertyType] = None
    area_m2: AreaQ2OptPos = None
    purchase_price: Optional[Q2] = None
    purchase_currency: Optional[Currency] = None
    
    __update_require_any__ = {"name", "country", "city", "type", "area_m2", "purchase_price", "purchase_currency"}
    
    
class WalletCreate(WalletBase):
    model_config = ConfigDict(from_attributes=False)
    
    user_id: uuid.UUID
  
    
class WalletCreateWithoutUser(WalletBase):
    model_config = ConfigDict(from_attributes=False)
    
    
class WalletRead(WalletBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    user_id: uuid.UUID
   
    
class WalletUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    
    __update_require_any__ = {"name"}
    
    
class DebtCreate(DebtBase):
    model_config = ConfigDict(from_attributes=False)

    wallet_id: uuid.UUID
       
    
class DebtRead(DebtBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    wallet_id: uuid.UUID
    
    
class DebtUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    lander: Optional[NonEmptyStr] = None
    amount: Optional[Q2] = None
    currency: Optional[Currency] = None
    interest_rate_pct: Optional[Q2] = None
    monthly_payment: Optional[Q2] = None
    end_date: Optional[datetime] = None
    
    __update_require_any__ = {"name", "lander", "amount", "type", "currency", "interest_rate_pct", "monthly_payment", "end_date"}
    

class RecurringExpenseCreate(RecurringExpenseBase):
    wallet_id: uuid.UUID


class RecurringExpenseRead(RecurringExpenseBase, UUIDMixin, TimestampMixin):
    wallet_id: uuid.UUID


class RecurringExpenseUpdate(PartialUpdateMixin):
    name: Optional[NonEmptyStr] = None
    category: Optional[NonEmptyStr] = None
    amount: Optional[Q2] = None
    currency: Optional[Currency] = None
    due_day: Optional[int] = None
    account: Optional[NonEmptyStr] = None
    note: Optional[NonEmptyStr] = None

    __update_require_any__ = {
        "name", "category", "amount", "currency", "due_day", "account", "note"
    }
    
    
class UserNoteUpsert(UserNoteBase):
    model_config = ConfigDict(from_attributes=False)


class UserNoteRead(UserNoteBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    user_id: uuid.UUID
    
    
class YearGoalCreate(YearGoalBase):
    model_config = ConfigDict(from_attributes=False)

    wallet_id: uuid.UUID


class YearGoalRead(YearGoalBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    wallet_id: uuid.UUID


class YearGoalUpdate(PartialUpdateMixin):
    rev_target_year: Optional[Q2] = None
    exp_budget_year: Optional[Q2] = None
    currency: Optional[Currency] = None
    
    __update_require_any__ = {
        "rev_target_year", "exp_budget_year", "currency", 
    }
    
    
class DepositAccountMonthlySnapshotRead(DepositAccountMonthlySnapshotBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    account_id: uuid.UUID
    wallet_id: uuid.UUID


class BrokerageAccountMonthlySnapshotRead(BrokerageAccountMonthlySnapshotBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    brokerage_account_id: uuid.UUID
    wallet_id: uuid.UUID


class MetalHoldingMonthlySnapshotRead(MetalHoldingMonthlySnapshotBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    metal_holding_id: uuid.UUID
    wallet_id: uuid.UUID


class RealEstateMonthlySnapshotRead(RealEstateMonthlySnapshotBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    real_estate_id: uuid.UUID
    wallet_id: uuid.UUID
