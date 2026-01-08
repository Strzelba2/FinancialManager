from typing import Optional, Iterable, List
from datetime import date, datetime, timezone, timedelta, time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.quote_latest import (
    fetch_latest_quote, fetch_latest_for_mic, fetch_latest_quotes_by_symbols
)
from app.crud.instrument import get_instrument_by_symbol
from app.crud.candle_daily import get_min_max_date, upsert_candles_daily
from app.schemas.quates import (
    QuotePayloadOut, BulkQuotesOut, LatestQuoteBySymbol, SyncDailyResult, DailyRow
)

from app.utils.utils import build_st_url, download_text_csv
from app.markerdata.parser import parse_daily_csv

logger = logging.getLogger(__name__)


def chunks(items: list[DailyRow], n: int) -> Iterable[list[DailyRow]]:
    for i in range(0, len(items), n):
        yield items[i: i + n]


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


async def sync_daily_by_symbol(
    session: AsyncSession,
    symbol: str,
    overlap_days: int = 7,
    chunk_size: int = 1500,
    timeout_s: float = 30.0,
) -> SyncDailyResult:
    """
    Download and upsert daily candle data for a single instrument symbol.

    This function:
    - Resolves the instrument by `symbol`
    - Determines a sync window based on the latest stored candle date and `overlap_days`
    - Downloads daily candles as CSV from the configured historical source
    - Parses and filters rows to the sync window
    - Upserts candles in chunks into the database

    Args:
        session: SQLAlchemy async database session.
        symbol: Instrument symbol to sync (e.g. "AAPL", "PKO").
        overlap_days: Number of days to overlap from the last stored candle date (helps fix revisions).
        chunk_size: Batch size for DB upserts.
        timeout_s: Timeout (seconds) used for the upstream CSV download.

    Returns:
        A `SyncDailyResult` containing sync stats (fetched rows, upserted rows) and sync range.

    Raises:
        ValueError: If the instrument does not exist for the given `symbol`.
        Exception: Propagates unexpected failures (download/parse/db upsert), after logging.
    """
    logger.info(f"Request: sync_daily_by_symbol symbol={symbol} overlap_days={overlap_days} ")

    inst = await get_instrument_by_symbol(session, symbol=symbol)
    if inst is None:
        raise ValueError(f"Instrument not found for symbol={symbol}")

    src = (inst.historical_source or "").strip()
    if not src:
        logger.info(f"skip: sync_daily_by_symbol symbol={symbol} has no historical_source")
        return SyncDailyResult(
            symbol=symbol,
            instrument_id=inst.id,
            requested_url="",
            fetched_rows=0,
            upserted_rows=0,
        )

    today = datetime.now(timezone.utc).date()

    _, max_dt = await get_min_max_date(session, instrument_id=inst.id)
     
    start = (max_dt - timedelta(days=max(0, overlap_days))) if max_dt else None
    end = today - timedelta(days=1)
    
    if max_dt is not None and max_dt >= end:
        logger.info(f"symbol={symbol} already up-to-date (max_dt={max_dt} >= end={end}); skipping download.")
        return SyncDailyResult(
            symbol=symbol,
            instrument_id=inst.id,
            requested_url="",
            fetched_rows=0,
            upserted_rows=0,
            sync_start=None,
            sync_end=end,
        )
    
    url = build_st_url(src, start=start, end=end, interval="d")
    logger.info(f"sync: symbol={symbol} start={start} end={end} url={url}")

    text = await download_text_csv(url=url, timeout_s=timeout_s)
    rows = parse_daily_csv(text)
    fetched_rows = len(rows)

    if start is not None:
        rows = [r for r in rows if r.date_quote >= start]
    if end is not None:
        rows = [r for r in rows if r.date_quote <= end]

    upserted_total = 0
    for batch in chunks(rows, chunk_size):
        payload: list[dict] = []
        for r in batch:
            payload.append(
                {
                    "instrument_id": inst.id,
                    "date_quote": r.date_quote,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "trade_at": datetime.combine(r.date_quote, time(0, 0), tzinfo=timezone.utc),
                }
            )
        upserted_total += await upsert_candles_daily(session, rows=payload)

    return SyncDailyResult(
        symbol=symbol,
        instrument_id=inst.id,
        requested_url=url,
        fetched_rows=fetched_rows,
        upserted_rows=upserted_total,
        sync_start=start,
        sync_end=end,
    )
