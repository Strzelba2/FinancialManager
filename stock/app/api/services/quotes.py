from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.quote_latest import fetch_latest_quote, fetch_latest_for_mic
from app.schemas.quates import QuotePayloadOut, BulkQuotesOut

logger = logging.getLogger(__name__)


async def get_latest_quote_service(session: AsyncSession, mic: str, symbol: str) -> Optional[QuotePayloadOut]:
    """
    Fetch the latest quote for a single instrument on a given market.

    Args:
        session: Async SQLAlchemy database session.
        mic: Market MIC code (e.g. XWAR, XNCO).
        symbol: Instrument symbol (e.g. PKN, AAPL).

    Returns:
        A `QuotePayloadOut` instance with the latest quote data,
        or `None` if no quote was found.
    """
    logger.info(f"Fetching latest quote for mic={mic!r}, symbol={symbol!r}")
    
    ql = await fetch_latest_quote(session, mic, symbol)
    if not ql:
        logger.warning(f"No latest quote found for mic={mic!r}, symbol={symbol!r}")
        return None
    
    return QuotePayloadOut(
        name=getattr(ql.instrument, "shortname", None),
        last_price=ql.last_price,
        change_pct=ql.change_pct,
        volume=ql.volume,
        last_trade_at=ql.last_trade_at,
    )


async def get_latest_bulk_service(session: AsyncSession, mic: str) -> BulkQuotesOut:
    """
    Fetch the latest quotes for all instruments on a given market.

    Args:
        session: Async SQLAlchemy database session.
        mic: Market MIC code (e.g. XWAR, XNCO).

    Returns:
        A `BulkQuotesOut` instance containing a mapping from instrument symbol
        to `QuotePayloadOut` with the latest quote for each instrument.
    """
    logger.info(f"Fetching bulk latest quotes for mic={mic!r}")
    
    rows = await fetch_latest_for_mic(session, mic)
    
    if not rows:
        logger.warning(f"No latest quotes found for mic={mic!r}")
        return None
    
    payload = {
        ql.instrument.symbol: QuotePayloadOut(
            name=getattr(ql.instrument, "shortname", None),
            last_price=ql.last_price,
            change_pct=ql.change_pct,
            volume=ql.volume,
            last_trade_at=ql.last_trade_at,
        )
        for ql in rows
    }
    bulk = BulkQuotesOut(payload)
    logger.debug(
        f"Built BulkQuotesOut for mic={mic!r} with {len(payload)} instruments"
    )
    return bulk
