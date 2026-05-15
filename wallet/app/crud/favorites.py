from __future__ import annotations

import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from sqlalchemy.orm import selectinload

from app.models.models import FavoriteList, FavoriteItem, Instrument, PriceAlert


async def list_favorite_lists(session: AsyncSession, user_id: uuid.UUID) -> list[FavoriteList]:
    stmt = (
        select(FavoriteList)
        .where(FavoriteList.user_id == user_id)
        .order_by(FavoriteList.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_favorite_list(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
) -> Optional[FavoriteList]:
    obj = await session.get(FavoriteList, list_id)
    if not obj or obj.user_id != user_id:
        return None
    return obj


async def create_favorite_list(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    description: Optional[str] = None,
) -> FavoriteList:
    clean_name = name.strip()
    stmt = select(FavoriteList).where(
        FavoriteList.user_id == user_id,
        FavoriteList.name == clean_name,
    )
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        raise ValueError("Favorite list with this name already exists for this user.")

    obj = FavoriteList(
        user_id=user_id,
        name=clean_name,
        description=(description.strip() if description else None),
    )
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Favorite list with this name already exists for this user.") from e

    await session.refresh(obj)
    return obj


async def update_favorite_list(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[FavoriteList]:
    obj = await get_favorite_list(session, user_id, list_id)
    if not obj:
        return None

    if name is not None:
        obj.name = name.strip()
    if description is not None:
        obj.description = description.strip() if description else None

    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def delete_favorite_list(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
) -> bool:
    obj = await get_favorite_list(session, user_id, list_id)
    if not obj:
        return False
    await session.delete(obj)
    await session.commit()
    return True


async def add_favorite_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> FavoriteItem:
    lst = await get_favorite_list(session, user_id, list_id)
    if not lst:
        raise ValueError("Favorite list not found or not owned by user")

    instr = await session.get(Instrument, instrument_id)
    if not instr:
        raise ValueError("Instrument not found")

    stmt = select(FavoriteItem).where(
        FavoriteItem.favorite_list_id == list_id,
        FavoriteItem.instrument_id == instrument_id,
    )
    res = await session.execute(stmt)
    existing = res.scalars().first()
    if existing:
        return existing

    obj = FavoriteItem(favorite_list_id=list_id, instrument_id=instrument_id)
    session.add(obj)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        
        res = await session.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return existing
        raise

    await session.refresh(obj)
    return obj


async def remove_favorite_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> bool:
    lst = await get_favorite_list(session, user_id, list_id)
    if not lst:
        return False

    stmt = select(FavoriteItem).where(
        FavoriteItem.favorite_list_id == list_id,
        FavoriteItem.instrument_id == instrument_id,
    )
    res = await session.execute(stmt)
    obj = res.scalars().first()
    if not obj:
        return False

    await session.delete(obj)
    await session.commit()
    return True


async def list_favorite_items(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
) -> list[FavoriteItem]:
    lst = await get_favorite_list(session, user_id, list_id)
    if not lst:
        return []

    stmt = (
        select(FavoriteItem)
        .where(FavoriteItem.favorite_list_id == list_id)
        .order_by(FavoriteItem.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_last_favorite_items_for_user(
    session: AsyncSession,
    user_id,
    limit: int = 5,
) -> List[FavoriteItem]:

    q = (
        select(FavoriteItem)
        .join(FavoriteList, FavoriteItem.favorite_list_id == FavoriteList.id)
        .where(FavoriteList.user_id == user_id)
        .order_by(desc(getattr(FavoriteItem, "created_at", FavoriteItem.id)))
        .limit(limit)
        .options(selectinload(FavoriteItem.instrument))
    )

    res = await session.execute(q)
    return list(res.scalars().all())


async def list_favorite_items_with_alerts(
    session: AsyncSession,
    user_id: uuid.UUID,
    list_id: uuid.UUID,
) -> list[dict]:

    lst = await get_favorite_list(session, user_id, list_id)
    if not lst:
        return []

    stmt = (
        select(
            FavoriteItem.id,
            FavoriteItem.instrument_id,
            Instrument.symbol,
            Instrument.mic,
            Instrument.name,
            Instrument.currency,
            Instrument.type,
            PriceAlert.enabled,
            PriceAlert.below_price,
            PriceAlert.above_price,
            PriceAlert.one_shot,
            PriceAlert.expires_at,
        )
        .join(Instrument, Instrument.id == FavoriteItem.instrument_id)
        .outerjoin(
            PriceAlert,
            (PriceAlert.instrument_id == FavoriteItem.instrument_id)
            & (PriceAlert.user_id == user_id),
        )
        .where(FavoriteItem.favorite_list_id == list_id)
        .order_by(Instrument.symbol.asc())
    )

    res = await session.execute(stmt)
    rows = res.all()

    out: list[dict] = []
    for r in rows:
        (
            fav_item_id,
            instrument_id,
            symbol,
            mic,
            name,
            currency,
            instr_type,
            alert_enabled,
            below_price,
            above_price,
            one_shot,
            expires_at,
        ) = r

        alert = None
        if alert_enabled is not None or below_price is not None or above_price is not None:
            alert = {
                "enabled": bool(alert_enabled),
                "below_price": below_price,
                "above_price": above_price,
                "one_shot": bool(one_shot) if one_shot is not None else False,
                "expires_at": expires_at,
            }

        out.append(
            {
                "favorite_item_id": fav_item_id,
                "instrument_id": instrument_id,
                "symbol": symbol,
                "mic": mic,
                "name": name,
                "currency": currency,
                "type": instr_type,
                "alert": alert,
            }
        )

    return out
