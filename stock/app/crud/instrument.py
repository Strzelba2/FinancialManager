import uuid
from typing import Optional
import logging
from sqlmodel import select, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Instrument, Market
from app.schemas.schemas import InstrumentCreate

logger = logging.getLogger(__name__)


async def count_by_market_id(session: AsyncSession, market_id: uuid.UUID) -> int:
    """
    Count instruments belonging to a given market.

    Args:
        session: Async SQLAlchemy session.
        market_id: ID of the market whose instruments should be counted.

    Returns:
        Number of instruments associated with the given market.
    """
    logger.debug(f"Counting instruments for market_id={market_id}")
    res = await session.execute(
        select(func.count()).select_from(Instrument).where(Instrument.market_id == market_id)
    )
    return int(res.scalar_one())


async def get_by_symbol_in_market(session: AsyncSession, market_id: uuid.UUID, symbol: str) -> Optional[Instrument]:
    """
    Fetch a single instrument by symbol within a specific market.

    Args:
        session: Async SQLAlchemy session.
        market_id: ID of the market.
        symbol: Instrument symbol to look up.

    Returns:
        The matching `Instrument` instance, or None if not found.
    """
    logger.debug(
        f"get_by_symbol_in_market: market_id={market_id}, symbol={symbol!r}"
    )
    res = await session.execute(
        select(Instrument).where(Instrument.market_id == market_id, Instrument.symbol == symbol)
    )
    return res.scalars().first()


async def get_instrument_by_symbol(
    session: AsyncSession,
    symbol: str,
) -> Optional[Instrument]:
    """
    Fetch a single instrument by its unique symbol.

    Args:
        session: SQLAlchemy async database session.
        symbol: Instrument symbol to look up (e.g. "AAPL", "PKO").

    Returns:
        The `Instrument` if found, otherwise `None`.

    Raises:
        Exception: Propagates unexpected database errors after logging.
    """
    stmt = select(Instrument).where(Instrument.symbol == symbol)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def create_instrument(session: AsyncSession, data: InstrumentCreate) -> Instrument:
    """
    Create and persist a new instrument.

    Args:
        session: Async SQLAlchemy session.
        data: `InstrumentCreate` payload used to construct the Instrument.

    Returns:
        The newly created `Instrument` instance.

    Raises:
        ValueError: If an instrument with the same symbol or shortname already exists.
    """
    payload = data.model_dump(exclude_none=False)

    instrument = Instrument(**payload)
    
    logger.debug(
        f"create_instrument: constructed Instrument(symbol={instrument.symbol!r}, "
        f"isin={instrument.isin!r})"
    )
    
    session.add(instrument)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        logger.error(
            "create_instrument: integrity error "
            f"for symbol={instrument.symbol!r}, isin={instrument.isin!r}: {e}"
        )
        raise ValueError("instrument with this symbol or shortname already exists.") from e
    await session.refresh(instrument)
    logger.debug(
        f"create_instrument: persisted Instrument id={instrument.id}, "
        f"symbol={instrument.symbol!r}, isin={instrument.isin!r}"
    )
    return instrument


async def list_instruments(
    session: AsyncSession,
    mic: str,
    limit: int = 1200,
    offset: int = 0,
) -> list[Instrument]:
    """
    List instruments for a given market MIC with pagination.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC (e.g. 'XWAR').
        limit: Maximum number of instruments to return.
        offset: Number of instruments to skip (for pagination).

    Returns:
        A list of `Instrument` instances.
    """
    logger.debug(
        f"list_instruments: mic={mic!r}, limit={limit}, offset={offset}"
    )
    stmt = (
        select(Instrument)
        .join(Instrument.market)    
        .where(Market.mic == mic)
        .order_by(Instrument.symbol.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().unique().all()


async def search_instruments_by_shortname_or_name(
    session: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[tuple[Instrument, Market]]:
    """
    Search instruments by shortname or full name (case-insensitive, partial match).

    Args:
        session: Async SQLAlchemy session.
        query: Text fragment to search in `shortname` or `name`.
        limit: Maximum number of results to return.

    Returns:
        A list of `(Instrument, Market)` tuples matching the search query.
    """
    q = (query or "").strip()
    logger.debug(
        f"search_instruments_by_shortname_or_name: raw_query={query!r}, "
        f"normalized_query={q!r}, limit={limit}"
    )

    if not q:
        logger.debug(
            "search_instruments_by_shortname_or_name: empty query after strip, "
            "returning empty result."
        )
        return []

    stmt = (
        select(Instrument, Market)
        .join(Market, Instrument.market_id == Market.id)
        .where(
            or_(
                Instrument.shortname.ilike(f"%{q}%"),
                Instrument.name.ilike(f"%{q}%"),
            )
        )
        .order_by(Instrument.shortname.asc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    rows: list[tuple[Instrument, Market]] = result.all()
    return rows
