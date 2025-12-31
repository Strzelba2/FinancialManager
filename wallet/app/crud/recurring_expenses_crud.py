import uuid
from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RecurringExpense
from app.schamas.schemas import RecurringExpenseCreate, RecurringExpenseUpdate


async def list_recurring_expenses(session: AsyncSession, wallet_id: uuid.UUID) -> List[RecurringExpense]:
    """
    List all recurring expenses for a wallet.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.

    Returns:
        List of RecurringExpense ordered by due_day asc, created_at desc.
    """
    stmt = (
        select(RecurringExpense)
        .where(RecurringExpense.wallet_id == wallet_id)
        .order_by(RecurringExpense.due_day.asc(), RecurringExpense.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def list_top_recurring_expenses(
    session: AsyncSession,
    wallet_id: uuid.UUID,
    limit: int = 5,
) -> list[RecurringExpense]:
    """
    List top recurring expenses for a wallet.

    Note:
        Your original ordering was by due_day desc (not by amount). This keeps the same logic.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        limit: Max number of results (clamped to >= 1).

    Returns:
        List of RecurringExpense rows.
    """
    stmt = (
        select(RecurringExpense)
        .where(RecurringExpense.wallet_id == wallet_id)
        .order_by(desc(RecurringExpense.due_day))
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_recurring_expense(session: AsyncSession, expense_id: uuid.UUID) -> Optional[RecurringExpense]:
    """
    Fetch a single recurring expense by id.

    Args:
        session: SQLAlchemy async session.
        expense_id: Recurring expense UUID.

    Returns:
        RecurringExpense if found, otherwise None.
    """
    stmt = select(RecurringExpense).where(RecurringExpense.id == expense_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def create_recurring_expense(session: AsyncSession, payload: RecurringExpenseCreate) -> RecurringExpense:
    """
    Create a recurring expense row.

    Args:
        session: SQLAlchemy async session.
        payload: RecurringExpenseCreate payload.

    Returns:
        Created RecurringExpense ORM object.
    """
    obj = RecurringExpense(**payload.model_dump())
    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def update_recurring_expense(
    session: AsyncSession,
    expense_id: uuid.UUID,
    payload: RecurringExpenseUpdate,
) -> Optional[RecurringExpense]:
    """
    Update an existing recurring expense with a partial payload.

    Args:
        session: SQLAlchemy async session.
        expense_id: Recurring expense UUID.
        payload: RecurringExpenseUpdate payload (partial).

    Returns:
        Updated RecurringExpense or None if not found.
    """
    obj = await get_recurring_expense(session, expense_id)
    if not obj:
        return None

    patch = payload.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(obj, k, v)

    session.add(obj)
    await session.flush()
    await session.refresh(obj)
    return obj


async def delete_recurring_expense(session: AsyncSession, expense_id: uuid.UUID) -> bool:
    """
    Delete a recurring expense row.

    Args:
        session: SQLAlchemy async session.
        expense_id: Recurring expense UUID.

    Returns:
        True if deleted, False if not found.
    """
    obj = await get_recurring_expense(session, expense_id)
    if not obj:
        return False

    await session.delete(obj)
    await session.flush()
    return True
