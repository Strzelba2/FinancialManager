from sqlmodel import SQLModel
from pydantic import ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.base import (UserBase, UUIDMixin, TimestampMixin, PartialUpdateMixin,  BankBase,
                             AccountBase, BrokerageAccountBase, DepositAccountBalanceBase,
                             InstrumentBase, HoldingBase, TransactionBase, RealEstateBase, 
                             MetalHoldingBase, WalletBase, BrokerageDepositLinkBase)

from app.validators.validators import (
    Username12, EmailLower, FirstNameOpt, NonEmptyStr, Shortname, BICOpt, Q2OptNonNeg,
    Q2,  Q6Pos, AreaQ2OptPos, CountryISO2Opt, CityOpt, NoneIfEmpty
)

from app.models.enums import (
    AccountType, Currency, InstrumentType, TransactionType, MetalType,
    PropertyType
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
    
    
class TransactionRead(TransactionBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)
    
    account_id: uuid.UUID
    
    
class TransactionUpdate(PartialUpdateMixin):
    
    type: Optional[TransactionType] = None
    amount: Optional[Q2] = None
    description: NoneIfEmpty = None
    balance_before: Optional[Q2] = None
    balance_after: Optional[Q2] = None
    
    __update_require_any__ = {"type", "amount", "description", "balance_before", "balance_after"}
    
    
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
    
    
class WalletRead(WalletBase, UUIDMixin, TimestampMixin):
    model_config = ConfigDict(from_attributes=True, validate_assignment=False)

    user_id: uuid.UUID
    
    
class WalletUpdate(PartialUpdateMixin):

    name: Optional[NonEmptyStr] = None
    
    __update_require_any__ = {"name"}
