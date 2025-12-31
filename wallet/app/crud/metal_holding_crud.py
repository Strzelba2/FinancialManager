import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MetalHolding  
from app.schamas.schemas import MetalHoldingCreate, MetalHoldingUpdate
from app.models.enums import MetalType


METAL_TO_SYMBOL = {
    MetalType.GOLD: "GC.F",
    MetalType.SILVER: "SI.F",
    MetalType.PLATINUM: "PL.F",
    MetalType.PALLADIUM: "PA.F",
}


async def list_metal_holdings_by_wallet(
    session: AsyncSession,
    wallet_id: uuid.UUID,
) -> List[MetalHolding]:
    stmt = (
        select(MetalHolding)
        .where(MetalHolding.wallet_id == wallet_id)
        .order_by(MetalHolding.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_metal_holding(
    session: AsyncSession,
    metal_holding_id: uuid.UUID,
) -> Optional[MetalHolding]:
    stmt = select(MetalHolding).where(MetalHolding.id == metal_holding_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def create_metal_holding(
    session: AsyncSession,
    payload: MetalHoldingCreate,
) -> MetalHolding:
    obj = MetalHolding.model_validate(payload)

    if not getattr(obj, "quote_symbol", None):
        obj.quote_symbol = METAL_TO_SYMBOL.get(obj.metal)
        
    session.add(obj)
    await session.flush()  
    await session.refresh(obj) 
    return obj


async def update_metal_holding(
    session: AsyncSession,
    metal_holding_id: uuid.UUID,
    payload: MetalHoldingUpdate,
) -> Optional[MetalHolding]:
    obj = await get_metal_holding(session, metal_holding_id=metal_holding_id)
    if obj is None:
        return None

    if payload.grams is not None:
        obj.grams = payload.grams
    if payload.cost_basis is not None:
        obj.cost_basis = payload.cost_basis
    if payload.cost_currency is not None:
        obj.cost_currency = payload.cost_currency

    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def delete_metal_holding(
    session: AsyncSession,
    metal_holding_id: uuid.UUID,
) -> bool:
    obj = await get_metal_holding(session, metal_holding_id=metal_holding_id)
    if obj is None:
        return False
    await session.delete(obj)
    return True
