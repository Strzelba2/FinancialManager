from __future__ import annotations
import uuid
from typing import Optional, List
from decimal import Decimal
from fastapi import HTTPException, status

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Holding, Instrument, BrokerageAccount, Wallet
from app.models.enums import BrokerageEventKind
from app.schamas.schemas import (
    HoldingCreate, HoldingUpdate, BrokerageEventCreate
)


async def create_holding(session: AsyncSession, data: HoldingCreate) -> Holding:
    obj = Holding(**data.model_dump())
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Holding already exists for this account & instrument, or invalid FK.") from e
    await session.refresh(obj)
    return obj


async def get_or_create_holding(
    session: AsyncSession,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
) -> Holding:
    stmt = (
        select(Holding)
        .where(
            Holding.account_id == account_id,
            Holding.instrument_id == instrument_id,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    holding = result.scalar_one_or_none()

    if holding is None:
        data = HoldingCreate(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=Decimal("0"),
            avg_cost=Decimal("0"),
        )
        holding = await create_holding(session, data)

    return holding


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
    account_id: Optional[uuid.UUID] = None,
    account_ids: Optional[list[uuid.UUID]] = None,
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
    if account_ids:
        stmt = stmt.where(Holding.account_id.in_(account_ids))
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
    return list(result.scalars().unique().all())


async def list_holdings_rows_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    brokerage_account_ids: Optional[list[uuid.UUID]] = None,
    q: Optional[str] = None,
) -> list[dict]:
    stmt = (
        select(
            BrokerageAccount.id.label("account_id"),
            BrokerageAccount.name.label("account_name"),
            Instrument.id.label("instrument_id"),
            Instrument.symbol.label("instrument_symbol"),
            Instrument.name.label("instrument_name"),
            Instrument.currency.label("instrument_currency"),
            Holding.quantity.label("quantity"),
            Holding.avg_cost.label("avg_cost"),
        )
        .select_from(Holding)
        .join(BrokerageAccount, BrokerageAccount.id == Holding.account_id)
        .join(Wallet, Wallet.id == BrokerageAccount.wallet_id)
        .join(Instrument, Instrument.id == Holding.instrument_id)
        .where(Wallet.user_id == user_id)
    )

    if brokerage_account_ids:
        stmt = stmt.where(Holding.account_id.in_(brokerage_account_ids))

    if q:
        q_like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Instrument.symbol.ilike(q_like),
                Instrument.name.ilike(q_like),
            )
        )

    stmt = stmt.order_by(Instrument.symbol.asc(), BrokerageAccount.name.asc())

    res = await session.execute(stmt)
    rows = res.mappings().all()  
    return [dict(r) for r in rows]


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


def apply_event_to_holding(
    holding: Holding,
    payload: BrokerageEventCreate,
) -> None:

    kind = payload.kind
    qty = Decimal(payload.quantity)
    price = Decimal(payload.price)
    ratio = Decimal(payload.split_ratio)

    old_qty = Decimal(holding.quantity)
    old_avg = Decimal(holding.avg_cost)

    if kind == BrokerageEventKind.TRADE_BUY:
        if qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BUY quantity must be positive.",
            )

        new_qty = old_qty + qty
        if new_qty == 0:
            holding.quantity = Decimal("0")
            holding.avg_cost = Decimal("0")
        else:
            total_cost_old = old_qty * old_avg
            total_cost_new = qty * price
            holding.quantity = new_qty
            holding.avg_cost = (total_cost_old + total_cost_new) / new_qty

    elif kind == BrokerageEventKind.TRADE_SELL:
        if qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SELL quantity must be positive.",
            )

        new_qty = old_qty - qty
        if new_qty < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot sell more than holding quantity.",
            )
        holding.quantity = new_qty

    elif kind == BrokerageEventKind.SPLIT:
        if ratio <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Split ratio must be > 0.",
            )
        holding.quantity = old_qty * ratio
        holding.avg_cost = old_avg / ratio if ratio != 0 else old_avg

    elif kind == BrokerageEventKind.DIV:
        return

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported brokerage event kind: {kind}",
        )
