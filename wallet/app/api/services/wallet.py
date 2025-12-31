from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import logging
import uuid

from app.schamas.schemas import WalletCreate
from app.models.models import Wallet
from app.schamas.response import WalletResponse, DashFlowMonthItem
from app.utils.utils import normalize_name, month_floor, last_n_month_starts
from app.crud.wallet_crud import (
    ensure_unique_name, create_wallet, get_wallet, delete_wallet
    )
from app.crud.transaction_crud import sum_income_expense_for_wallet_month_range
from app.crud.capital_gain_crud import sum_capital_gains_for_wallet_month_range

logger = logging.getLogger(__name__)


async def create_wallet_service(session: AsyncSession, data: WalletCreate) -> WalletResponse:
    """
    Create a new wallet for a given user.

    Args:
        session (AsyncSession): SQLAlchemy async session.
        data (WalletCreate): Wallet creation data including user_id and name.

    Returns:
        WalletResponse: The created wallet's ID and normalized name.

    Raises:
        ValueError: If name is empty or too long.
        HTTPException: If the name is not unique for the user.
    """
    
    name = normalize_name(data.name)
    if not name:
        raise ValueError("Wallet name cannot be empty.")
    if len(name) > 40:
        raise ValueError("Wallet name is too long (max 40 characters).")
    
    user_id = data.user_id
    
    await ensure_unique_name(session, user_id, name)
    
    data = WalletCreate(name=name, user_id=user_id)
    
    wallet = await create_wallet(session, data)
    
    return WalletResponse(id=wallet.id, name=wallet.name)


async def delete_wallet_service(
    session: AsyncSession, 
    wallet_id: uuid.UUID, 
    user_id: uuid.UUID, 
) -> bool:
    """
    Delete a wallet by ID if it belongs to the given user.

    Args:
        session (AsyncSession): SQLAlchemy async session.
        wallet_id (UUID): The wallet ID to delete.
        user_id (UUID): The user ID attempting the deletion.

    Returns:
        bool: True if wallet was deleted, False if not found or not authorized.
    """
    wallet = await get_wallet(session, wallet_id)
    
    if not wallet:
        return False
    if wallet.user_id != user_id:  
        return False
    return await delete_wallet(session, wallet_id)


async def dash_flow_8m(
    session: AsyncSession, 
    wallet: Wallet, 
) -> List[DashFlowMonthItem]:
    """
    Build an 8-month dashboard cash-flow series for a wallet.

    This aggregates:
      - INCOME / EXPENSE transactions by month and currency
      - CAPITAL gains by month and currency

    Time window:
      - Starts at the first day of the month for the oldest month in the 8-month window
      - Ends at the first day of next month (exclusive)

    Args:
        session: SQLAlchemy async session.
        wallet: Wallet ORM object (must have `.id`).

    Returns:
        A list of DashFlowMonthItem ordered chronologically (oldest -> newest),
        one entry per month in the 8-month window.
    """
    now = datetime.now(timezone.utc)
    month_starts = last_n_month_starts(8, now)
    months_str = [dt.strftime("%Y-%m") for dt in month_starts]

    start_dt = month_starts[0]
    end_dt = month_floor(now) + relativedelta(months=1)

    tx_rows = await sum_income_expense_for_wallet_month_range(
        session=session,
        wallet_id=wallet.id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    cg_rows = await sum_capital_gains_for_wallet_month_range(
        session=session,
        wallet_id=wallet.id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    flow: dict[str, DashFlowMonthItem] = {
        ms: DashFlowMonthItem(month=ms) for ms in months_str
    }

    for m_dt, status_s, ccy, total in tx_rows:
        ms = m_dt.strftime("%Y-%m")
        if ms not in flow:
            continue
        total_dec = total or Decimal("0")
        if status_s == "INCOME":
            flow[ms].income_by_currency[ccy] = flow[ms].income_by_currency.get(ccy, Decimal("0")) + total_dec
        else:
            flow[ms].expense_by_currency[ccy] = flow[ms].expense_by_currency.get(ccy, Decimal("0")) + total_dec

    for m_dt, ccy, total in cg_rows:
        ms = m_dt.strftime("%Y-%m")
        if ms not in flow:
            continue
        total_dec = total or Decimal("0")
        flow[ms].capital_by_currency[ccy] = flow[ms].capital_by_currency.get(ccy, Decimal("0")) + total_dec
    
    return [flow[m] for m in months_str]
