from __future__ import annotations
import uuid
from typing import Optional, List

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Instrument
from app.schamas.schemas import InstrumentCreate, InstrumentUpdate
from app.models.enums import InstrumentType, Currency


async def create_instrument(session: AsyncSession, data: InstrumentCreate) -> Instrument:
    obj = Instrument(**data.model_dump()) 
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Instrument with this symbol already exists.") from e
    await session.refresh(obj)
    return obj


async def get_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> Optional[Instrument]:
    return await session.get(Instrument, instrument_id)


async def get_instrument_by_symbol(session: AsyncSession, symbol: str) -> Optional[Instrument]:
    result = await session.exec(select(Instrument).where(Instrument.symbol == symbol.upper()))
    return result.first()


async def list_instruments(
    session: AsyncSession,
    *,
    types: Optional[List[InstrumentType]] = None,
    currency: Optional[Currency] = None,
    search: Optional[str] = None, 
    limit: int = 50,
    offset: int = 0,
    order_by_symbol: bool = True, 
) -> List[Instrument]:
    stmt = select(Instrument)

    if types:
        stmt = stmt.where(Instrument.type.in_(types))
    if currency:
        stmt = stmt.where(Instrument.currency == currency)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Instrument.symbol.ilike(like) | Instrument.name.ilike(like))

    stmt = stmt.order_by(Instrument.symbol.asc() if order_by_symbol else Instrument.name.asc())
    stmt = stmt.offset(offset).limit(limit)

    result = await session.exec(stmt)
    return result.all()


async def update_instrument(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    data: InstrumentUpdate,
) -> Optional[Instrument]:
    obj = await session.get(Instrument, instrument_id)
    if not obj:
        return None

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(obj, field, value) 

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Instrument update violates uniqueness (symbol).") from e

    await session.refresh(obj)
    return obj


async def delete_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> bool:
    obj = await session.get(Instrument, instrument_id)
    if not obj:
        return False
    session.delete(obj)
    await session.commit()
    return True
