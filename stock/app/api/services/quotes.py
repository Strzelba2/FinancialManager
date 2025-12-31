from typing import Optional, Iterable, List
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.quote_latest import fetch_latest_quote, fetch_latest_for_mic, fetch_latest_quotes_by_symbols
from app.schemas.quates import QuotePayloadOut, BulkQuotesOut, LatestQuoteBySymbol

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


async def get_latest_quotes_by_symbols(
    session: AsyncSession,
    symbols: Iterable[str],
) -> List[LatestQuoteBySymbol]:
    """
    Fetch the latest quotes for a set of instrument symbols.

    The function queries the database for the most recent quote per symbol and
    returns a normalized list of `LatestQuoteBySymbol`.

    Args:
        session: SQLAlchemy async database session.
        symbols: Iterable of instrument symbols (e.g., ["AAPL", "MSFT"]).

    Returns:
        A list of `LatestQuoteBySymbol` objects. If nothing is found, returns an empty list.
        Instruments without a `QuoteLatest` row are skipped.
    """
    rows = await fetch_latest_quotes_by_symbols(session=session, symbols=symbols)

    if not rows:
        logger.warning(
            f"get_latest_quotes_by_symbols: no rows returned for symbols={list(symbols)}"
        )
        return []

    out: List[LatestQuoteBySymbol] = []
    for inst, market, ql in rows:
        if ql is None:
            logger.warning(
                f"Instrument id={inst.id} symbol={inst.symbol} has no QuoteLatest row"
            )
            continue

        out.append(
            LatestQuoteBySymbol(
                symbol=inst.symbol,
                price=ql.last_price,
                currency=market.currency,
            )
        )

    logger.info(
        f"get_latest_quotes_by_symbols: returning {len(out)} quotes "
    )
    return out
