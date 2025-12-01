from sqlmodel.ext.asyncio.session import AsyncSession
from decimal import Decimal
from datetime import timedelta
import uuid
import logging

from app.schamas.schemas import (
    CreateTransactionsRequest, TransactionIn, TransactionCreate,
    CapitalGainCreate
)
from app.models.enums import CapitalGainKind
from app.crud.deposit_account_crud import get_deposit_account
from app.crud.deposit_account_balance import get_deposit_account_balance
from app.crud.capital_gain_crud import create_capital_gain
from app.core.exceptions import ImportMismatchError
from app.crud.transaction_crud import (
    create_transaction_uow, account_has_transactions, find_duplicate_transaction
    )

logger = logging.getLogger(__name__)


async def create_transactions_service(
    session: AsyncSession,
    payload: CreateTransactionsRequest,
    verify_amount_after: bool = False, 
    return_tr: bool = False   
) -> dict:
    """
    Imports multiple transactions into a deposit account and updates the available balance.

    Args:
        session (AsyncSession): SQLAlchemy database session.
        payload (CreateTransactionsRequest): Contains account ID and transaction rows.
        verify_amount_after (bool, optional): If True, verifies provided balance_after values.
                                              Raises `ImportMismatchError` on mismatch.

    Returns:
        dict: Summary of the operation including:
              - number of created transactions
              - final balance
              - account ID

    Raises:
        ValueError: If account is not found.
        ImportMismatchError: If balance_after mismatch is detected when `verify_amount_after` is True.
    """
    logger.info(f"Creating transactions for account: {payload.account_id}")
    
    account = await get_deposit_account(session, payload.account_id)
    if not account:
        logger.error("Unknown account_id provided")
        raise ValueError("Unknown account_id")
    
    if payload.transactions[0].date > payload.transactions[-1].date:
        rows: list[TransactionIn] = list(reversed(payload.transactions))
    else:
        rows = payload.transactions

    bal = await get_deposit_account_balance(session, account.id)
    
    has_tx = await account_has_transactions(session, payload.account_id)
    
    if not has_tx:
        first = rows[0]
        if first.amount_after is not None:
            last_balance = Decimal(first.amount_after) - Decimal(first.amount)
        else:

            last_balance = Decimal(bal.available or 0)

    else:
        last_balance = Decimal(bal.available or 0)
    
    created = 0
    transaction_ids: list[uuid.UUID] = []
    for i, r in enumerate(rows, start=0):
        amount = Decimal(r.amount)
        before = last_balance

        computed_after = before + amount
        if r.amount_after is not None:
            provided_after = Decimal(r.amount_after)
            if verify_amount_after and provided_after != computed_after:
                raise ImportMismatchError(f"Saldo po operacji w dniu {r.date} nie zgadza się: {provided_after} != {computed_after}")
            after = provided_after
        else:
            after = computed_after

        tx_data = TransactionCreate(
            account_id=payload.account_id,
            amount=amount,
            description=r.description,
            balance_before=before,
            balance_after=after,
            date_transaction=r.date + timedelta(seconds=i)
        )
        
        dup = await find_duplicate_transaction(session, tx_data)
        if dup is not None:
            raise ValueError(
                f"Duplicate transaction detected for "
                f"account={payload.account_id}, "
                f"date={tx_data.date_transaction}, "
                f"amount={tx_data.amount}, "
                f"description={tx_data.description!r}"
            )

        tx = await create_transaction_uow(session, tx_data)
        
        transaction_ids.append(tx.id)
        created += 1
        last_balance = after

        bal.available = last_balance
        session.add(bal)
        await session.flush()
        
        if r.capital_gain_kind in (
            CapitalGainKind.DEPOSIT_INTEREST,
            CapitalGainKind.BROKER_DIVIDEND,
        ) and amount != 0:
            cg_data = CapitalGainCreate(
                deposit_account_id=payload.account_id,
                transaction_id=tx.id,
                kind=r.capital_gain_kind,
                amount=amount,                
                currency=account.currency,  
                occurred_at=tx.date_transaction,
                tax_year=tx.date_transaction.year,
            )
            await create_capital_gain(session, cg_data)

    logger.info(f"{created} transactions created for account {account.id}")
    
    if return_tr:
        return {
            "created": created,
            "final_balance": last_balance,
            "account_id": str(account.id),
            "transaction_ids": [str(tid) for tid in transaction_ids],
        }
        
    return {
        "created": created, 
        "final_balance": last_balance, 
        "account_id": str(account.id)
        }