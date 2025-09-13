from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DepositAccountBalance, DepositAccount
from app.schamas.schemas import DepositAccountBalanceCreate


async def create_deposit_account_balance(
    session: AsyncSession, data: DepositAccountBalanceCreate
) -> DepositAccountBalance:
    bal = DepositAccountBalance(**data.model_dump())
    session.add(bal)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Balance already exists for this account or invalid account_id.") from e
    await session.refresh(bal)
    return bal


async def get_deposit_account_balance(
    session: AsyncSession, account_id: uuid.UUID
) -> Optional[DepositAccountBalance]:
    return await session.get(DepositAccountBalance, account_id)


async def get_deposit_account_balance_with_account(
    session: AsyncSession, account_id: uuid.UUID
) -> Optional[DepositAccountBalance]:
    stmt = (
        select(DepositAccountBalance)
        .options(selectinload(DepositAccountBalance.account))
        .where(DepositAccountBalance.account_id == account_id)
    )
    return (await session.exec(stmt)).first()


async def list_deposit_account_balances(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,   
    account_ids: Optional[List[uuid.UUID]] = None,
    min_available: Optional[float] = None,  
    limit: int = 50,
    offset: int = 0,
    with_account: bool = False,
) -> List[DepositAccountBalance]:
    stmt = select(DepositAccountBalance)

    if wallet_id:
        stmt = stmt.join(DepositAccount).where(DepositAccount.wallet_id == wallet_id)

    if account_ids:
        stmt = stmt.where(DepositAccountBalance.account_id.in_(account_ids))

    if min_available is not None:
        stmt = stmt.where(DepositAccountBalance.available >= min_available)

    if with_account:
        stmt = stmt.options(selectinload(DepositAccountBalance.account))

    stmt = stmt.offset(offset).limit(limit)
    result = await session.exec(stmt)
    return result.all()


async def delete_deposit_account_balance(
    session: AsyncSession, account_id: uuid.UUID
) -> bool:
    bal = await session.get(DepositAccountBalance, account_id)
    if not bal:
        return False
    session.delete(bal)
    await session.commit()
    return True
