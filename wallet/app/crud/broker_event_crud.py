from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid

from app.models.models import BrokerageEvent
from app.schamas.schemas import BrokerageEventCreate


async def create_brokerage_event(session: AsyncSession, data: BrokerageEventCreate, instrument_id: uuid.UUID ) -> BrokerageEvent:
    obj = BrokerageEvent(
        brokerage_account_id=data.brokerage_account_id,
        instrument_id=instrument_id,
        kind=data.kind,
        quantity=data.quantity,
        price=data.price,
        currency=data.currency,
        split_ratio=data.split_ratio,
        trade_at=data.trade_at,
    )
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError(f"Broker event already exists for this account & instrument, or invalid FK. {e}") from e
    await session.refresh(obj)
    return obj


async def find_duplicate_brokerage_event(
    session: AsyncSession,
    data: BrokerageEventCreate,
    instrument_id: uuid.UUID,
) -> Optional[BrokerageEvent]:
    stmt = (
        select(BrokerageEvent)
        .where(
            BrokerageEvent.brokerage_account_id == data.brokerage_account_id,
            BrokerageEvent.instrument_id == instrument_id,
            BrokerageEvent.kind == data.kind,
            BrokerageEvent.trade_at == data.trade_at,
            BrokerageEvent.quantity == data.quantity,
            BrokerageEvent.price == data.price,
            BrokerageEvent.currency == data.currency,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()