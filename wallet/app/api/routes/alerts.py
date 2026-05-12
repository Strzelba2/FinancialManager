import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.schemas.schemas import PriceAlertCreate, PriceAlertUpdate, PriceAlertRead
from app.crud.price_alert_crud import (
    get_alert,
    upsert_alert,
    delete_alert,
    patch_alert,
    list_alerts_with_symbols
)
from app.crud.instrument_crud import get_instrument_by_symbol
from app.db.session import db
from app.api.deps import get_internal_user_id

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/alerts/{symbol}", response_model=Optional[PriceAlertRead])
async def api_get_alert(
    symbol: str,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> Optional[PriceAlertRead]:
    """
    Get a price alert for a given instrument symbol.

    Args:
        symbol: Instrument symbol (e.g., "PKN", "AAPL").
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        The alert as `PriceAlertRead` if it exists, otherwise None.

    Raises:
        HTTPException(404): If the instrument does not exist for the given symbol.
    """
    inst = await get_instrument_by_symbol(session, symbol)
    if inst is None:
        logger.info(f"api_get_alert: instrument not found symbol={symbol}")
        raise HTTPException(status_code=404, detail=f"Instrument not found for symbol='{symbol}'")
    return await get_alert(session, user_id, inst.id)


@router.post("/alerts", response_model=PriceAlertRead)
async def api_upsert_alert(
    body: PriceAlertCreate,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> PriceAlertRead:
    """
    Create or update a price alert for a user and symbol.

    Args:
        body: Alert payload (symbol + thresholds + settings).
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        Upserted alert as `PriceAlertRead`.

    Raises:
        HTTPException(404): If the instrument symbol does not exist.
        HTTPException(400): If validation fails (e.g. thresholds invalid).
    """
    try:
        inst = await get_instrument_by_symbol(session, body.symbol)
        
        if inst is None:
            logger.info(f"api_get_alert: instrument not found symbol={body.symbol} user_id={user_id}")
            raise HTTPException(status_code=404, detail=f"Instrument not found for symbol='{body.symbol}'")
        return await upsert_alert(
            session=session,
            user_id=user_id,
            instrument_id=inst.id,
            below_price=body.below_price,
            above_price=body.above_price,
            enabled=body.enabled,
            one_shot=body.one_shot,
            expires_at=body.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/alerts/{symbol}", response_model=PriceAlertRead)
async def api_patch_alert(
    symbol: str,
    body: PriceAlertUpdate,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> PriceAlertRead:
    """
    Patch (partially update) an existing alert for the given symbol.

    Args:
        symbol: Instrument symbol.
        body: Partial alert update payload.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        Updated alert as `PriceAlertRead`.

    Raises:
        HTTPException(404): If the instrument does not exist or the alert does not exist.
        HTTPException(400): If validation fails.
    """
    try:
        inst = await get_instrument_by_symbol(session, symbol)
        updated = await patch_alert(session, user_id, inst.id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")

    return updated


@router.get("/alerts", response_model=List[PriceAlertRead])
async def api_list_alerts(
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> list[PriceAlertRead]:
    """
    List all alerts for the current user, including instrument symbols.

    Args:
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        A list of alerts as `PriceAlertRead` (with the `symbol` field populated).
    """
    rows = await list_alerts_with_symbols(session, user_id)

    out: list[PriceAlertRead] = []
    for a, sym in rows:
        out.append(
            PriceAlertRead(
                id=a.id,
                instrument_id=a.instrument_id,
                user_id=a.user_id,
                symbol=sym,  
                below_price=a.below_price,
                above_price=a.above_price,
                enabled=a.enabled,
                one_shot=a.one_shot,
                expires_at=a.expires_at,
                created_at=a.created_at,
                updated_at=getattr(a, "updated_at", None),
            )
        )
    return out


@router.delete("/alerts/{symbol}")
async def api_delete_alert(
    symbol: str,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
):
    """
    Delete an alert for the given instrument symbol.

    Args:
        symbol: Instrument symbol.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException(404): If the instrument does not exist or alert does not exist.
    """
    inst = await get_instrument_by_symbol(session, symbol)
    ok = await delete_alert(session, user_id, inst.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}
