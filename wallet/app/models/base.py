from sqlmodel import Field, SQLModel
import sqlalchemy as sa
from sqlalchemy.sql import func, text
from sqlalchemy.types import DateTime
from decimal import Decimal
from pydantic import ConfigDict, model_validator
from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects import postgresql as pg
from typing import Optional, ClassVar, Set

from .enums import (
    PropertyType, AccountType, Currency, InstrumentType,
    MetalType, BrokerageEventKind, CapitalGainKind
    )

from app.validators.validators import (
    Username12, EmailLower, FirstNameOpt, 
    Shortname, BICOpt, NonEmptyStr,
    BytesLen32, Q2,  Q6Pos, AreaQ2OptPos,
    CountryISO2Opt, CityOpt, NoneIfEmpty,
    MICCode
)


class UUIDMixin(SQLModel, table=False):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=pg.UUID(as_uuid=True),   
        sa_column_kwargs={"server_default": text("gen_random_uuid()")}
    )


class TimestampMixin(SQLModel, table=False):
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),   
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),         
            "nullable": False,
        },
    )
 
    
class PartialUpdateMixin(SQLModel):
    """
    Shared validator to ensure an update payload isn't empty.

    Customize per-DTO via:
    - __update_require_any__: if set, require that *at least one* of these fields
      is present in the payload. If None (default), require any field at all.
    - __update_ignore__: fields to ignore when checking (e.g., metadata fields).
    """
    model_config = ConfigDict(from_attributes=False, validate_assignment=False)

    __update_require_any__: ClassVar[Optional[Set[str]]] = None
    __update_ignore__: ClassVar[Set[str]] = set()

    @model_validator(mode="after")
    def _require_some_fields(self):
        fields_set: Set[str] = set(getattr(self, "model_fields_set", set()))

        if self.__update_ignore__:
            fields_set = {f for f in fields_set if f not in self.__update_ignore__}

        if self.__update_require_any__ is not None:
            ok = bool(fields_set & self.__update_require_any__)
        else:
            ok = bool(fields_set)

        if not ok:
            if self.__update_require_any__:
                need = ", ".join(sorted(self.__update_require_any__))
                raise ValueError(f"Provide at least one of: {need}.")
            raise ValueError("Provide at least one field to update.")
        return self
  
    
class UserBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    username: Username12 = Field(
        sa_column=sa.Column(sa.String(12), unique=True, nullable=False),
        description="User handle (unique, max 12 chars)."
    )
    email: EmailLower = Field(
        sa_column=sa.Column(sa.String(255), unique=True, index=True, nullable=False),
        description="User handle (unique, max 12 chars)."
    )
    first_name: FirstNameOpt = Field(
        sa_column=sa.Column(sa.String(30)),
        description="User first name (optional)."
    )

    
class BankBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    name: NonEmptyStr = Field(
        sa_column=sa.Column(sa.String(255), nullable=False, unique=True),
        description="Full legal name of the bank/broker (unique)."
    )
    shortname: Shortname = Field(
        sa_column=sa.Column(sa.String(5), nullable=False, unique=True),
        description="Short code displayed in UI (unique, ≤5 chars)."
    )
    bic: BICOpt = Field(
        default=None, 
        sa_column=sa.Column(sa.String(11), nullable=True),
        description="BIC/SWIFT code if applicable."
    )
   
    
class AccountBase(SQLModel):
    model_config = ConfigDict(validate_assignment=False, from_attributes=True)
    
    name: NonEmptyStr = Field(
        sa_column=sa.Column(sa.String(255), nullable=False),
        description="Human-readable account name (unique within wallet via constraint)."
    )
    
    account_type: AccountType = Field(
        sa_column=sa.Column(sa.Enum(AccountType, name="account_type_enum"), nullable=False),
        description="Account category (e.g., CURRENT, SAVINGS, BROKERAGE_WALLET)."
    )
    
    account_number_nonce: bytes = Field(
        sa_column=sa.Column(sa.LargeBinary(12), nullable=False),
        description="AES-GCM nonce (12B) for account_number."
    )
    
    account_number_ct: bytes = Field(
        sa_column=sa.Column(sa.LargeBinary, nullable=False),
        description="AES-GCM ciphertext+tag for account_number."
    )

    account_number_fp: BytesLen32 = Field(
        sa_column=sa.Column("account_number_fp", sa.LargeBinary(32), unique=True, index=True, nullable=False),
        description="HMAC fingerprint of account number (used for uniqueness & lookups)."
    )

    iban_nonce: bytes | None = Field(
        default=None,
        sa_column=sa.Column(sa.LargeBinary(12), nullable=True),
        description="AES-GCM nonce (12B) for IBAN."
    )
    
    iban_ct: bytes | None = Field(
        default=None,
        sa_column=sa.Column(sa.LargeBinary, nullable=True),
        description="AES-GCM ciphertext+tag for IBAN."
    )
    
    iban_fp: Optional[bytes] = Field(
        default=None, 
        sa_column=sa.Column(sa.LargeBinary(32), nullable=True, unique=True, index=True)
    )

    currency: Currency = Field(
        sa_column=sa.Column(sa.Enum(Currency, name="currency_enum"), nullable=False),
        description="Account currency (must match balances & transactions)."
    )

    @model_validator(mode="after")
    def _both_account_secrets_set(self):
        if not self.account_number_ct or not self.account_number_fp or not self.account_number_nonce:
            raise ValueError("Both account_number_ct and account_number_fp and account_number_nonce must be set")
        return self

    
class BrokerageAccountBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    name: NonEmptyStr = Field(
        sa_column=sa.Column(sa.String(255), nullable=False),
        description="Human-readable account name (unique within wallet via constraint)."
    )
    
    
class BrokerageEventBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)

    kind: BrokerageEventKind = Field(
        sa_column=sa.Column(
            sa.Enum(
                BrokerageEventKind,
                name="brokerage_event_kind",
            ),
            nullable=False,
        )
    )

    quantity: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="quantity envent"
    )
    price: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="price envent"
    )
    currency: Currency = Field(
        sa_column=sa.Column(sa.Enum(Currency, name="currency_enum"), nullable=False),
        description="Brokerage event currency."
    )
    
    split_ratio: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Split event"
    )
    trade_at: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))  
   
    
class BrokerageDepositLinkBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    currency: Currency = Field(sa_column=sa.Column(sa.Enum(Currency, name="currency_enum"), nullable=False))
   
      
class DepositAccountBalanceBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    available: Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Available balance"
    )
    blocked:   Q2 = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"),
        description="Blocked balance"
    )
    
    
class CapitalGainBase(SQLModel):
    kind: CapitalGainKind = Field(
        sa_column=sa.Column(
            sa.Enum(CapitalGainKind, name="capital_gain_kind_enum"),
            nullable=False,
        ),
        description="Source of profit"
    )
    amount: Q2 = Field(
        sa_column=sa.Column(sa.Numeric(20, 2), nullable=False),
    )
    currency: Currency = Field(
        sa_column=sa.Column(sa.Enum(Currency, name="currency_enum"), nullable=False),
    )
    occurred_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )

     
class HoldingBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True) 
    
    quantity: Q2 = Field(sa_column=sa.Column(sa.Numeric(28, 10), nullable=False, server_default="0"))
    avg_cost: Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 8),  nullable=False, server_default="0"))
       
           
class InstrumentBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    symbol: Shortname = Field(sa_column=sa.Column(sa.String(5), unique=True, index=True))
    mic: MICCode = Field(sa_column=sa.Column(sa.String(4), index=True, nullable=False),
                         description="MIC: 4 uppercase alphanumeric (ISO 10383 operating MICs like XWAR, XLON, XNAS)" )
    name: NonEmptyStr = Field(sa_column=sa.Column(sa.String(255), nullable=False))
    type: InstrumentType = Field(sa_column=sa.Column(sa.Enum(InstrumentType, name="instrument_type_enum"), nullable=False))
    currency: Currency = Field(sa_column=sa.Column(sa.Enum(Currency, name="currency_enum"), nullable=False))
    sync_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(),
                            onupdate=sa.func.now(), nullable=False)
    )  
  
            
class TransactionBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    amount: Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 2), nullable=False))
    description: NoneIfEmpty = Field(default=None, sa_column=sa.Column(sa.String(255)))
    balance_before: Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"))
    balance_after:  Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 2), nullable=False, server_default="0"))
    date_transaction: datetime = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False))
   
    
class MetalHoldingBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    metal: MetalType = Field(sa_column=sa.Column(sa.Enum(MetalType, name="metal_enum"), nullable=False))
    grams: Q6Pos = Field(sa_column=sa.Column(sa.Numeric(20, 6), nullable=False))
    cost_basis: Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 2)))
    cost_currency: Currency | None = Field(default=None, sa_column=sa.Column(sa.Enum(Currency, name="currency_enum")))
  
    
class RealEstateBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    name: NonEmptyStr = Field(sa_column=sa.Column(sa.String(255), nullable=False)) 
    country: CountryISO2Opt = Field(default=None, sa_column=sa.Column(sa.String(2)))
    city: CityOpt = Field(default=None, sa_column=sa.Column(sa.String(64)))
    type: PropertyType = Field(sa_column=sa.Column(sa.Enum(PropertyType, name="propertyt_type_enum"), nullable=False))
    area_m2: AreaQ2OptPos = Field(default=None, sa_column=sa.Column(sa.Numeric(12, 2)))
    purchase_price: Q2 = Field(sa_column=sa.Column(sa.Numeric(20, 2)))
    purchase_currency: Currency | None = Field(default=None, sa_column=sa.Column(sa.Enum(Currency, name="currency_enum")))


class WalletBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True, from_attributes=True)
    
    name: NonEmptyStr = Field(sa_column=sa.Column(sa.String(255),  nullable=False))
