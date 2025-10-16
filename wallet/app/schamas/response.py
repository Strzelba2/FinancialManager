from pydantic import BaseModel, Field
from decimal import Decimal
from typing import List, Optional
from .schemas import AccountType, Currency
import uuid


class AccountListItem(BaseModel):
    id: uuid.UUID
    name: str
    account_type: AccountType
    currency: Currency
    available: Optional[Decimal] = None    
    blocked: Optional[Decimal] = None


class WalletListItem(BaseModel):
    id: uuid.UUID
    name: str
    accounts: Optional[List[AccountListItem]] = Field(default_factory=list)


class WalletUserResponse(BaseModel):
    first_name: str
    user_id: str
    wallets: Optional[List[WalletListItem]] = Field(default_factory=list)
    banks: Optional[List] = Field(default_factory=list)
    
    
class WalletResponse(WalletListItem):
    pass

    
class AccountCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    account_type: str
