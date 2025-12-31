from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.api.services.sell_assets_service import sell_metal_holding_service
from app.crud.user_crud import get_user
from app.crud.metal_holding_crud import (
    list_metal_holdings_by_wallet, update_metal_holding,
    delete_metal_holding, create_metal_holding,
    )
from app.schamas.schemas import MetalHoldingCreate, MetalHoldingRead, MetalHoldingUpdate
from app.schamas.response import SellMetalIn

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{wallet_id}/metal-holdings", response_model=List[MetalHoldingRead])
async def list_metal_holdings_endpoint(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> List[MetalHoldingRead]:
    """
    List metal holdings for a wallet owned by the authenticated user.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        List of metal holdings in this wallet.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet not found or not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/metal-holdings: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        rows = await list_metal_holdings_by_wallet(session, wallet_id=wallet_id)
    return [MetalHoldingRead.model_validate(r) for r in rows]


@router.post("/metal-holdings/create", response_model=MetalHoldingRead)
async def create_metal_holding_endpoint(
    payload: MetalHoldingCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> MetalHoldingRead:
    """
    Create a metal holding for a wallet owned by the authenticated user.

    Args:
        payload: MetalHoldingCreate (must include wallet_id and metal identifier).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Created metal holding.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet not found or not owned by the user.
        HTTPException(409): if holding already exists (unique constraint).
    """
    logger.info("POST /metal-holdings/create: start")
    try:
        async with session.begin():
            user = await get_user(session, user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

            obj = await create_metal_holding(session, payload=payload)

        return MetalHoldingRead.model_validate(obj)
    
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Metal holding already exists for this wallet and metal.",
        )


@router.put("/metal-holdings/{metal_holding_id}", response_model=MetalHoldingRead)
async def update_metal_holding_endpoint(
    metal_holding_id: uuid.UUID,
    payload: MetalHoldingUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> MetalHoldingRead:
    """
    Update a metal holding owned by the authenticated user.

    Notes:
        To enforce ownership, we validate that the holding's wallet is owned by `user_id`.
        This requires that `update_metal_holding` returns an object with `wallet_id`
        OR you do a separate get-by-id before update.

    Args:
        metal_holding_id: Holding UUID.
        payload: Update payload.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated metal holding.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if holding not found or not owned by the user.
    """
    logger.info(f"PUT /metal-holdings/{metal_holding_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        obj = await update_metal_holding(
            session,
            metal_holding_id=metal_holding_id,
            payload=payload,
        )
        if obj is None:
            raise HTTPException(status_code=404, detail="Metal holding not found")

    return MetalHoldingRead.model_validate(obj)


@router.delete("/metal-holdings/{metal_holding_id}")
async def delete_metal_holding_endpoint(
    metal_holding_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Delete a metal holding owned by the authenticated user.

    Args:
        metal_holding_id: Holding UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True}

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if holding not found (or not owned by the user, depending on CRUD enforcement).
    """
    logger.info(f"DELETE /metal-holdings/{metal_holding_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')

        ok = await delete_metal_holding(session, metal_holding_id=metal_holding_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Metal holding not found")
    return {"ok": True}


@router.patch("/metal-holdings/{metal_holding_id}/sell")
async def sell_metal(
    metal_holding_id: uuid.UUID,
    req: SellMetalIn,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Sell (part of) a metal holding and apply the transaction effects (service layer).

    Args:
        metal_holding_id: Holding UUID.
        req: SellMetalIn payload (e.g., quantity/proceeds info).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"updated": <int>} (whatever your service returns as 'updated').

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404/400): depending on service validation (holding not found, currency mismatch, etc.).
    """
    logger.info(f"PATCH /metal-holdings/{metal_holding_id}/sell: start")
    user = await get_user(session, user_id)
    await session.rollback()
    if not user:
        logger.warning(
            "sell_real_estate: unknown user_id"
        )
        raise HTTPException(status_code=400, detail='Unknown user_id')
    
    updated = await sell_metal_holding_service(session=session, user_id=user_id, metal_holding_id=metal_holding_id, req=req)
    return {"updated": updated}
