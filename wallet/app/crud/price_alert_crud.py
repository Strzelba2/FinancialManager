from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.models.models import PriceAlert, Instrument
from app.schamas.schemas import PriceAlertUpdate  


async def get_alert(
    session: AsyncSession,
    user_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> Optional[PriceAlert]:
    stmt = select(PriceAlert).where(
        PriceAlert.user_id == user_id,
        PriceAlert.instrument_id == instrument_id,
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def upsert_alert(
    session: AsyncSession,
    user_id: uuid.UUID,
    instrument_id: uuid.UUID,
    below_price: Optional[Decimal],
    above_price: Optional[Decimal],
    enabled: bool = True,
    one_shot: bool = False,
    expires_at: Optional[datetime] = None,
) -> PriceAlert:

    if below_price is None and above_price is None:
        raise ValueError("Provide below_price and/or above_price.")
    if below_price is not None and below_price < 0:
        raise ValueError("below_price must be >= 0.")
    if above_price is not None and above_price < 0:
        raise ValueError("above_price must be >= 0.")
    if below_price is not None and above_price is not None and below_price >= above_price:
        raise ValueError("below_price must be < above_price when both are set.")

    instr = await session.get(Instrument, instrument_id)
    if not instr:
        raise ValueError("Instrument not found")

    obj = await get_alert(session, user_id, instrument_id)
    if obj:
        obj.below_price = below_price
        obj.above_price = above_price
        obj.enabled = enabled
        obj.one_shot = one_shot
        obj.expires_at = expires_at

        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    obj = PriceAlert(
        user_id=user_id,
        instrument_id=instrument_id,
        below_price=below_price,
        above_price=above_price,
        enabled=enabled,
        one_shot=one_shot,
        expires_at=expires_at,
    )

    session.add(obj)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()

        existing = await get_alert(session, user_id, instrument_id)
        if existing:
            return existing
        raise

    await session.refresh(obj)
    return obj


async def patch_alert(
    session: AsyncSession,
    user_id: uuid.UUID,
    instrument_id: uuid.UUID,
    body: PriceAlertUpdate,
) -> Optional[PriceAlert]:

    current = await get_alert(session, user_id, instrument_id)
    if not current:
        return None

    patch: Dict[str, Any] = body.model_dump(exclude_unset=True)

    for k, v in patch.items():
        setattr(current, k, v)

    below = current.below_price
    above = current.above_price

    if below is None and above is None:
        raise ValueError("Provide below_price and/or above_price (you cannot clear both).")

    if below is not None and Decimal(below) < 0:
        raise ValueError("below_price must be >= 0.")
    if above is not None and Decimal(above) < 0:
        raise ValueError("above_price must be >= 0.")

    if below is not None and above is not None and Decimal(below) >= Decimal(above):
        raise ValueError("below_price must be < above_price when both are set.")

    try:
        session.add(current)
        await session.commit()
        await session.refresh(current)
        return current
    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"DB constraint failed: {e.orig}") from e


async def delete_alert(
    session: AsyncSession,
    user_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> bool:
    obj = await get_alert(session, user_id, instrument_id)
    if not obj:
        return False

    await session.delete(obj)
    await session.commit()
    return True


async def list_alerts(session: AsyncSession, user_id: uuid.UUID) -> list[PriceAlert]:
    stmt = (
        select(PriceAlert)
        .where(PriceAlert.user_id == user_id)
        .order_by(PriceAlert.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_alerts_with_symbols(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int | None = None,
) -> list[tuple[PriceAlert, str | None]]:
    stmt = (
        select(PriceAlert, Instrument.symbol)
        .outerjoin(Instrument, Instrument.id == PriceAlert.instrument_id)  
        .where(PriceAlert.user_id == user_id)
        .order_by(PriceAlert.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)

    res = await session.execute(stmt)
    return [(a, sym) for (a, sym) in res.all()]


async def list_last_price_alerts_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 5,
) -> List[PriceAlert]:
    stmt = (
        select(PriceAlert)
        .options(selectinload(PriceAlert.instrument))  
        .where(PriceAlert.user_id == user_id)
        .order_by(PriceAlert.created_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
