from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BrokerageAccount
from app.schamas.schemas import (
    BrokerageAccountCreate,
    BrokerageAccountUpdate,
)


async def create_brokerage_account(
    session: AsyncSession, data: BrokerageAccountCreate
) -> BrokerageAccount:
    obj = BrokerageAccount(**data.model_dump())  
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Brokerage account already exists for this wallet/bank/name.") from e
    await session.refresh(obj)
    return obj


async def get_brokerage_account(
    session: AsyncSession, account_id: uuid.UUID
) -> Optional[BrokerageAccount]:
    return await session.get(BrokerageAccount, account_id)


async def get_brokerage_account_with_relations(
    session: AsyncSession, account_id: uuid.UUID
) -> Optional[BrokerageAccount]:
    stmt = (
        select(BrokerageAccount)
        .options(
            selectinload(BrokerageAccount.bank),
            selectinload(BrokerageAccount.wallet),
            selectinload(BrokerageAccount.deposit_links),
            selectinload(BrokerageAccount.holdings),
        )
        .where(BrokerageAccount.id == account_id)
    )
    result = await session.execute(stmt)
    return result.first()


async def get_brokerage_by_wallet_bank_name(
    session: AsyncSession, wallet_id: uuid.UUID, bank_id: uuid.UUID, name: str
) -> Optional[BrokerageAccount]:
    stmt = select(BrokerageAccount).where(
        (BrokerageAccount.wallet_id == wallet_id)
        & (BrokerageAccount.bank_id == bank_id)
        & (BrokerageAccount.name == name)
    )
    return (await session.execute(stmt)).first()


async def list_brokerage_accounts(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,
    bank_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None, 
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
) -> List[BrokerageAccount]:
    stmt = select(BrokerageAccount)
    if wallet_id:
        stmt = stmt.where(BrokerageAccount.wallet_id == wallet_id)
    if bank_id:
        stmt = stmt.where(BrokerageAccount.bank_id == bank_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(BrokerageAccount.name.ilike(like))

    if with_relations:
        stmt = stmt.options(
            selectinload(BrokerageAccount.bank),
            selectinload(BrokerageAccount.wallet),
            selectinload(BrokerageAccount.deposit_links),
            selectinload(BrokerageAccount.holdings),
        )

    stmt = stmt.order_by(BrokerageAccount.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all() 


async def update_brokerage_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    data: BrokerageAccountUpdate,
) -> Optional[BrokerageAccount]:
    obj = await session.get(BrokerageAccount, account_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(obj, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Brokerage account update violates uniqueness constraints.") from e

    await session.refresh(obj)
    return obj


async def delete_brokerage_account(session: AsyncSession, account_id: uuid.UUID) -> bool:
    obj = await session.get(BrokerageAccount, account_id)
    if not obj:
        return False
    session.delete(obj)
    await session.commit()
    return True
