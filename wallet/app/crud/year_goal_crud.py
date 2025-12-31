import uuid
from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import YearGoal
from app.schamas.schemas import YearGoalCreate, YearGoalUpdate


async def get_year_goal(session: AsyncSession, wallet_id: uuid.UUID, year: int) -> Optional[YearGoal]:
    """
    Get a year goal for a given wallet and year.

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        year: Goal year.

    Returns:
        YearGoal if found, otherwise None.
    """
    stmt = select(YearGoal).where(YearGoal.wallet_id == wallet_id, YearGoal.year == year)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_year_goals(session: AsyncSession, wallet_id: uuid.UUID) -> List[YearGoal]:
    """
    List all year goals for a wallet (newest year first).

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.

    Returns:
        List of YearGoal objects ordered by year desc.
    """
    stmt = select(YearGoal).where(YearGoal.wallet_id == wallet_id).order_by(YearGoal.year.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_year_goal(session: AsyncSession, payload: YearGoalCreate) -> YearGoal:
    """
    Create a year goal.

    Notes:
        Uses flush() but does not commit.

    Args:
        session: SQLAlchemy async session.
        payload: YearGoalCreate payload.

    Returns:
        Created YearGoal ORM object.
    """
    obj = YearGoal(**payload.model_dump())
    session.add(obj)
    await session.flush()
    return obj


async def upsert_year_goal(session: AsyncSession, payload: YearGoalCreate) -> YearGoal:
    """
    Upsert (insert or update) a year goal by (wallet_id, year).

    If goal exists -> updates rev_target_year, exp_budget_year, currency.
    If missing -> creates a new row.

    Args:
        session: SQLAlchemy async session.
        payload: YearGoalCreate payload.

    Returns:
        Created/updated YearGoal ORM object.
    """
    obj = await get_year_goal(session, wallet_id=payload.wallet_id, year=payload.year)
    if obj is None:
        return await create_year_goal(session, payload=payload)

    obj.rev_target_year = payload.rev_target_year
    obj.exp_budget_year = payload.exp_budget_year
    obj.currency = payload.currency
    session.add(obj)
    await session.flush()
    return obj


async def update_year_goal(session: AsyncSession, goal_id: uuid.UUID, patch: YearGoalUpdate) -> Optional[YearGoal]:
    """
    Patch-update a year goal by id.

    Args:
        session: SQLAlchemy async session.
        goal_id: YearGoal UUID.
        patch: Partial update payload.

    Returns:
        Updated YearGoal or None if not found.
    """
    obj = await session.get(YearGoal, goal_id)
    if obj is None:
        return None

    data = patch.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)

    session.add(obj)
    await session.flush()
    return obj


async def delete_year_goal(session: AsyncSession, goal_id: uuid.UUID) -> bool:
    """
    Delete a year goal by id.

    Args:
        session: SQLAlchemy async session.
        goal_id: YearGoal UUID.

    Returns:
        True if deleted, False if not found.
    """
    obj = await session.get(YearGoal, goal_id)
    if obj is None:
        return False
    await session.delete(obj)
    await session.flush()
    return True
