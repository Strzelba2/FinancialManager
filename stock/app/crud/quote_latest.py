from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlmodel import select
from typing import Optional, List, Tuple, Iterable
import logging

from app.models.models import Instrument, QuoteLatest, Market
from app.models.enums import InstrumentStatus
from app.schemas.schemas import QuoteLatesInput
from app.markerdata.registry import get_configured_market_timezone

logger = logging.getLogger(__name__)


def trade_date_in_market_timezone(
    last_trade_at: datetime,
    market_timezone: str | None,
) -> date:
    """
    Resolve the session date using the market calendar instead of the UTC date.

    Some quote sources publish a date-only "last trade" value. For GPW,
    midnight on 2026-06-12 in Europe/Warsaw is stored as 2026-06-11 22:00 UTC,
    so taking `.date()` in UTC would incorrectly cap candle sync at 2026-06-11.
    """
    trade_at = last_trade_at
    if trade_at.tzinfo is None:
        trade_at = trade_at.replace(tzinfo=timezone.utc)

    timezone_name = (market_timezone or "UTC").strip() or "UTC"
    try:
        market_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            "Invalid market timezone %r for latest quote; falling back to UTC",
            timezone_name,
        )
        market_tz = timezone.utc

    return trade_at.astimezone(market_tz).date()


async def upsert_quote_latest(session: AsyncSession, instrument_id, qin: QuoteLatesInput) -> QuoteLatest:
    """
    Insert or update the latest quote for a given instrument.

    The row in `QuoteLatest` is locked (FOR UPDATE) to avoid concurrent write issues.
    If no row exists for the given `instrument_id`, it is created; otherwise it is updated.

    Args:
        session: Async SQLAlchemy session.
        instrument_id: ID of the instrument whose latest quote is being upserted.
        qin: Input payload with the latest quote data.

    Returns:
        The up-to-date `QuoteLatest` instance.

    Raises:
        ValueError: If the upsert violates a database constraint (e.g. unique/index).
    """
    logger.debug(
        f"upsert_quote_latest: instrument_id={instrument_id}, "
        f"payload={qin.model_dump()}"
    )
    stmt = (
        select(QuoteLatest)
        .where(QuoteLatest.instrument_id == instrument_id)
        .with_for_update(of=QuoteLatest, nowait=False, skip_locked=False)
    )
    ql = (await session.execute(stmt)).scalar_one_or_none()
    if ql is None:
        ql = QuoteLatest(instrument_id=instrument_id, **qin.model_dump())
        session.add(ql)
    else:
        ql.last_price = qin.last_price
        ql.change_pct = qin.change_pct
        ql.volume = qin.volume
        ql.last_trade_at = qin.last_trade_at
        
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise ValueError("Upsert for QuoteLatest violated a database constraint.") from e

    await session.refresh(ql)
    return ql


async def fetch_latest_quote(session: AsyncSession, mic: str, symbol: str) -> Optional[QuoteLatest]:
    """
    Fetch the latest quote for a given MIC and symbol.

    The query joins `QuoteLatest` with `Instrument` and eagerly loads the instrument
    relationship. Only a single row (limit 1) is returned if present.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').
        symbol: Instrument symbol (e.g. 'PKN').

    Returns:
        The matching `QuoteLatest` instance (with `instrument` loaded), or None.
    """
    logger.debug(
        f"fetch_latest_quote: mic={mic!r}, symbol={symbol!r}"
    )

    stmt = (
        select(QuoteLatest)
        .join(Instrument, Instrument.id == QuoteLatest.instrument_id)
        .join(Market, Market.id == Instrument.market_id)
        .options(joinedload(QuoteLatest.instrument)) 
        .where(Market.mic == mic, Instrument.symbol == symbol)
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_latest_quote_for_instrument(
    session: AsyncSession,
    instrument_id,
) -> Optional[QuoteLatest]:
    stmt = (
        select(QuoteLatest)
        .where(QuoteLatest.instrument_id == instrument_id)
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_latest_trade_date_by_symbol(
    session: AsyncSession,
    symbol: str,
) -> Optional[date]:
    """
    Return the latest quote trade date stored for a given symbol.

    This is used to cap historical candle sync windows so we do not ask the
    upstream source for dates newer than the latest quote already available in
    our DB.
    """
    stmt = (
        select(QuoteLatest.last_trade_at, Market.timezone, Market.mic)
        .join(Instrument, Instrument.id == QuoteLatest.instrument_id)
        .join(Market, Market.id == Instrument.market_id)
        .where(Instrument.symbol == symbol)
        .limit(1)
    )
    res = await session.execute(stmt)
    row = res.one_or_none()
    if row is None:
        return None

    last_trade_at, market_timezone, market_mic = row
    market_timezone = get_configured_market_timezone(market_mic) or market_timezone
    return trade_date_in_market_timezone(last_trade_at, market_timezone)


async def fetch_latest_for_mic(session: AsyncSession, mic: str) -> List[QuoteLatest]:
    """
    Fetch all latest quotes for a given MIC, with instruments eagerly loaded.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').

    Returns:
        A list of `QuoteLatest` instances for all instruments in the given MIC.
    """
    logger.info(f"fetch_latest_for_mic: mic={mic!r}")
    
    stmt = (
        select(QuoteLatest)
        .join(Instrument, Instrument.id == QuoteLatest.instrument_id)
        .join(Market, Market.id == Instrument.market_id)   
        .options(
            joinedload(QuoteLatest.instrument).joinedload(Instrument.market)  
        )
        .where(Market.mic == mic)
        .order_by(Instrument.symbol)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def fetch_latest_quotes_by_symbols(
    session: AsyncSession,
    symbols: Iterable[str],
) -> List[Tuple[Instrument, Market, QuoteLatest]]:
    """
    Low-level CRUD: fetch Instrument, Market and QuoteLatest rows for given symbols.

    This function contains ALL DB/ORM logic.
    Service layer should not build queries directly.

    Args:
        session: SQLAlchemy async session.
        symbols: iterable of symbols (e.g. ["PKN", "CDR"]).

    Returns:
        List of tuples: (Instrument, Market, QuoteLatest).
        Instruments without a QuoteLatest row or inactive markets/instruments
        are filtered out.
    """
    symbols_list = list({s.strip().upper() for s in symbols if s and s.strip()})
    logger.info(f"symbols_list: {symbols_list}")
    if not symbols_list:
        logger.info("fetch_latest_quotes_by_symbols: empty symbols list after normalization")
        return []

    logger.info(f"fetch_latest_quotes_by_symbols: querying {len(symbols_list)} symbols")

    stmt = (
        select(Instrument, Market, QuoteLatest)
        .join(Market, Instrument.market_id == Market.id)
        .join(QuoteLatest, QuoteLatest.instrument_id == Instrument.id)
        .where(
            Instrument.symbol.in_(symbols_list),
            Instrument.status == InstrumentStatus.ACTIVE,
            Market.active.is_(True),
        )
    )

    result = await session.execute(stmt)
    rows: List[Tuple[Instrument, Market, QuoteLatest]] = result.all()
    logger.info(
        f"fetch_latest_quotes_by_symbols: fetched {len(rows)} rows "
        f"for {len(symbols_list)} requested symbols"
    )
    return rows
