import uuid
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.clients.stock_client import StockClient

from app.schamas.schemas import (
    FavoriteListCreate, FavoriteListRead, FavoriteItemCreate,
    FavoriteItemRead, Currency
)
from app.crud.favorites import (
    list_favorite_lists,
    create_favorite_list,
    delete_favorite_list,
    list_favorite_items,
    add_favorite_item,
    remove_favorite_item,
    list_favorite_items_with_alerts,
)
from app.crud.instrument_crud import get_or_create_instrument, get_instrument_by_symbol
from app.db.session import db
from app.api.deps import get_internal_user_id, get_stock_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/favorites/lists", response_model=List[FavoriteListRead])
async def api_list_lists(
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> List[FavoriteListRead]:
    """
    List all favorite lists for the current user.

    Args:
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        A list of favorite lists as `FavoriteListRead`.
    """
    return await list_favorite_lists(session, user_id)


@router.post("/favorites/lists", response_model=FavoriteListRead)
async def api_create_list(
    body: FavoriteListCreate,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> FavoriteListRead:
    """
    Create a new favorite list for the current user.

    Args:
        body: Create payload containing list name and optional description.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        The created list as `FavoriteListRead`.
    """
    return await create_favorite_list(session, user_id, name=body.name, description=body.description)


@router.delete("/favorites/lists/{list_id}")
async def api_delete_list(
    list_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> Dict[str, Any]:
    """
    Delete a favorite list (owned by the current user).

    Args:
        list_id: Favorite list id.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException(404): If the list does not exist or does not belong to the user.
    """
    ok = await delete_favorite_list(session, user_id, list_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Favorite list not found")
    return {"ok": True}


@router.get("/favorites/lists/{list_id}/items", response_model=List[FavoriteItemRead])
async def api_list_items(
    list_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> List[FavoriteItemRead]:
    """
    List items in a favorite list.

    Args:
        list_id: Favorite list id.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        A list of items as `FavoriteItemRead`.
    """
    return await list_favorite_items(session, user_id, list_id)


@router.get("/favorites/lists/{list_id}/items-with-alerts")
async def api_list_items_with_alerts(
    list_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> List[Dict[str, Any]]:
    """
    List items in a favorite list enriched with alert information (if present).

    This is typically used by UI pages that want:
      - favorite items
      - plus their corresponding alert payloads in one call

    Args:
        list_id: Favorite list id.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        A list of dicts (API payload) returned by `list_favorite_items_with_alerts`.
    """
    return await list_favorite_items_with_alerts(session, user_id, list_id)


@router.post("/favorites/lists/{list_id}/items", response_model=FavoriteItemRead)
async def api_add_item(
    list_id: uuid.UUID,
    body: FavoriteItemCreate,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
    stock_client: StockClient = Depends(get_stock_client),
) -> FavoriteItemRead:
    """
    Add an instrument to a favorite list.

    This endpoint resolves the instrument in stock-service (by MIC + symbol),
    then ensures the instrument exists locally (get-or-create), and finally
    creates a favorite-list item linking the user/list to that instrument.

    Args:
        list_id: Favorite list id.
        body: Payload with at least `mic` and `symbol`.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).
        stock_client: Stock-service client dependency.

    Returns:
        The created favorite item as `FavoriteItemRead`.

    Raises:
        HTTPException(404): If instrument cannot be resolved in stock-service
            or local creation fails with ValueError.
    """
    try:
        stock_inst = await stock_client.resolve_instrument(mic=body.mic, symbol=body.symbol)
        instrument_name = (stock_inst.name or body.symbol or "").strip()
        if not instrument_name:
            raise ValueError(f"Cannot determine instrument name for symbol={body.symbol}")

        inst = await get_or_create_instrument(
            session=session,
            mic=stock_inst.mic,
            symbol=stock_inst.symbol,
            name=instrument_name,
            currency=Currency(stock_inst.currency),
        )
        
        return await add_favorite_item(session, user_id, list_id, inst.id)
    except ValueError as e:
        logger.info(f"value error : {e}")
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/favorites/lists/{list_id}/items/{symbol}")
async def api_remove_item(
    list_id: uuid.UUID,
    symbol: str,
    session: AsyncSession = Depends(db.get_session),
    user_id: uuid.UUID = Depends(get_internal_user_id),
) -> Dict[str, Any]:
    """
    Remove an instrument from a favorite list by symbol.

    Args:
        list_id: Favorite list id.
        symbol: Instrument symbol to remove.
        session: SQLAlchemy async database session.
        user_id: Authenticated user id (resolved internally).

    Returns:
        {"ok": True} on success.

    Raises:
        HTTPException(404): If instrument does not exist or item is not in the list.
    """
    inst = await get_instrument_by_symbol(session, symbol)
    ok = await remove_favorite_item(session, user_id, list_id, inst.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Favorite item not found")
    return {"ok": True}
