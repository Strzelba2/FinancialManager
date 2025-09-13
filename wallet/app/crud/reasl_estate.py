from __future__ import annotations
import uuid
from decimal import Decimal
from typing import Optional, List

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


async def create_real_estate(session: AsyncSession, data: RealEstateCreate) -> RealEstate:
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
    return await session.get(RealEstate, re_id)


async def get_real_estate_with_wallet(session: AsyncSession, re_id: uuid.UUID) -> Optional[RealEstate]:
    stmt = (
        select(RealEstate)
        .options(selectinload(RealEstate.wallet))
        .where(RealEstate.id == re_id)
    )
    result = await session.exec(stmt)
    return result.first()


async def list_real_estates(
    session: AsyncSession,
    *,
    wallet_id: Optional[uuid.UUID] = None,
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
    stmt = select(RealEstate)

    if wallet_id:
        stmt = stmt.where(RealEstate.wallet_id == wallet_id)
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

    result = await session.exec(stmt)
    return result.all()


async def update_real_estate(
    session: AsyncSession,
    re_id: uuid.UUID,
    data: RealEstateUpdate,
) -> Optional[RealEstate]:
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
    obj = await session.get(RealEstate, re_id)
    if not obj:
        return False
    session.delete(obj)
    await session.commit()
    return True
