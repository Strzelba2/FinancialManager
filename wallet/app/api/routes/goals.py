from fastapi import APIRouter, Depends, HTTPException, Query
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.wallet_crud import get_wallet
from app.crud.year_goal_crud import (
    get_year_goal, list_year_goals, upsert_year_goal, 
    update_year_goal, delete_year_goal
    )
from app.api.services.transactions import compute_wallet_ytd_income_expense_maps
from app.schamas.schemas import YearGoalCreate, YearGoalRead, YearGoalUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{wallet_id}/goals", response_model=Optional[YearGoalRead])
async def get_goals_for_wallet_year(
    wallet_id: uuid.UUID,
    year: int = Query(default=datetime.now(timezone.utc).year),
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> Optional[YearGoalRead]:
    """
    Get the yearly goal for a specific wallet and year.

    Args:
        wallet_id: Wallet UUID.
        year: Target year (defaults to current UTC year).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        YearGoalRead if it exists, otherwise None.

    Raises:
        HTTPException(404): if the wallet does not exist or is not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/goals: start")
    w = await get_wallet(session, wallet_id)
    if not w or w.user_id != user_id:
        raise HTTPException(status_code=404, detail="Wallet not found")

    obj = await get_year_goal(session, wallet_id=wallet_id, year=year)
    return YearGoalRead.model_validate(obj) if obj else None


@router.get("/{wallet_id}/goals/all", response_model=List[YearGoalRead])
async def list_goals_for_wallet(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> List[YearGoalRead]:
    """
    List all yearly goals for a wallet.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        List of YearGoalRead rows.

    Raises:
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/goals/all: start")
    w = await get_wallet(session, wallet_id)
    if not w or w.user_id != user_id:
        raise HTTPException(status_code=404, detail="Wallet not found")

    rows = await list_year_goals(session, wallet_id=wallet_id)
    return [YearGoalRead.model_validate(x) for x in rows]


@router.post("/goals/upsert", response_model=YearGoalRead)
async def upsert_goals(
    payload: YearGoalCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> YearGoalRead:
    """
    Create or update (upsert) a yearly goal for a wallet+year.

    Args:
        payload: YearGoalCreate payload (must include wallet_id and year).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Upserted YearGoalRead.

    Raises:
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info("POST /goals/upsert: start")
    async with session.begin():
        w = await get_wallet(session, payload.wallet_id)
        if not w or w.user_id != user_id:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        obj = await upsert_year_goal(session, payload=payload)
        
        goal = YearGoalRead.model_validate(obj)

    return goal


@router.put("/goals/{goal_id}", response_model=YearGoalRead)
async def update_goals(
    goal_id: uuid.UUID,
    patch: YearGoalUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> YearGoalRead:
    """
    Update a yearly goal by id (only if owned by the authenticated user).

    Args:
        goal_id: Goal UUID.
        patch: Partial update payload.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated YearGoalRead.

    Raises:
        HTTPException(404): if goal does not exist or is not owned by the user.
    """
    logger.info(f"PUT /goals/{goal_id}: start")
    async with session.begin():
        goal = await session.get(__import__("app.models.year_goal").models.year_goal.YearGoal, goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        w = await get_wallet(session, goal.wallet_id)
        if not w or w.user_id != user_id:
            raise HTTPException(status_code=404, detail="Goal not found")

        obj2 = await update_year_goal(session, goal_id=goal_id, patch=patch)
        
        goal = YearGoalRead.model_validate(obj2)

    return goal


@router.delete("/goals/{goal_id}")
async def delete_goals(
    goal_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict[str, bool]:
    """
    Delete a yearly goal by id (only if owned by the authenticated user).

    Args:
        goal_id: Goal UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} on success, {"ok": False} if delete returned falsy.

    Raises:
        HTTPException(404): if goal does not exist or is not owned by the user.
    """
    logger.info(f"DELETE /goals/{goal_id}: start")
    async with session.begin():
        goal = await session.get(__import__("app.models.year_goal").models.year_goal.YearGoal, goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        w = await get_wallet(session, goal.wallet_id)
        if not w or w.user_id != user_id:
            raise HTTPException(status_code=404, detail="Goal not found")
    
        ok = await delete_year_goal(session, goal_id=goal_id)

    return {"ok": ok}


@router.get("/{wallet_id}/ytd-summary")
async def get_wallet_ytd_summary(
    wallet_id: uuid.UUID,
    year: int = Query(default=datetime.now(timezone.utc).year),
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    w = await get_wallet(session, wallet_id)
    if not w or w.user_id != user_id:
        raise HTTPException(status_code=404, detail="Wallet not found")

    income, expense = await compute_wallet_ytd_income_expense_maps(session, wallet_id=wallet_id, year=year)

    return {"year": year, "income_by_currency": income, "expense_by_currency": expense}
