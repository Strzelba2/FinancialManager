import uuid
from sqlmodel import Field, Relationship
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from typing import Optional

from .base import (UserBase, UUIDMixin, TimestampMixin, BankBase,
                   AccountBase, BrokerageAccountBase, DepositAccountBalanceBase,
                   InstrumentBase, HoldingBase, TransactionBase, RealEstateBase, 
                   MetalHoldingBase, WalletBase, BrokerageDepositLinkBase,
                   BrokerageEventBase, CapitalGainBase, RealEstatePriceBase,
                   DebtBase, RecurringExpenseBase, UserNoteBase, YearGoalBase,
                   FxMonthlySnapshotBase, DepositAccountMonthlySnapshotBase,
                   BrokerageAccountMonthlySnapshotBase, RealEstateMonthlySnapshotBase,
                   MetalHoldingMonthlySnapshotBase)


class User(UserBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "users"
    
    wallets: list["Wallet"] = Relationship(back_populates="user") 
  
    
class Bank(BankBase, UUIDMixin, table=True):
    __tablename__ = "banks"

    accounts: list["DepositAccount"] = Relationship(back_populates="bank")
    brokerage_accounts: list["BrokerageAccount"] = Relationship(back_populates="bank") 
  
      
class DepositAccount(AccountBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "deposit_accounts"
    
    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        ) 
    )
    bank_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("banks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    wallet: "Wallet" = Relationship(back_populates="deposit_accounts")
    bank: Optional[Bank] = Relationship(back_populates="accounts")
    balance: Optional["DepositAccountBalance"] = Relationship(
        back_populates="account",
        sa_relationship_kwargs={      
            "cascade": "all, delete-orphan",
            "passive_deletes": True,  
        },
    )
    transactions: list["Transaction"] = Relationship(
        back_populates="account",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
        )
    
    __table_args__ = (
        sa.UniqueConstraint("wallet_id", "name", name="uq_depacc_wallet_name"),
        )

    
class BrokerageAccount(BrokerageAccountBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "brokerage_accounts"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    bank_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("banks.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    
    wallet: "Wallet" = Relationship(back_populates="brokerage_accounts")
    bank: Optional[Bank] = Relationship(back_populates="brokerage_accounts")
    deposit_links: list["BrokerageDepositLink"] = Relationship(
        back_populates="brokerage_account",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True})
    
    holdings: list["Holding"] = Relationship(
        back_populates="account",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True})
    
    events: list["BrokerageEvent"] = Relationship(
        back_populates="account_event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    
    __table_args__ = (
        sa.Index("ix_brokerage_wallet_bank", "wallet_id", "bank_id"),
        sa.UniqueConstraint("wallet_id", "bank_id", "name", name="uq_brokerage_name_per_wallet_bank"),
    )
    

class BrokerageEvent(BrokerageEventBase, UUIDMixin, table=True):
    __tablename__ = "brokerage_events"
    
    brokerage_account_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True),
                            sa.ForeignKey("brokerage_accounts.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )
    
    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True),
                            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )
    
    account_event: "BrokerageAccount" = Relationship(back_populates="events")
    
    __table_args__ = (
        sa.CheckConstraint("quantity >= 0", name="ck_brokevent_quantity_nonneg"),
        sa.CheckConstraint("price >= 0",  name="ck_brokevent_price_nonneg"),
    )
    
    
class BrokerageDepositLink(BrokerageDepositLinkBase, table=True):

    __tablename__ = "brokerage_deposit_links"
    
    brokerage_account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("brokerage_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    deposit_account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("deposit_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    
    brokerage_account: BrokerageAccount = Relationship(back_populates="deposit_links")
    deposit_account: DepositAccount = Relationship()

    __table_args__ = (
        sa.UniqueConstraint("brokerage_account_id", "currency", name="uq_brokerage_currency_one_deposit"),
    )
    
    
class DepositAccountBalance(DepositAccountBalanceBase, TimestampMixin, table=True):
    __tablename__ = "deposit_account_balances"

    account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("deposit_accounts.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )

    account: Optional[DepositAccount] = Relationship(back_populates="balance")
    
    __table_args__ = (
        sa.CheckConstraint("available >= 0", name="ck_depaccbal_available_nonneg"),
        sa.CheckConstraint("blocked >= 0",  name="ck_depaccbal_blocked_nonneg"),
    )
    

class Instrument(InstrumentBase, UUIDMixin, table=True):
    __tablename__ = "instruments"
   
    __table_args__ = (
        sa.Index("ix_instr_ref_symbol", "symbol"),
    )
    
    
class Holding(HoldingBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "holdings"

    account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("brokerage_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )
    instrument_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    account: BrokerageAccount = Relationship(back_populates="holdings")
    instrument: Instrument = Relationship()

    __table_args__ = (
        sa.UniqueConstraint("account_id", "instrument_id", name="uq_holding"),
        sa.CheckConstraint("quantity >= 0", name="ck_holding_qty_nonneg"),
        sa.CheckConstraint("avg_cost >= 0", name="ck_holding_avgcost_nonneg"),
    )
    
    
class Transaction(UUIDMixin, TransactionBase, TimestampMixin, table=True):
    __tablename__ = "transactions"
    
    account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("deposit_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    account: Optional[DepositAccount] = Relationship(back_populates="transactions")
    
    __table_args__ = (
        sa.CheckConstraint("balance_before >= 0", name="ck_tx_balance_before_nonneg"),
        sa.CheckConstraint("balance_after  >= 0", name="ck_tx_balance_after_nonneg"),
    )
     
 
class CapitalGain(CapitalGainBase, UUIDMixin, table=True):
    __tablename__ = "capital_gains"

    deposit_account_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("deposit_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    transaction_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
            index=True,
        ),
    )   
    
    
class RealEstate(RealEstateBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "real_estates"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    wallet: "Wallet" = Relationship(back_populates="real_estates")
    
    __table_args__ = (
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_re_name_not_empty"),
    )


class RealEstatePrice(RealEstatePriceBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "real_estate_prices"

    __table_args__ = (
        sa.Index(
            "ix_re_price_lookup_latest",
            "type",
            "country",
            "city",
            "currency",
            "created_at",
        ),
        sa.CheckConstraint("avg_price_per_m2 >= 0", name="ck_re_price_m2_nonneg"),
    )
    
      
class MetalHolding(MetalHoldingBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "metal_holdings"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    wallet: "Wallet" = Relationship(back_populates="metal_holdings")

    __table_args__ = (
        sa.UniqueConstraint("wallet_id", "metal", name="uq_wallet_metal_one_row"),
        sa.CheckConstraint("grams > 0", name="ck_metal_grams_pos"),
    )
    
    
class Wallet(WalletBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "wallets"
    
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    user: "User" = Relationship(back_populates="wallets")

    deposit_accounts: list["DepositAccount"] = Relationship(back_populates="wallet",
                                                            sa_relationship_kwargs={"cascade": "all, delete-orphan",
                                                                                    "passive_deletes": True})
    brokerage_accounts: list["BrokerageAccount"] = Relationship(back_populates="wallet",
                                                                sa_relationship_kwargs={"cascade": "all, delete-orphan",
                                                                                        "passive_deletes": True})
    
    real_estates: list["RealEstate"] = Relationship(back_populates="wallet",
                                                    sa_relationship_kwargs={"cascade": "all, delete-orphan", 
                                                                            "passive_deletes": True})
    metal_holdings: list["MetalHolding"] = Relationship(back_populates="wallet",
                                                        sa_relationship_kwargs={"cascade": "all, delete-orphan", 
                                                                                "passive_deletes": True})
    debts: list["Debt"] = Relationship(back_populates="wallet",
                                       sa_relationship_kwargs={"cascade": "all, delete-orphan", 
                                                               "passive_deletes": True})
    
    __table_args__ = (
        sa.UniqueConstraint("user_id", "name", name="uq_wallet_owner_name"),
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_wallet_name_not_empty"),
    )
    
    
class Debt(DebtBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "debt"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
    )

    wallet: "Wallet" = Relationship(back_populates="debts")
    
    __table_args__ = (
        sa.CheckConstraint("char_length(btrim(name)) > 0", name="ck_debt_name_not_empty"),
        sa.CheckConstraint("char_length(btrim(lander)) > 0", name="ck_debt_lander_not_empty"),
        sa.CheckConstraint("amount >= 0", name="ck_debt_amount_nonneg"),
        sa.CheckConstraint("interest_rate_pct >= 0", name="ck_debt_rate_nonneg"),
        sa.CheckConstraint("monthly_payment >= 0", name="ck_debt_payment_nonneg"),
    )
    
    
class RecurringExpense(RecurringExpenseBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "recurring_expenses"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    __table_args__ = (
        sa.CheckConstraint("amount >= 0", name="ck_recurring_exp_amount_nonneg"),
        sa.CheckConstraint("due_day >= 1 AND due_day <= 31", name="ck_recurring_exp_due_day_range"),
        sa.Index("ix_recurring_exp_wallet_due_day", "wallet_id", "due_day"),
    )
    
    
class UserNote(UserNoteBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "user_notes"

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )


class YearGoal(YearGoalBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "year_goals"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    __table_args__ = (
        sa.UniqueConstraint("wallet_id", "year", name="uq_year_goals_wallet_year"),
        sa.CheckConstraint("year >= 1970 AND year <= 2100", name="ck_year_goals_year_range"),
    )


class FxMonthlySnapshot(FxMonthlySnapshotBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "fx_monthly_snapshots"

    __table_args__ = (
        sa.UniqueConstraint("month_key", name="uq_fx_month_key"),
        sa.Index("ix_fx_month_key", "month_key"),
    )
      
    
class DepositAccountMonthlySnapshot(DepositAccountMonthlySnapshotBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "deposit_account_monthly_snapshots"
    
    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )

    account_id: Optional[uuid.UUID] = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True), 
            sa.ForeignKey("deposit_accounts.id", ondelete="SET NULL"),
            nullable=True, 
            index=True)
    )

    __table_args__ = (
        sa.UniqueConstraint("account_id", "month_key", name="uq_depacc_monthly_snapshot"),
        sa.Index("ix_depacc_monthly_wallet_month", "wallet_id", "month_key"),
        sa.Index("ix_depacc_monthly_wallet_month_id", "wallet_id", "month_key", "account_id"),
        
    )


class BrokerageAccountMonthlySnapshot(BrokerageAccountMonthlySnapshotBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "brokerage_account_monthly_snapshots"
    
    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )
    
    brokerage_account_id: Optional[uuid.UUID] = Field(
        sa_column=sa.Column(
            pg.UUID(as_uuid=True), 
            sa.ForeignKey("brokerage_accounts.id", ondelete="SET NULL"),
            nullable=True, 
            index=True)
    )

    __table_args__ = (
        sa.UniqueConstraint("brokerage_account_id", "month_key", name="uq_broacc_monthly_snapshot"),
        sa.Index("ix_broacc_monthly_wallet_month", "wallet_id", "month_key"),
        sa.Index("ix_broacc_monthly_wallet_month_id", "wallet_id", "month_key", "brokerage_account_id"),
    )


class MetalHoldingMonthlySnapshot(MetalHoldingMonthlySnapshotBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "metal_holding_monthly_snapshots"

    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )
    metal_holding_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("metal_holdings.id", ondelete="SET NULL"),
                            nullable=True, index=True)
    )

    __table_args__ = (
        sa.UniqueConstraint("metal_holding_id", "month_key", name="uq_metal_monthly_snapshot"),
        sa.Index("ix_metal_wallet_month", "wallet_id", "month_key"),
        sa.Index("ix_metal_wallet_month_id", "wallet_id", "month_key", "metal_holding_id"),
    )


class RealEstateMonthlySnapshot(RealEstateMonthlySnapshotBase, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "real_estate_monthly_snapshots"
    
    wallet_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    )
    real_estate_id: uuid.UUID = Field(
        sa_column=sa.Column(pg.UUID(as_uuid=True), sa.ForeignKey("real_estates.id", ondelete="SET NULL"),
                            nullable=True, index=True)
    )

    __table_args__ = (
        sa.UniqueConstraint("real_estate_id", "month_key", name="uq_re_monthly_snapshot"),
        sa.Index("ix_re_monthly_wallet_month", "wallet_id", "month_key"),
        sa.Index("ix_re_monthly_wallet_month_id", "wallet_id", "month_key", "real_estate_id"),
    )
