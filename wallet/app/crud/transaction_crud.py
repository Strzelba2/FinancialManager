from __future__ import annotations
from fastapi import HTTPException, status
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.models import (
    Transaction, DepositAccount, Wallet, DepositAccountBalance, CapitalGain
    )
from app.schamas.schemas import (
    TransactionCreate, TransactionRead,
    TransactionUpdate,
)
from app.schamas.response import (
    BatchUpdateTransactionsRequest, BatchUpdateTransactionsResponse, Currency
)

logger = logging.getLogger(__name__)


async def create_transaction(session: AsyncSession, data: TransactionCreate) -> Transaction:
    tx = Transaction(**data.model_dump())  
    session.add(tx)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Could not create transaction (invalid account or constraints).") from e
    await session.refresh(tx)
    return tx


async def create_transaction_uow(session: AsyncSession, data: TransactionCreate) -> None:
    """Create a Transaction without committing; caller controls the transaction boundary."""
    tx = Transaction(**data.model_dump(exclude_unset=True))
    session.add(tx)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError("Could not create transaction (invalid account or constraints).") from e
    await session.refresh(tx)
    return tx


async def get_transaction(session: AsyncSession, tx_id: uuid.UUID) -> Optional[Transaction]:
    return await session.get(Transaction, tx_id)


async def get_transaction_with_account(session: AsyncSession, tx_id: uuid.UUID) -> Optional[Transaction]:
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.account))
        .where(Transaction.id == tx_id)
    )
    result = await session.execute(stmt)
    return result.first()


async def get_last_transactions_for_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    limit: int = 5,
) -> List[TransactionRead]:
    """
    Return last `limit` transactions for a single deposit account, ordered by date_transaction DESC.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.date_transaction.desc(), Transaction.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [TransactionRead.model_validate(r, from_attributes=True) for r in rows]


async def list_transactions(
    session: AsyncSession,
    account_id: Optional[uuid.UUID] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    search: Optional[str] = None,       
    limit: int = 50,
    offset: int = 0,
    newest_first: bool = True,
    with_account: bool = False,
) -> List[Transaction]:
    stmt = select(Transaction)

    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if created_from:
        stmt = stmt.where(Transaction.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Transaction.created_at < created_to)
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Transaction.description.ilike(like))

    if with_account:
        stmt = stmt.options(selectinload(Transaction.account))

    stmt = stmt.order_by(
        Transaction.created_at.desc() if newest_first else Transaction.created_at.asc()
    ).offset(offset).limit(limit)

    result = await session.execute(stmt)
    return result.all()


def _apply_tx_filters(
    stmt,
    account_ids: Optional[list[uuid.UUID]] = None,
    categories: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
):
    if account_ids:
        stmt = stmt.where(Transaction.account_id.in_(account_ids))
    if categories:
        stmt = stmt.where(Transaction.category.in_([c for c in categories if c]))
    if statuses:
        stmt = stmt.where(Transaction.status.in_([s for s in statuses if s]))
    if date_from:
        stmt = stmt.where(Transaction.date_transaction >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Transaction.date_transaction <= datetime.combine(date_to, datetime.max.time()))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Transaction.description.ilike(like))
    return stmt


async def list_transactions_page(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    size: int,
    account_ids: Optional[list[uuid.UUID]] = None,
    categories: Optional[list[str]] = None,
    statuses: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
) -> tuple[list[tuple[Transaction, DepositAccount]], int, int, dict[str, Decimal]]:
    page = max(1, int(page))
    size = min(200, max(1, int(size)))
    offset = (page - 1) * size

    base = (
        select(Transaction, DepositAccount)
        .join(DepositAccount, DepositAccount.id == Transaction.account_id)
        .join(Wallet, Wallet.id == DepositAccount.wallet_id)
        .where(Wallet.user_id == user_id)
    )
    base = _apply_tx_filters(
        base,
        account_ids=account_ids,
        categories=categories,
        statuses=statuses,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    rows = (
        (await session.execute(base.order_by(Transaction.date_transaction.desc()).offset(offset).limit(size)))
        .all()
    )

    sum_stmt = (
        select(DepositAccount.currency, func.coalesce(func.sum(Transaction.amount), 0))
        .join(DepositAccount, DepositAccount.id == Transaction.account_id)
        .join(Wallet, Wallet.id == DepositAccount.wallet_id)
        .where(Wallet.user_id == user_id)
    )
    sum_stmt = _apply_tx_filters(
        sum_stmt,
        account_ids=account_ids,
        categories=categories,
        statuses=statuses,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    sum_stmt = sum_stmt.group_by(DepositAccount.currency)

    sum_rows = (await session.execute(sum_stmt)).all()
    sum_by_ccy: dict[str, Decimal] = {}
    for ccy, total_amt in sum_rows:
        ccy_str = str(getattr(ccy, "value", ccy))
        sum_by_ccy[ccy_str] = Decimal(str(total_amt))

    return rows, total, size, sum_by_ccy


async def update_transaction(
    session: AsyncSession,
    tx_id: uuid.UUID,
    data: TransactionUpdate,
) -> Optional[Transaction]:
    tx = await session.get(Transaction, tx_id)
    if not tx:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tx, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Transaction update violates constraints.") from e

    await session.refresh(tx)
    return tx


async def delete_transaction(session: AsyncSession, tx_id: uuid.UUID) -> bool:
    tx = await session.get(Transaction, tx_id)
    if not tx:
        return False
    session.delete(tx)
    await session.commit()
    return True


async def delete_transaction_for_user_rebalance(
    session: AsyncSession,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
) -> bool:
    tx = await session.scalar(
        select(Transaction)
        .join(DepositAccount, DepositAccount.id == Transaction.account_id)
        .join(Wallet, Wallet.id == DepositAccount.wallet_id)
        .where(Wallet.user_id == user_id, Transaction.id == transaction_id)
        .with_for_update()
    )
    if tx is None:
        return False

    acc_id = uuid.UUID(str(tx.account_id))
    tx_dt = tx.date_transaction
    tx_id = uuid.UUID(str(tx.id))

    bal = await session.scalar(
        select(DepositAccountBalance)
        .where(DepositAccountBalance.account_id == acc_id)
        .with_for_update()
    )
    if bal is None:
        bal = DepositAccountBalance(
            account_id=acc_id,
            available=Decimal("0"),
            blocked=Decimal("0"),
        )
        session.add(bal)
        await session.flush()

    prev = await session.scalar(
        select(Transaction)
        .where(
            Transaction.account_id == acc_id,
            or_(
                Transaction.date_transaction < tx_dt,
                and_(Transaction.date_transaction == tx_dt, Transaction.id < tx_id),
            ),
        )
        .order_by(Transaction.date_transaction.desc(), Transaction.id.desc())
        .limit(1)
        .with_for_update()
    )

    later = list(
        (await session.scalars(
            select(Transaction)
            .where(
                Transaction.account_id == acc_id,
                or_(
                    Transaction.date_transaction > tx_dt,
                    and_(Transaction.date_transaction == tx_dt, Transaction.id > tx_id),
                ),
            )
            .order_by(Transaction.date_transaction.asc(), Transaction.id.asc())
            .with_for_update()
        )).all()
    )

    await session.execute(
        delete(CapitalGain).where(CapitalGain.transaction_id == tx_id)
    )

    await session.delete(tx)
    await session.flush()

    if prev is not None:
        running = Decimal(str(prev.balance_after))
    else:
        running = Decimal(str(tx.balance_before))

    for t in later:
        amt = Decimal(str(t.amount))
        t.balance_before = running
        t.balance_after = running + amt
        running = Decimal(str(t.balance_after))

    if running < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deleting this transaction would make account balance negative.",
        )

    bal.available = running

    await session.flush()
    return True


async def account_has_transactions(session: AsyncSession, account_id: uuid.UUID) -> bool:
    stmt = select(func.count()).select_from(Transaction).where(Transaction.account_id == account_id)
    result = await session.execute(stmt)
    return (result.scalar_one() or 0) > 0


async def find_duplicate_transaction(
    session: AsyncSession,
    data: TransactionCreate,
) -> Optional[Transaction]:

    stmt = (
        select(Transaction)
        .where(
            Transaction.account_id == data.account_id,
            Transaction.date_transaction == data.date_transaction,
            Transaction.amount == data.amount,
            Transaction.description == data.description,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def batch_update_transactions(
    session: AsyncSession,
    user_id: uuid.UUID,
    req: BatchUpdateTransactionsRequest,
) -> BatchUpdateTransactionsResponse:
    updated = 0

    for patch in req.items:
        tx = await session.get(Transaction, patch.id)
        if tx is None:
            continue

        acc = await session.get(DepositAccount, tx.account_id)
        if acc is None:
            continue

        w = await session.get(Wallet, acc.wallet_id)
        if w is None or w.user_id != user_id:
            continue

        data = patch.model_dump(exclude_unset=True, exclude_none=True)
        data.pop("id", None)

        for k, v in data.items():
            setattr(tx, k, v)

        updated += 1

    await session.commit()
    return BatchUpdateTransactionsResponse(updated=updated)


async def get_last_balance_after(session: AsyncSession, account_id: uuid.UUID) -> Decimal:
    stmt = (
        select(Transaction.balance_after)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.date_transaction.desc())
        .limit(1)
    )
    val = await session.scalar(stmt)
    return Decimal(str(val or "0"))


async def sum_income_expense_for_wallet_year(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    year: int,
) -> List[Tuple[str, Currency, Decimal]]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    stmt = (
        select(
            Transaction.status,
            DepositAccount.currency,
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .select_from(Transaction)
        .join(DepositAccount, DepositAccount.id == Transaction.account_id)
        .where(
            DepositAccount.wallet_id == wallet_id,
            Transaction.date_transaction >= start,
            Transaction.date_transaction < end,
            Transaction.status.in_(["INCOME", "EXPENSE"]),
        )
        .group_by(Transaction.status, DepositAccount.currency)
    )
    res = await session.execute(stmt)
    return list(res.all())


async def sum_income_expense_for_wallet_month_range(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    start_dt: datetime,
    end_dt: datetime,
) -> List[Tuple[datetime, str, Currency, Decimal]]:
    month = func.date_trunc("month", Transaction.date_transaction).label("month")

    stmt = (
        select(
            month,
            Transaction.status,
            DepositAccount.currency,  
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .select_from(Transaction)
        .join(DepositAccount, DepositAccount.id == Transaction.account_id)
        .where(
            DepositAccount.wallet_id == wallet_id,
            Transaction.date_transaction >= start_dt,
            Transaction.date_transaction < end_dt,
            Transaction.status.in_(["INCOME", "EXPENSE"]),
        )
        .group_by(month, Transaction.status, DepositAccount.currency)
        .order_by(month.asc())
    )
    res = await session.execute(stmt)
    return list(res.all())
