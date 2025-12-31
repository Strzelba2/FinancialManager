from fastapi import APIRouter, Depends, HTTPException, status
import uuid
from typing import Optional, Dict
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.api.services.sell_assets_service import sell_real_estate_service
from app.crud.user_crud import get_user
from app.crud.real_estate_crud import (
    create_real_estate, list_real_estates, 
    update_real_estate, delete_real_estate, 
    )
from app.schamas.schemas import RealEstateCreate, RealEstateRead, RealEstateUpdate
from app.schamas.response import SellRealEstateIn


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/real-estates/create", response_model=RealEstateRead)
async def create_real_estate_endpoint(
    payload: RealEstateCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> RealEstateRead:
    """
    Create a new real estate record for a wallet owned by the authenticated user.

    Args:
        payload: RealEstateCreate payload (must include wallet_id).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        The created RealEstateRead.

    Raises:
        HTTPException(400): if user_id is unknown or constraint violation occurs.
        HTTPException(404): if wallet not found / not owned by the user.
    """
    logger.info("POST /real-estates/create: start")
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    try:
        obj = await create_real_estate(session, data=payload)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create real estate (constraint violation).",
        )
    return RealEstateRead.model_validate(obj)


@router.get("/{wallet_id}/real-estates", response_model=list[RealEstateRead])
async def list_real_estates_endpoint(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[RealEstateRead]:
    """
    List all real estate records for a wallet owned by the authenticated user.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        List of RealEstateRead entries.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet not found / not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/real-estates: start")
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    
    rows = await list_real_estates(session, wallet_id)
    return [RealEstateRead.model_validate(r) for r in rows]


@router.put("/real-estates/{real_estate_id}", response_model=RealEstateRead)
async def update_real_estate_endpoint(
    real_estate_id: uuid.UUID,
    payload: RealEstateUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> RealEstateRead:
    """
    Update a real estate record owned by the authenticated user.

    Ownership enforcement:
        Ideally fetch the object (get_real_estate) and verify wallet.user_id == user_id
        before applying update. If your update_real_estate already does ownership checks,
        this is redundant but safe.

    Args:
        real_estate_id: Real estate UUID.
        payload: Patch/update payload.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated RealEstateRead.

    Raises:
        HTTPException(400): if user_id is unknown or constraint violation occurs.
        HTTPException(404): if record not found / not owned by the user.
    """
    logger.info(f"PUT /real-estates/{real_estate_id}: start")
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    
    try:
        obj = await update_real_estate(session, re_id=real_estate_id, data=payload)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Real estate not found")
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not update real estate (constraint violation).",
        )
    return RealEstateRead.model_validate(obj)


@router.delete("/real-estates/{real_estate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_real_estate_endpoint(
    real_estate_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> None:
    """
    Delete a real estate record owned by the authenticated user.

    Args:
        real_estate_id: Real estate UUID.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        None (204 No Content).

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if record not found / not owned by the user.
    """
    logger.info(f"DELETE /real-estates/{real_estate_id}: start")
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
    
    try:
        await delete_real_estate(session, re_id=real_estate_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Real estate not found")
    
    
@router.patch("/real-estates/{real_estate_id}/sell")
async def sell_real_estate(
    real_estate_id: uuid.UUID,
    req: SellRealEstateIn,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> Optional[Dict[str, int]]:
    """
    Sell a real estate asset (service operation).

    Args:
        real_estate_id: Real estate UUID.
        req: SellRealEstateIn payload.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"updated": <int>} (whatever the service returns).

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404/400): depending on service validation (not found, invalid inputs, etc.).
    """
    logger.info(f"PATCH /real-estates/{real_estate_id}/sell: start")
    user = await get_user(session, user_id)
    await session.rollback()
    if not user:
        logger.warning(
            "sell_real_estate: unknown user_id"
        )
        raise HTTPException(status_code=400, detail='Unknown user_id')
    
    updated = await sell_real_estate_service(
        session=session, user_id=user_id, real_estate_id=real_estate_id, req=req
    )
    logger.info(f"updated: {updated}")
    return {"updated": updated}
