from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MetalHolding
from app.schamas.schemas import (
    MetalHoldingCreate,
    MetalHoldingUpdate,
)
from app.models.enums import MetalType


async def create_metal_holding(
    session: AsyncSession, data: MetalHoldingCreate
) -> MetalHolding:
    obj = MetalHolding(**data.model_dump())  
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Metal holding already exists for this wallet and metal, or invalid wallet_id.") from e
    await session.refresh(obj)
    return obj


async def get_metal_holding(
    session: AsyncSession, holding_id: uuid.UUID
) -> Optional[MetalHolding]:
    return await session.get(MetalHolding, holding_id)


async def get_metal_holding_by_wallet_and_metal(
    session: AsyncSession, wallet_id: uuid.UUID, metal: MetalType
) -> Optional[MetalHolding]:
    stmt = select(MetalHolding).where(
        (MetalHolding.wallet_id == wallet_id) & (MetalHolding.metal == metal)
    )
    return (await session.execute(stmt)).first()


async def get_metal_holding_with_wallet(
    session: AsyncSession, holding_id: uuid.UUID
) -> Optional[MetalHolding]:
    stmt = (
        select(MetalHolding)
        .options(selectinload(MetalHolding.wallet))
        .where(MetalHolding.id == holding_id)
    )
    return (await session.execute(stmt)).first()


async def list_metal_holdings(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,
    metals: Optional[List[MetalType]] = None,
    min_grams: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    with_wallet: bool = False,
) -> List[MetalHolding]:
    stmt = select(MetalHolding)

    if wallet_id:
        stmt = stmt.where(MetalHolding.wallet_id == wallet_id)
    if metals:
        stmt = stmt.where(MetalHolding.metal.in_(metals))
    if min_grams is not None:
        stmt = stmt.where(MetalHolding.grams >= min_grams)

    if with_wallet:
        stmt = stmt.options(selectinload(MetalHolding.wallet))

    stmt = stmt.order_by(MetalHolding.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.all()


async def update_metal_holding(
    session: AsyncSession,
    holding_id: uuid.UUID,
    data: MetalHoldingUpdate,
) -> Optional[MetalHolding]:
    obj = await session.get(MetalHolding, holding_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Failed to update metal holding (unique/constraint violation).") from e

    await session.refresh(obj)
    return obj


async def delete_metal_holding(session: AsyncSession, holding_id: uuid.UUID) -> bool:
    obj = await session.get(MetalHolding, holding_id)
    if not obj:
        return False
    session.delete(obj)
    await session.commit()
    return True
