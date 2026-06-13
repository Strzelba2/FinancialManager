import uuid
import logging
from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.models import Instrument, Market
from app.schemas.schemas import MarketCreate
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def get_market_by_mic(session: AsyncSession, mic: str) -> Optional[Market]:
    """
    Fetch a single market by its MIC code.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').

    Returns:
        The `Market` instance if found, otherwise None.
    """
    logger.debug(f"get_market_by_mic: querying market by mic={mic!r}")
    
    res = await session.execute(select(Market).where(Market.mic == mic))
    return res.scalars().first()


async def get_market_id_by_mic(session: AsyncSession, mic: str) -> Optional[uuid.UUID]:
    """
    Fetch only the ID of a market by its MIC code.

    Args:
        session: Async SQLAlchemy session.
        mic: Market MIC code (e.g. 'XWAR').

    Returns:
        The UUID of the market if found, otherwise None.
    """
    logger.debug(f"get_market_id_by_mic: querying market id by mic={mic!r}")
    
    res = await session.execute(select(Market.id).where(Market.mic == mic))
    return res.scalar_one_or_none()


async def create_market(session: AsyncSession, data: MarketCreate) -> Market:
    payload = data.model_dump(exclude_none=False)
    market = Market(**payload)
    session.add(market)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("market with this MIC or name already exists.") from exc
    await session.refresh(market)
    return market


async def list_markets(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    with_instruments: bool = False,
    only_with_instruments: bool = False,
) -> List[Market]:
    """
    List markets with optional search and pagination.

    Args:
        session: Async SQLAlchemy session.
        limit: Maximum number of markets to return.
        offset: Number of markets to skip (for pagination).
        search: Optional search string applied to name, MIC, or country (ILIKE).
        with_instruments: If True, eagerly loads related `instruments`.
        only_with_instruments: If True, returns only markets with at least one instrument.

    Returns:
        A list of `Market` instances matching the criteria.
    """
    logger.debug(
        "list_markets: start query with "
        f"limit={limit}, offset={offset}, search={search!r}, "
        f"with_instruments={with_instruments}"
    )
    
    stmt = select(Market).order_by(Market.name.asc())

    if only_with_instruments:
        stmt = stmt.join(Instrument, Instrument.market_id == Market.id).distinct()

    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            Market.name.ilike(like)
            | Market.mic.ilike(like)
            | Market.country.ilike(like)
        )

    if with_instruments:
        stmt = stmt.options(
            selectinload(Market.instruments),
        )

    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    markets: List[Market] = result.scalars().unique().all()
    return markets
