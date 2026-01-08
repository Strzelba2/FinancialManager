from __future__ import annotations
import uuid
from decimal import Decimal
from typing import Optional, List
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RealEstate
from app.schamas.schemas import (
    RealEstateCreate,
    RealEstateUpdate,
)
from app.models.enums import PropertyType

logger = logging.getLogger(__name__)


async def create_real_estate(session: AsyncSession, data: RealEstateCreate) -> RealEstate:
    """
    Create a RealEstate row.

    Notes:
        This function does NOT commit. The caller should manage the transaction
        (e.g., `async with session.begin(): ...`).

    Args:
        session: SQLAlchemy async session.
        data: RealEstateCreate payload.

    Returns:
        Created RealEstate ORM object.

    Raises:
        ValueError: if constraints / FK fail (mapped from IntegrityError).
    """
    obj = RealEstate(**data.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Could not create real estate (invalid wallet or constraints).") from e
    await session.refresh(obj)
    return obj


async def get_real_estate(session: AsyncSession, re_id: uuid.UUID) -> Optional[RealEstate]:
    """
    Fetch a RealEstate by id.

    Args:
        session: SQLAlchemy async session.
        re_id: RealEstate UUID.

    Returns:
        RealEstate or None.
    """
    return await session.get(RealEstate, re_id)


async def get_real_estate_with_wallet(session: AsyncSession, re_id: uuid.UUID) -> Optional[RealEstate]:
    """
    Fetch a RealEstate by id with its wallet relationship eagerly loaded.

    Args:
        session: SQLAlchemy async session.
        re_id: RealEstate UUID.

    Returns:
        RealEstate or None.
    """
    stmt = (
        select(RealEstate)
        .options(selectinload(RealEstate.wallet))
        .where(RealEstate.id == re_id)
    )
    result = await session.execute(stmt)
    return result.first()


async def list_real_estates(
    session: AsyncSession,
    wallet_id: Optional[uuid.UUID] = None,
    wallet_ids: Optional[list[uuid.UUID]] = None,
    country: Optional[str] = None,
    city: Optional[str] = None,
    types: Optional[List[PropertyType]] = None,
    min_area: Optional[Decimal] = None,
    max_area: Optional[Decimal] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    search: Optional[str] = None, 
    limit: int = 50,
    offset: int = 0,
    newest_first: bool = True,
    with_wallet: bool = False,
) -> List[RealEstate]:
    """
    List real estates with optional filtering.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Optional wallet filter.
        wallet_ids: Optional wallets filter.
        country: Optional country filter (normalized to upper).
        city: Optional city filter (ILIKE).
        types: Optional property type filter.
        min_area/max_area: Optional area filters (m²).
        min_price/max_price: Optional purchase price filters.
        search: Optional free-text search applied to name or city.
        limit: Max rows (clamped to >=1).
        offset: Offset (clamped to >=0).
        newest_first: Order by created_at desc if True else asc.
        with_wallet: If True, eager-load wallet relation.

    Returns:
        List of RealEstate ORM objects.
    """
    stmt = select(RealEstate)

    if wallet_id:
        stmt = stmt.where(RealEstate.wallet_id == wallet_id)
    if wallet_ids:
        stmt = stmt.where(RealEstate.wallet_id.in_(wallet_ids))
    if country:
        stmt = stmt.where(RealEstate.country == country.upper())
    if city:
        stmt = stmt.where(RealEstate.city.ilike(city)) 
    if types:
        stmt = stmt.where(RealEstate.type.in_(types))
    if min_area is not None:
        stmt = stmt.where(RealEstate.area_m2 >= min_area)
    if max_area is not None:
        stmt = stmt.where(RealEstate.area_m2 <= max_area)
    if min_price is not None:
        stmt = stmt.where(RealEstate.purchase_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(RealEstate.purchase_price <= max_price)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(RealEstate.name.ilike(like) | RealEstate.city.ilike(like))

    if with_wallet:
        stmt = stmt.options(selectinload(RealEstate.wallet))

    stmt = stmt.order_by(
        RealEstate.created_at.desc() if newest_first else RealEstate.created_at.asc()
    ).offset(offset).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_real_estate(
    session: AsyncSession,
    re_id: uuid.UUID,
    data: RealEstateUpdate,
) -> Optional[RealEstate]:
    """
    Update a RealEstate row.

    Notes:
        No internal commit; caller manages transaction.

    Args:
        session: SQLAlchemy async session.
        re_id: RealEstate UUID.
        data: RealEstateUpdate payload.

    Returns:
        Updated RealEstate or None if not found.

    Raises:
        ValueError: if constraints fail (mapped from IntegrityError).
    """
    obj = await session.get(RealEstate, re_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Failed to update real estate (constraint violation).") from e

    await session.refresh(obj)
    return obj


async def delete_real_estate(session: AsyncSession, re_id: uuid.UUID) -> bool:
    """
    Delete a RealEstate row.

    Notes:
        No internal commit; caller manages transaction.

    Args:
        session: SQLAlchemy async session.
        re_id: RealEstate UUID.

    Returns:
        True if deleted, False if not found.
    """
    obj = await session.get(RealEstate, re_id)
    
    if not obj:
        return False

    await session.delete(obj)
    await session.commit()
    return True
