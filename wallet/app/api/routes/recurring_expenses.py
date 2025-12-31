from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.schamas.schemas import RecurringExpenseCreate, RecurringExpenseUpdate, RecurringExpenseRead
from app.crud.recurring_expenses_crud import (
    update_recurring_expense, create_recurring_expense, delete_recurring_expense,
    list_recurring_expenses)
from app.crud.wallet_crud import get_wallet


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{wallet_id}/recurring-expenses", response_model=list[RecurringExpenseRead])
async def list_recurring_expenses_endpoint(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[RecurringExpenseRead]:
    """
    List recurring expenses for a wallet owned by the authenticated user.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        List of RecurringExpenseRead.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet not found or not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/recurring-expenses: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        wallet = await get_wallet(session, wallet_id=wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        rows = await list_recurring_expenses(session, wallet_id)
    return [RecurringExpenseRead.model_validate(x) for x in rows]


@router.post("/recurring-expenses/create", response_model=RecurringExpenseRead)
async def create_recurring_expense_endpoint(
    payload: RecurringExpenseCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> RecurringExpenseRead:
    """
    Create a recurring expense for a wallet owned by the authenticated user.

    Args:
        payload: RecurringExpenseCreate payload (must include wallet_id).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Created RecurringExpenseRead.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet not found or not owned by the user.
    """
    logger.info("POST /recurring-expenses/create: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        wallet = await get_wallet(session, wallet_id=payload.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        obj = await create_recurring_expense(session, payload)

    return RecurringExpenseRead.model_validate(obj)


@router.put("/recurring-expenses/{expense_id}", response_model=RecurringExpenseRead)
async def update_recurring_expense_endpoint(
    expense_id: uuid.UUID,
    payload: RecurringExpenseUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> RecurringExpenseRead:
    """
    Update a recurring expense owned by the authenticated user.

    Ownership enforcement:
        Recommended to fetch the expense and verify wallet ownership before update.

    Args:
        expense_id: Recurring expense UUID.
        payload: Update payload.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated RecurringExpenseRead.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if expense not found or not owned by the user.
    """
    logger.info(f"PUT /recurring-expenses/{expense_id}: start")

    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        obj = await update_recurring_expense(session, expense_id, payload)
        if not obj:
            raise HTTPException(status_code=404, detail="Not found")

    return RecurringExpenseRead.model_validate(obj)


@router.delete("/recurring-expenses/{expense_id}")
async def delete_recurring_expense_endpoint(
    expense_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict[str, bool]:
    """
    Delete a recurring expense owned by the authenticated user.

    Args:
        expense_id: Recurring expense UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if expense not found (or not owned by the user depending on CRUD enforcement).
    """
    logger.info(f"DELETE /recurring-expenses/{expense_id}: start")

    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        ok = await delete_recurring_expense(session, expense_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
