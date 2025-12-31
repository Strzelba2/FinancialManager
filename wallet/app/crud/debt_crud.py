import uuid
from typing import Sequence, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Debt
from app.schamas.schemas import DebtCreate, DebtUpdate


async def list_debts(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    limit: int = 10_000,
    offset: int = 0,
) -> Sequence[Debt]:
    """
    List debts for a wallet.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        limit: Max rows to return (clamped to >= 1).
        offset: Rows to skip (clamped to >= 0).

    Returns:
        Sequence of Debt ORM objects ordered by end_date asc, created_at desc.
    """
    stmt = (
        sa.select(Debt)
        .where(Debt.wallet_id == wallet_id)
        .order_by(Debt.end_date.asc(), Debt.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_debt(session: AsyncSession, debt_id: uuid.UUID) -> Optional[Debt]:
    """
    Fetch a single debt by id.

    Args:
        session: SQLAlchemy async session.
        debt_id: Debt UUID.

    Returns:
        Debt ORM object if found, otherwise None.
    """
    stmt = sa.select(Debt).where(Debt.id == debt_id)
    res = await session.execute(stmt)
    return res.scalars().first()


async def create_debt(session: AsyncSession, payload: DebtCreate) -> Debt:
    """
    Create a new debt row.

    Args:
        session: SQLAlchemy async session.
        payload: DebtCreate payload.

    Returns:
        Created Debt ORM object.
    """
    obj = Debt(**payload.model_dump())
    session.add(obj)
    await session.flush()    
    await session.refresh(obj)
    return obj


async def update_debt(
    session: AsyncSession,
    debt_id: uuid.UUID,
    payload: DebtUpdate,
) -> Optional[Debt]:
    """
    Update an existing debt row with a partial payload.

    Args:
        session: SQLAlchemy async session.
        debt_id: Debt UUID.
        payload: DebtUpdate payload (partial).

    Returns:
        Updated Debt ORM object, or None if not found.
    """
    obj = await get_debt(session, debt_id=debt_id)
    if not obj:
        return None

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        setattr(obj, k, v)

    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def delete_debt(session: AsyncSession, debt_id: uuid.UUID) -> bool:
    """
    Delete a debt row by id.

    Args:
        session: SQLAlchemy async session.
        debt_id: Debt UUID.

    Returns:
        True if deleted, False if not found.
    """
    obj = await get_debt(session, debt_id=debt_id)
    if not obj:
        return False
    await session.delete(obj)
    return True
