from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Holding, Instrument, BrokerageAccount
from app.schamas.schemas import (
    HoldingCreate,
    HoldingUpdate,
)


async def create_holding(session: AsyncSession, data: HoldingCreate) -> Holding:
    obj = Holding(**data.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Holding already exists for this account & instrument, or invalid FK.") from e
    await session.refresh(obj)
    return obj


async def get_holding(session: AsyncSession, holding_id: uuid.UUID) -> Optional[Holding]:
    return await session.get(Holding, holding_id)


async def get_holding_by_keys(
    session: AsyncSession, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> Optional[Holding]:
    stmt = select(Holding).where(
        (Holding.account_id == account_id) & (Holding.instrument_id == instrument_id)
    )
    return (await session.execute(stmt)).first()


async def get_holding_with_relations(
    session: AsyncSession, holding_id: uuid.UUID
) -> Optional[Holding]:
    stmt = (
        select(Holding)
        .options(
            selectinload(Holding.account),
            selectinload(Holding.instrument),
        )
        .where(Holding.id == holding_id)
    )
    return (await session.execute(stmt)).first()


async def list_holdings(
    session: AsyncSession,
    *,
    account_id: Optional[uuid.UUID] = None,
    instrument_id: Optional[uuid.UUID] = None,
    wallet_id: Optional[uuid.UUID] = None, 
    instrument_symbol: Optional[str] = None, 
    min_quantity: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    with_relations: bool = False,
) -> List[Holding]:
    stmt = select(Holding)

    if account_id:
        stmt = stmt.where(Holding.account_id == account_id)
    if instrument_id:
        stmt = stmt.where(Holding.instrument_id == instrument_id)
    if wallet_id:
        stmt = stmt.join(BrokerageAccount).where(BrokerageAccount.wallet_id == wallet_id)
    if instrument_symbol:
        stmt = stmt.join(Instrument).where(Instrument.symbol.ilike(instrument_symbol))

    if min_quantity is not None:
        stmt = stmt.where(Holding.quantity >= min_quantity)

    if with_relations:
        stmt = stmt.options(
            selectinload(Holding.account),
            selectinload(Holding.instrument),
        )

    stmt = stmt.order_by(Holding.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.all()


async def update_holding(
    session: AsyncSession,
    holding_id: uuid.UUID,
    data: HoldingUpdate,
) -> Optional[Holding]:
    obj = await session.get(Holding, holding_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Failed to update holding.") from e

    await session.refresh(obj)
    return obj


async def delete_holding(session: AsyncSession, holding_id: uuid.UUID) -> bool:
    obj = await session.get(Holding, holding_id)
    if not obj:
        return False
    session.delete(obj)
    await session.commit()
    return True
