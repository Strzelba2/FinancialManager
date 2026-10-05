import uuid
from typing import Sequence, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CashHolding
from app.schemas.schemas import CashHoldingCreate, CashHoldingUpdate


async def list_cash_holdings(
    session: AsyncSession,
    wallet_id: uuid.UUID,
) -> Sequence[CashHolding]:
    """
    List physical cash holdings for a wallet.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.

    Returns:
        Sequence of CashHolding ORM objects ordered by created_at asc.
    """
    stmt = (
        sa.select(CashHolding)
        .where(CashHolding.wallet_id == wallet_id)
        .order_by(CashHolding.created_at.asc(), CashHolding.id.asc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def list_cash_holdings_for_wallets(
    session: AsyncSession,
    wallet_ids: list[uuid.UUID],
) -> Sequence[CashHolding]:
    """
    List physical cash holdings for several wallets.

    Args:
        session: SQLAlchemy async session.
        wallet_ids: Wallet UUIDs.

    Returns:
        Sequence of CashHolding ORM objects ordered by wallet and created_at.
    """
    if not wallet_ids:
        return []
    stmt = (
        sa.select(CashHolding)
        .where(CashHolding.wallet_id.in_(wallet_ids))
        .order_by(CashHolding.wallet_id, CashHolding.created_at.asc(), CashHolding.id.asc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_cash_holding(session: AsyncSession, cash_holding_id: uuid.UUID) -> Optional[CashHolding]:
    """
    Fetch a single physical cash holding by id.

    Args:
        session: SQLAlchemy async session.
        cash_holding_id: CashHolding UUID.

    Returns:
        CashHolding ORM object if found, otherwise None.
    """
    stmt = sa.select(CashHolding).where(CashHolding.id == cash_holding_id)
    res = await session.execute(stmt)
    return res.scalars().first()


async def create_cash_holding(session: AsyncSession, payload: CashHoldingCreate) -> CashHolding:
    """
    Create a new physical cash holding row.

    Args:
        session: SQLAlchemy async session.
        payload: CashHoldingCreate payload.

    Returns:
        Created CashHolding ORM object.
    """
    obj = CashHolding(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def update_cash_holding(
    session: AsyncSession,
    cash_holding_id: uuid.UUID,
    payload: CashHoldingUpdate,
) -> Optional[CashHolding]:
    """
    Update an existing physical cash holding with a partial payload.

    `name`, `amount` and `currency` are ignored when sent as null; `note` sent as
    null or empty clears the note.

    Args:
        session: SQLAlchemy async session.
        cash_holding_id: CashHolding UUID.
        payload: CashHoldingUpdate payload (partial).

    Returns:
        Updated CashHolding ORM object, or None if not found.
    """
    obj = await get_cash_holding(session, cash_holding_id=cash_holding_id)
    if not obj:
        return None

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is None and k != "note":
            continue
        setattr(obj, k, v)

    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def delete_cash_holding(session: AsyncSession, cash_holding_id: uuid.UUID) -> bool:
    """
    Delete a physical cash holding by id.

    Args:
        session: SQLAlchemy async session.
        cash_holding_id: CashHolding UUID.

    Returns:
        True if deleted, False if not found.
    """
    obj = await get_cash_holding(session, cash_holding_id=cash_holding_id)
    if not obj:
        return False
    await session.delete(obj)
    return True
