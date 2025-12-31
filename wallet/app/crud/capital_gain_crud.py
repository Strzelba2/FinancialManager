from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Tuple
from uuid import UUID


from app.models.models import CapitalGain, DepositAccount
from app.schamas.schemas import CapitalGainCreate
from app.models.enums import CapitalGainKind, Currency


async def create_capital_gain(session: AsyncSession, data: CapitalGainCreate) -> CapitalGain:
    """
    Create a CapitalGain row.

    Args:
        session: SQLAlchemy async session.
        data: CapitalGainCreate payload.

    Returns:
        Created CapitalGain ORM object.

    Raises:
        ValueError: If a unique constraint / FK constraint fails (e.g., transaction already linked or invalid FK).
    """
    obj = CapitalGain(**data.model_dump()) 
 
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as e:
        raise ValueError("Transaction already exists for this capital gain, or invalid FK.") from e
    await session.refresh(obj)
    return obj


async def sum_capital_gains_for_wallet_year(
    session: AsyncSession,
    wallet_id: UUID,
    year: int,
) -> List[Tuple[CapitalGainKind, Currency, Decimal]]:
    """
    Sum capital gains for a wallet in a given year grouped by (kind, currency).

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        year: Target year (UTC).

    Returns:
        List of tuples:
            (CapitalGain.kind, CapitalGain.currency, sum(amount))
    """

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    stmt = (
        select(
            CapitalGain.kind,
            CapitalGain.currency,
            func.coalesce(func.sum(CapitalGain.amount), 0),
        )
        .join(DepositAccount, CapitalGain.deposit_account_id == DepositAccount.id)
        .where(
            DepositAccount.wallet_id == wallet_id,
            CapitalGain.occurred_at >= start,
            CapitalGain.occurred_at < end,
        )
        .group_by(CapitalGain.kind, CapitalGain.currency)
    )

    result = await session.execute(stmt)
    rows = result.all()  

    return rows


async def sum_capital_gains_for_wallet_month_range(
    session: AsyncSession,
    wallet_id: UUID,
    start_dt: datetime,
    end_dt: datetime,
) -> list[tuple[datetime, Currency, Decimal]]:
    """
    Sum capital gains for a wallet grouped by month and currency.

    Groups by:
        date_trunc('month', occurred_at), currency

    Args:
        session: SQLAlchemy async session.
        wallet_id: Wallet UUID.
        start_dt: Inclusive lower bound datetime (UTC recommended).
        end_dt: Exclusive upper bound datetime (UTC recommended).

    Returns:
        List of tuples:
            (month_start_datetime, currency, total_amount)
        Ordered by month ascending.
    """
    m = func.date_trunc("month", CapitalGain.occurred_at).label("m")
    q = (
        select(
            m,
            CapitalGain.currency,
            func.sum(CapitalGain.amount).label("total"),
        )
        .join(DepositAccount, DepositAccount.id == CapitalGain.deposit_account_id)
        .where(DepositAccount.wallet_id == wallet_id)
        .where(CapitalGain.occurred_at >= start_dt)
        .where(CapitalGain.occurred_at < end_dt)
        .group_by(m, CapitalGain.currency)
        .order_by(m.asc())
    )
    res = await session.execute(q)
    return list(res.all())
