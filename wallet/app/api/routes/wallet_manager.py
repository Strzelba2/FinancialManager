from fastapi import APIRouter, Depends
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.clients.stock_client import StockClient

from app.api.deps import get_internal_user_id, get_stock_client
from app.api.services.wallet_manager_service import get_wallet_manager_tree_service, create_monthly_snapshot_for_user_service
from app.db.session import db
from app.schamas.response import (
    WalletManagerWalletOut, CreateMonthlySnapshotIn, CreateMonthlySnapshotOut,
    WalletManagerTreeIn
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/manager/tree", response_model=list[WalletManagerWalletOut])
async def wallet_manager_tree(
    payload: WalletManagerTreeIn,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
) -> list[WalletManagerWalletOut]:
    """
    Build a wallet-manager tree for a user.

    The tree contains wallets with grouped nodes (deposit accounts, brokerage accounts,
    metals, and real estate) plus health flags and optional snapshot metadata.

    Args:
        payload: Request body containing:
            - months: how many months of history/snapshots to include
            - currency_rate: FX map used to compute view values
        user_id: Internal user UUID resolved from request (dependency).
        session: SQLAlchemy async database session (dependency).
        stock_client: Stock service client used for quote/market lookups (dependency).

    Returns:
        A list of wallet manager tree nodes as `WalletManagerWalletOut`.
    """
    return await get_wallet_manager_tree_service(
        session=session,
        user_id=user_id,
        months=payload.months,
        stock_client=stock_client,
        currency_rate=payload.currency_rate,  
    )
    
    
@router.post("/snapshots/monthly", response_model=CreateMonthlySnapshotOut)
async def api_create_monthly_snapshot(
    payload: CreateMonthlySnapshotIn,
    user_id: uuid.UUID = Depends(get_internal_user_id),
    session: AsyncSession = Depends(db.get_session),
    stock_client: StockClient = Depends(get_stock_client),
) -> CreateMonthlySnapshotOut:
    """
    Create a monthly snapshot for the given user.

    This typically persists:
      - FX rates for the month (if applicable)
      - deposit account snapshot rows
      - brokerage snapshot rows
      - metals snapshot rows
      - real estate snapshot rows

    Args:
        payload: Request body containing:
            - month_key: target month key (e.g. "2026-01")
            - currency_rate: FX map used to store snapshot values
        user_id: Internal user UUID resolved from request (dependency).
        session: SQLAlchemy async database session (dependency).
        stock_client: Stock service client used to value brokerage positions (dependency).

    Returns:
        `CreateMonthlySnapshotOut` with counts of upserted rows and ok=True on success.
    """
    mk, fx_saved, dep_up, bro_up, metal_up, re_up = await create_monthly_snapshot_for_user_service(
        session=session,
        user_id=user_id,
        month_key_snap=payload.month_key,
        currency_rate=payload.currency_rate,
        stock_client=stock_client,
    )
    return CreateMonthlySnapshotOut(
        ok=True,
        month_key=str(mk),
        fx_saved=bool(fx_saved),
        dep_upserted=int(dep_up),
        bro_upserted=int(bro_up),
        metal_upserted=int(metal_up),
        re_upserted=int(re_up),
    )
