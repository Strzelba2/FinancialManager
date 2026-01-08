import uuid
from datetime import date
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from app.models.models import CandleDaily


async def get_min_max_date(
    session: AsyncSession,
    instrument_id: uuid.UUID,
) -> tuple[Optional[date], Optional[date]]:
    """
    Get the minimum and maximum available candle dates for an instrument.

    Args:
        session: SQLAlchemy async database session.
        instrument_id: Instrument UUID.

    Returns:
        A tuple `(min_date, max_date)` where each element can be `None`
        if the instrument has no candles.

    Raises:
        Exception: Propagates unexpected database errors after logging.
    """
    stmt = (
        select(
            func.min(CandleDaily.date_quote),
            func.max(CandleDaily.date_quote),
        )
        .where(CandleDaily.instrument_id == instrument_id)
    )
    res = await session.execute(stmt)
    return res.one()


async def upsert_candles_daily(
    session: AsyncSession,
    rows: list[dict],
) -> int:
    """
    Upsert daily candles into the database.

    The `rows` items must contain keys:
      - instrument_id, date_quote, open, high, low, close, volume, trade_at

    Args:
        session: SQLAlchemy async database session.
        rows: List of candle dictionaries to upsert.

    Returns:
        Number of affected rows reported by the database (rowcount).

    Raises:
        Exception: Propagates unexpected database errors after logging.
    """
    if not rows:
        return 0

    stmt = insert(CandleDaily.__table__).values(rows)

    stmt = stmt.on_conflict_do_update(
        index_elements=["instrument_id", "date_quote"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "trade_at": stmt.excluded.trade_at,
        },
    )

    res = await session.execute(stmt)
    return int(res.rowcount or 0)


async def list_candles_daily(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Sequence[CandleDaily]:
    """
    List daily candles for an instrument within an optional date range.

    Args:
        session: SQLAlchemy async database session.
        instrument_id: Instrument UUID.
        date_from: Optional inclusive lower bound for `date_quote`.
        date_to: Optional inclusive upper bound for `date_quote`.

    Returns:
        A sequence of `CandleDaily` records ordered by `date_quote` ascending.

    Raises:
        Exception: Propagates unexpected database errors after logging.
    """
    stmt = select(CandleDaily).where(CandleDaily.instrument_id == instrument_id)

    if date_from is not None:
        stmt = stmt.where(CandleDaily.date_quote >= date_from)
    if date_to is not None:
        stmt = stmt.where(CandleDaily.date_quote <= date_to)

    stmt = stmt.order_by(CandleDaily.date_quote.asc())
    res = await session.execute(stmt)
    return res.scalars().all()
