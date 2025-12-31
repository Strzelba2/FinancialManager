from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import db
from app.api.deps import get_internal_user_id
from app.crud.user_crud import get_user
from app.schamas.schemas import DebtCreate, DebtRead, DebtUpdate
from app.crud.debt_crud import delete_debt, create_debt, list_debts, get_debt, update_debt
from app.crud.wallet_crud import get_wallet


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{wallet_id}/debts", response_model=list[DebtRead])
async def list_debts_for_wallet(
    wallet_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> list[DebtRead]:
    """
    List all debts for a given wallet owned by the authenticated user.

    Args:
        wallet_id: Wallet UUID.
        user_id: Authenticated user UUID (resolved internally).
        session: SQLAlchemy async session.

    Returns:
        List of debts for that wallet.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info(f"GET /{wallet_id}/debts: start")
    
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        wallet = await get_wallet(session, wallet_id=wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        rows = await list_debts(session, wallet_id=wallet_id)
    return [DebtRead.model_validate(r) for r in rows]


@router.post("/debts/create", response_model=DebtRead)
async def create_debt_endpoint(
    payload: DebtCreate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> DebtRead:
    """
    Create a new debt entry for a wallet owned by the authenticated user.

    Args:
        payload: DebtCreate model (must include wallet_id).
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        The created debt model.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if wallet does not exist or is not owned by the user.
    """
    logger.info("POST /debts/create: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        wallet = await get_wallet(session, wallet_id=payload.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        obj = await create_debt(session, payload=payload)

    return DebtRead.model_validate(obj)


@router.put("/debts/{debt_id}", response_model=DebtRead)
async def update_debt_endpoint(
    debt_id: uuid.UUID,
    payload: DebtUpdate,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> DebtRead:
    """
    Update an existing debt entry owned by the authenticated user.

    Security model:
    - Debt must exist
    - The wallet belonging to that debt must be owned by the user

    Args:
        debt_id: Debt UUID to update.
        payload: DebtUpdate model.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        Updated debt.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if debt does not exist or is not owned by the user.
    """
    logger.info(f"PUT /debts/{debt_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        obj = await get_debt(session, debt_id=debt_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Debt not found")

        wallet = await get_wallet(session, wallet_id=obj.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=404, detail="Debt not found")

        updated = await update_debt(session, debt_id=debt_id, payload=payload)

        if not updated:
            raise HTTPException(status_code=404, detail="Debt not found")

    return DebtRead.model_validate(updated)


@router.delete("/debts/{debt_id}", response_model=dict)
async def delete_debt_endpoint(
    debt_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """
    Delete a debt entry owned by the authenticated user.

    Args:
        debt_id: Debt UUID to delete.
        user_id: Authenticated user UUID.
        session: SQLAlchemy async session.

    Returns:
        {"ok": True} on successful deletion.

    Raises:
        HTTPException(400): if user_id is unknown.
        HTTPException(404): if debt does not exist or is not owned by the user.
    """
    logger.info(f"DELETE /debts/{debt_id}: start")
    async with session.begin():
        user = await get_user(session, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Unknown user_id')
        
        obj = await get_debt(session, debt_id=debt_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Debt not found")

        wallet = await get_wallet(session, wallet_id=obj.wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise HTTPException(status_code=404, detail="Debt not found")

        ok = await delete_debt(session, debt_id=debt_id)

        if not ok:
            raise HTTPException(status_code=404, detail="Debt not found")

    return {"ok": True}
