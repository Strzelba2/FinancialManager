import base64
import binascii
from typing import Optional, Iterable, List
from datetime import datetime, timezone, timedelta, time, date
from fastapi import HTTPException
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.quote_latest import (
    fetch_latest_quote, fetch_latest_for_mic, fetch_latest_quotes_by_symbols,
    get_latest_trade_date_by_symbol,
)
from app.crud.instrument import get_instrument_by_symbol
from app.crud.candle_daily import get_min_max_date, upsert_candles_daily
from app.crud.instrument_sync import (
    should_skip_daily_sync, mark_daily_attempt, get_or_create_sync_state,
    mark_daily_failure, mark_daily_success
)
from app.schemas.quotes import (
    QuotePayloadOut, BulkQuotesOut, LatestQuoteBySymbol, SyncDailyResult, DailyRow
)

from app.utils.utils import build_st_url as build_historical_url, download_text_csv
from app.markerdata.parser import parse_daily_csv
from app.markerdata.historical_browser import requires_browser_fetch, fetch_csv_via_browser
from app.exceptions import UpstreamDownloadError

logger = logging.getLogger(__name__)


def chunks(items: list[DailyRow], n: int) -> Iterable[list[DailyRow]]:
    for i in range(0, len(items), n):
        yield items[i: i + n]


def _decode_daily_csv_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("Uploaded file could not be decoded as text CSV")


def _rows_span(rows: list[DailyRow]) -> tuple[Optional[date], Optional[date]]:
    if not rows:
        return None, None

    dates = [row.date_quote for row in rows]
    return min(dates), max(dates)


async def _upsert_daily_row_batches(
    session: AsyncSession,
    instrument_id,
    rows: list[DailyRow],
    chunk_size: int,
) -> int:
    upserted_total = 0
    for batch in chunks(rows, chunk_size):
        payload: list[dict] = []
        for r in batch:
            payload.append(
                {
                    "instrument_id": instrument_id,
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

    return upserted_total


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
        currency=getattr(ql.instrument, "currency", None),
    )


async def get_latest_bulk_service(session: AsyncSession, mic: str) -> Optional[BulkQuotesOut]:
    """
    Fetch the latest quotes for all instruments on a given market.

    Args:
        session: Async SQLAlchemy database session.
        mic: Market MIC code (e.g. XWAR, XNCO).

    Returns:
        A `BulkQuotesOut` instance containing a mapping from instrument symbol
        to `QuotePayloadOut` with the latest quote for each instrument,
        or `None` if there are no stored latest quotes for the market.
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
            currency=getattr(ql.instrument, "currency", None),
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
        if inst.currency is None:
            logger.warning(
                f"Instrument id={inst.id} symbol={inst.symbol} has no quote currency"
            )
            continue

        out.append(
            LatestQuoteBySymbol(
                symbol=inst.symbol,
                price=ql.last_price,
                currency=inst.currency,
                change_pct=ql.change_pct
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
            name=inst.shortname,
            instrument_id=inst.id,
            requested_url="",
            fetched_rows=0,
            upserted_rows=0,
        )

    now = datetime.now(timezone.utc)
    today = now.date()
    latest_trade_date = await get_latest_trade_date_by_symbol(session, symbol=symbol)

    _, max_dt = await get_min_max_date(session, instrument_id=inst.id)
     
    start = (max_dt - timedelta(days=max(0, overlap_days))) if max_dt else None
    end = today - timedelta(days=1)

    if latest_trade_date is not None and latest_trade_date < end:
        logger.info(
            f"sync_daily_by_symbol: capping end for symbol={symbol} "
            f"from {end} to latest_trade_date={latest_trade_date}"
        )
        end = latest_trade_date
    
    if max_dt is not None and max_dt >= end:
        logger.info(f"symbol={symbol} already up-to-date (max_dt={max_dt} >= end={end}); skipping download.")
        return SyncDailyResult(
            symbol=symbol,
            name=inst.shortname,
            instrument_id=inst.id,
            requested_url="",
            fetched_rows=0,
            upserted_rows=0,
            sync_start=None,
            sync_end=end,
        )
    
    url = build_historical_url(src, start=start, end=end, interval="d")
    logger.info(f"sync: symbol={symbol} start={start} end={end} url={url}")
    
    state = await get_or_create_sync_state(session, inst.id)
    
    if should_skip_daily_sync(state, today=today, target_end=end):
        logger.info(
            f"skip: symbol={symbol} already handled for target_end={end} "
            f"(success_end={state.daily_last_success_end}, attempt_end={state.daily_last_attempt_end})"
        )
        return SyncDailyResult(
            symbol=symbol,
            name=inst.shortname,
            instrument_id=inst.id,
            requested_url="",
            fetched_rows=0,
            upserted_rows=0,
            sync_start=None,
            sync_end=end,
        )

    await mark_daily_attempt(session, state, now=now, target_end=end, requested_url=url)
    try:
        if requires_browser_fetch(src):
            logger.info(
                f"sync_daily_by_symbol: using browser-assisted fetch symbol={symbol}"
            )
            text = await fetch_csv_via_browser(
                historical_source=src,
                start=start,
                end=end,
                timeout_ms=max(int(timeout_s * 1000), 20000),
            )
        else:
            text = await download_text_csv(url=url, timeout_s=timeout_s)
        rows = parse_daily_csv(text)
    except UpstreamDownloadError as e:
        logger.error(f"sync_daily_candles upstream error symbol={symbol} err={e}")
        state = await get_or_create_sync_state(session, inst.id)
        await mark_daily_failure(session, state, error=str(e))
        raise HTTPException(status_code=503, detail=str(e))
    fetched_rows = len(rows)

    if fetched_rows == 0:
        msg = (
            f"Upstream returned no candle rows for symbol={symbol} "
            f"(url={url})"
        )
        logger.error(msg)
        state = await get_or_create_sync_state(session, inst.id)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=503, detail=msg)

    if start is not None:
        rows = [r for r in rows if r.date_quote >= start]
    if end is not None:
        rows = [r for r in rows if r.date_quote <= end]

    sync_start, sync_end = _rows_span(rows)
    if sync_end is None:
        msg = (
            f"Upstream returned no candle rows in requested sync window for symbol={symbol} "
            f"(start={start}, end={end}, url={url})"
        )
        logger.error(msg)
        state = await get_or_create_sync_state(session, inst.id)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=503, detail=msg)

    if sync_end < end:
        logger.info(
            f"sync_daily_by_symbol: upstream latest row for symbol={symbol} "
            f"is {sync_end}, earlier than target_end={end}"
        )

    upserted_total = await _upsert_daily_row_batches(
        session=session,
        instrument_id=inst.id,
        rows=rows,
        chunk_size=chunk_size,
    )
        
    state = await get_or_create_sync_state(session, inst.id)
    await mark_daily_success(
        session,
        state,
        now=datetime.now(timezone.utc),
        target_end=sync_end,
        fetched_rows=fetched_rows,
        upserted_rows=upserted_total,
    )

    return SyncDailyResult(
        symbol=symbol,
        name=inst.shortname,
        instrument_id=inst.id,
        requested_url=url,
        fetched_rows=fetched_rows,
        upserted_rows=upserted_total,
        sync_start=sync_start,
        sync_end=sync_end,
    )


async def import_daily_csv_by_symbol(
    session: AsyncSession,
    symbol: str,
    content_b64: str,
    filename: Optional[str] = None,
    chunk_size: int = 1500,
) -> SyncDailyResult:
    logger.info(f"Request: import_daily_csv_by_symbol symbol={symbol} filename={filename!r}")

    inst = await get_instrument_by_symbol(session, symbol=symbol)
    if inst is None:
        raise ValueError(f"Instrument not found for symbol={symbol}")

    now = datetime.now(timezone.utc)
    state = await get_or_create_sync_state(session, inst.id)
    safe_filename = (filename or "manual.csv").strip() or "manual.csv"
    requested_url = f"upload:{safe_filename[:180]}"
    fallback_end = now.date()

    try:
        raw_bytes = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError):
        msg = f"Invalid base64 payload for uploaded CSV: symbol={symbol}"
        logger.error(msg)
        await mark_daily_attempt(session, state, now=now, target_end=fallback_end, requested_url=requested_url)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=422, detail=msg)

    if not raw_bytes:
        msg = f"Uploaded CSV file is empty for symbol={symbol}"
        logger.error(msg)
        await mark_daily_attempt(session, state, now=now, target_end=fallback_end, requested_url=requested_url)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=422, detail=msg)

    try:
        text = _decode_daily_csv_bytes(raw_bytes)
    except ValueError as e:
        msg = f"{e}: symbol={symbol}"
        logger.error(msg)
        await mark_daily_attempt(session, state, now=now, target_end=fallback_end, requested_url=requested_url)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=422, detail=msg)

    rows = parse_daily_csv(text)
    fetched_rows = len(rows)
    if fetched_rows == 0:
        msg = (
            f"Uploaded CSV does not contain any daily candle rows for symbol={symbol}. "
            "Expected columns like Date,Open,High,Low,Close,Volume."
        )
        logger.error(msg)
        await mark_daily_attempt(session, state, now=now, target_end=fallback_end, requested_url=requested_url)
        await mark_daily_failure(session, state, error=msg)
        raise HTTPException(status_code=422, detail=msg)

    sync_start, sync_end = _rows_span(rows)
    target_end = sync_end or fallback_end

    await mark_daily_attempt(session, state, now=now, target_end=target_end, requested_url=requested_url)

    upserted_total = await _upsert_daily_row_batches(
        session=session,
        instrument_id=inst.id,
        rows=rows,
        chunk_size=chunk_size,
    )

    await mark_daily_success(
        session,
        state,
        now=datetime.now(timezone.utc),
        target_end=target_end,
        fetched_rows=fetched_rows,
        upserted_rows=upserted_total,
    )

    return SyncDailyResult(
        symbol=symbol,
        name=inst.shortname,
        instrument_id=inst.id,
        requested_url=requested_url,
        fetched_rows=fetched_rows,
        upserted_rows=upserted_total,
        sync_start=sync_start,
        sync_end=sync_end,
    )
