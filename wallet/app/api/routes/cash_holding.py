from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.schemas.schemas import CashHoldingCreate, CashHoldingRead, CashHoldingUpdate
from app.crud.cash_holding_crud import (
    create_cash_holding, delete_cash_holding, get_cash_holding, list_cash_holdings, update_cash_holding,
)
from app.crud.wallet_crud import get_wallet


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{wallet_id}/cash-holdings", response_model=list[CashHoldingRead])
async def list_cash_holdings_for_wallet(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[CashHoldingRead]:
    """
    List physical cash holdings for a wallet owned by the authenticated user.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID (resolved internally).
        session: SQLAlchemy async session.

    Returns:
        List of physical cash holdings for that wallet.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/cash-holdings: start")

    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        wallet = await get_wallet(session, wallet_id=wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        rows = await list_cash_holdings(session, wallet_id=wallet_id)
    return [CashHoldingRead.model_validate(r) for r in rows]


@router.post("/cash-holdings/create", response_model=CashHoldingRead)
async def create_cash_holding_endpoint(
    payload: CashHoldingCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> CashHoldingRead:
    """
    Create a physical cash holding for a wallet owned by the authenticated user.

    Args:
        payload: CashHoldingCreate model (must include wallet_id).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        The created physical cash holding.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info("POST /cash-holdings/create: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        wallet = await get_wallet(session, wallet_id=payload.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        obj = await create_cash_holding(session, payload=payload)

    return CashHoldingRead.model_validate(obj)


@router.put("/cash-holdings/{cash_holding_id}", response_model=CashHoldingRead)
async def update_cash_holding_endpoint(
    cash_holding_id: uuid.UUID,
    payload: CashHoldingUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> CashHoldingRead:
    """
    Update a physical cash holding owned by the authenticated user.

    Args:
        cash_holding_id: CashHolding UUID to update.
        payload: CashHoldingUpdate model.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated physical cash holding.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if the holding does not exist or is not owned by the user.
    """
    logger.info(f"PUT /cash-holdings/{cash_holding_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        obj = await get_cash_holding(session, cash_holding_id=cash_holding_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Cash holding not found")

        wallet = await get_wallet(session, wallet_id=obj.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=404, detail="Cash holding not found")

        updated = await update_cash_holding(session, cash_holding_id=cash_holding_id, payload=payload)

        if not updated:
            raise HTTPException(status_code=404, detail="Cash holding not found")

    return CashHoldingRead.model_validate(updated)


@router.delete("/cash-holdings/{cash_holding_id}", response_model=dict)
async def delete_cash_holding_endpoint(
    cash_holding_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Delete a physical cash holding owned by the authenticated user.

    Args:
        cash_holding_id: CashHolding UUID to delete.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} on successful deletion.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if the holding does not exist or is not owned by the user.
    """
    logger.info(f"DELETE /cash-holdings/{cash_holding_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        obj = await get_cash_holding(session, cash_holding_id=cash_holding_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Cash holding not found")

        wallet = await get_wallet(session, wallet_id=obj.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=404, detail="Cash holding not found")

        ok = await delete_cash_holding(session, cash_holding_id=cash_holding_id)

        if not ok:
            raise HTTPException(status_code=404, detail="Cash holding not found")

    return {"ok": True}
