from fastapi import APIRouter, HTTPException, Query, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import List, Any
import asyncio
import uuid
import logging

from app.api.services.quotes import get_latest_quote_service, get_latest_bulk_service
from app.db.session import db
from app.schemas.schemas import (
    MarketOut, InstrumentOptionOut, InstrumentSearchRead, InstrumentRead
)
from app.schemas.quates import (
    LatestQuoteBySymbol, QuotesBySymbolsRequest, CandleDailyOut, SyncDailyResponse,
    SyncDailyRequest
)
from app.crud.market import list_markets
from app.crud.instrument import (
    list_instruments, search_instruments_by_shortname_or_name, get_instrument_by_symbol,
    get_instrument_with_market_by_mic_symbol
)
from app.api.services.quotes import get_latest_quotes_by_symbols, sync_daily_by_symbol
from app.crud.candle_daily import list_candles_daily
from app.markerdata.registry import get_provider
from app.api.services.stock import ingest_market

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("quotes/latest")
async def get_latest_quote(
    mic: str = Query(..., description="Market MIC, e.g. XWAR, XNCO"), 
    symbol: str = Query(..., description="Instrument symbol, e.g. PKN, AAPL"), 
    session: AsyncSession = Depends(db.get_session),
) -> dict[str, Any]:
    """
    Get the latest quote for a single instrument on a given market.

    Args:
        mic: Market MIC code (e.g. XWAR, XNCO).
        symbol: Instrument symbol (e.g. PKN, AAPL).
        session: SQLAlchemy async database session.

    Returns:
        A JSON-serializable dictionary representing the latest quote.

    Raises:
        HTTPException(404): If no quote is found for the given MIC and symbol.
    """
    logger.info(f"Request: get_latest_quote mic={mic!r}, symbol={symbol!r}")
    
    data = await get_latest_quote_service(session, mic, symbol)
    if data is None:
        logger.warning(f"No latest quote found for mic={mic!r}, symbol={symbol!r}")
        raise HTTPException(status_code=404, detail="Not found")
    
    dumped = data.model_dump(mode="json")
    logger.debug(f"Latest quote response for mic={mic!r}, symbol={symbol!r}: {dumped}")
    return dumped
   
    
@router.get("/quotes/latest/bulk")
async def get_latest_bulk(
    mic: str = Query(..., description="Market MIC, e.g. XWAR, XNCO"),
    session: AsyncSession = Depends(db.get_session),
):
    """
    Get the latest quotes for all instruments on a given market.

    Args:
        mic: Market MIC code (e.g. XWAR, XNCO).
        session: SQLAlchemy async database session.

    Returns:
        A JSON-serializable dictionary with bulk latest quotes for the given market.

    Raises:
        HTTPException(404): If there are no quotes for the given MIC.
    """
    logger.info(f"Request: get_latest_bulk mic={mic!r}")
    
    root = (await get_latest_bulk_service(session, mic)).model_dump(mode="json")
    if not root:
        logger.warning(f"No bulk quotes found for mic={mic!r}")
        raise HTTPException(status_code=404, detail="No quotes for MIC")
    
    logger.debug(f"Bulk latest quotes response for mic={mic!r}: {root}")
    return root


@router.get("/markets", response_model=list[MarketOut])
async def get_list_markets(session: AsyncSession = Depends(db.get_session)) -> list[MarketOut]:
    """
    List all configured markets.

    Args:
        session: SQLAlchemy async database session.

    Returns:
        A list of markets as `MarketOut` models.

    Raises:
        HTTPException(404): If there are no markets to display.
    """
    logger.info("Request: get_list_markets")
    
    list_of_markets = await list_markets(session)   
    if not list_of_markets:
        logger.warning("No markets found in database")
        raise HTTPException(status_code=404, detail="No markets to display")
    
    result = [MarketOut.model_validate(m) for m in list_of_markets]
    logger.debug(f"Markets response with {len(result)} items")
    return result


@router.get("/instruments/options", response_model=list[InstrumentOptionOut])
async def get_instrument_options(
    mic: str = Query(..., description="Market MIC, e.g. XWAR, XNCO"),
    session: AsyncSession = Depends(db.get_session),
) -> list[InstrumentOptionOut]:
    """
    Get a list of instruments for a given market as UI options.

    Args:
        mic: Market MIC code (e.g. XWAR, XNCO).
        session: SQLAlchemy async database session.

    Returns:
        A list of instrument options as `InstrumentOptionOut` models.

    Raises:
        HTTPException(404): If there are no instruments for the given market.
    """
    logger.info(f"Request: get_instrument_options mic={mic!r}")
    
    instruments = await list_instruments(session, mic=mic)

    if not instruments:
        logger.warning(f"No instruments found for market mic={mic!r}")
        raise HTTPException(status_code=404, detail="No instruments for this market")

    result = [InstrumentOptionOut.model_validate(i) for i in instruments]
    logger.debug(f"Instrument options response for mic={mic!r}: {len(result)} items")
    return result


@router.get("/instruments/resolve", response_model=InstrumentRead)
async def api_resolve_instrument(
    mic: str = Query(...),
    symbol: str = Query(...),
    session: AsyncSession = Depends(db.get_session),
) -> InstrumentRead:
    """
    Resolve a single instrument by MIC and symbol, returning instrument details
    enriched with market metadata (MIC and currency).

    Args:
        mic: Market Identifier Code (MIC) to search within.
        symbol: Instrument symbol/ticker within the given MIC.
        session: SQLAlchemy async database session.

    Returns:
        An `InstrumentRead` model with instrument fields plus `mic` and `currency`.

    Raises:
        HTTPException: 404 if no instrument is found for the given MIC+symbol.
    """
    result = await get_instrument_with_market_by_mic_symbol(
        session=session,
        mic=mic.strip().upper(),
        symbol=symbol.strip().upper(),
    )
    if not result:
        logger.info(
            f"api_resolve_instrument: instrument not found mic={mic}, symbol={symbol}"
        )
        raise HTTPException(status_code=404, detail="Instrument not found")

    inst, market = result

    return InstrumentRead(
        **inst.model_dump(),
        mic=market.mic,
        currency=market.currency,
    )


@router.get(
    "/instruments/search",
    response_model=List[InstrumentSearchRead],
)
async def search_instruments_endpoint(
    q: str = Query(..., description="Shortname or fragment of name"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    session: AsyncSession = Depends(db.get_session),
) -> list[InstrumentSearchRead]:
    """
    Search instruments by shortname or name fragment.

    Args:
        q: Search query; shortname or a fragment of the full name.
        limit: Maximum number of results to return (1–100).
        session: SQLAlchemy async database session.

    Returns:
        A list of instrument search results as `InstrumentSearchRead` models.
    """
    logger.info(f"Request: search_instruments_endpoint q={q!r}, limit={limit}")
    
    rows = await search_instruments_by_shortname_or_name(session, q, limit)

    result: list[InstrumentSearchRead] = []
    for inst, market in rows:
        result.append(
            InstrumentSearchRead(
                id=inst.id,
                isin=inst.isin,
                symbol=inst.symbol,
                shortname=inst.shortname,
                name=inst.name,
                type=inst.type,
                mic=market.mic,
            )
        )
    logger.debug(
        f"Search instruments response for q={q!r}, limit={limit}: {len(result)} items"
    )
    return result


@router.post("/quotes/latest/symbols", response_model=list[LatestQuoteBySymbol])
async def get_latest_by_symbols(
    payload: QuotesBySymbolsRequest,
    session: AsyncSession = Depends(db.get_session),
) -> list[LatestQuoteBySymbol]:
    """
    Get the latest quotes for a list of symbols.

    Args:
        payload: Request body containing `symbols` (list of instrument symbols).
        session: SQLAlchemy async database session.

    Returns:
        A list of latest quotes as `LatestQuoteBySymbol` models.

    Raises:
        HTTPException: 404 if no quotes were found for the provided symbols.
    """
    symbols = payload.symbols
    logger.info(f"Request: get_latest_by_symbols symbols_count={len(symbols)} symbols={symbols!r}")
                
    quotes = await get_latest_quotes_by_symbols(session, symbols)
    
    if not quotes:
        logger.warning(f"No quotes found for symbols={symbols!r}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No quotes for given symbols",
        )
        
    logger.debug(f"Response: get_latest_by_symbols returned {len(quotes)} quotes for symbols={symbols!r}")
    return quotes


@router.post("/instruments/{symbol}/candles/daily/sync", response_model=SyncDailyResponse)
async def sync_daily_candles(
    symbol: str,
    payload: SyncDailyRequest,
    session: AsyncSession = Depends(db.get_session),
) -> SyncDailyResponse:
    """
    Sync daily candles for a single instrument symbol.

    Runs a daily-candle synchronization (upsert) and optionally returns candles
    from the database (either the sync window / requested range, or all data).

    Args:
        symbol: Instrument symbol (path param).
        payload: Request body controlling overlap, date range, and whether to return items.
        session: SQLAlchemy async database session.

    Returns:
        A `SyncDailyResponse` containing sync stats and optionally candle items.

    Raises:
        HTTPException: 404 if the instrument symbol does not exist.
        HTTPException: 500 if the sync or database operations fail unexpectedly.
    """
    logger.info(f"Request: sync_daily_candles symbol={symbol} ")
    inst = await get_instrument_by_symbol(session, symbol=symbol)
  
    if inst is None:
        logger.warning(f"Instrument not found: sync_daily_candles symbol={symbol}")
        raise HTTPException(status_code=404, detail=f"Instrument not found: {symbol}")

    await session.rollback()
    async with session.begin():
        sync_res = await sync_daily_by_symbol(
            session,
            symbol=symbol,
            overlap_days=payload.overlap_days,
        )

    if not payload.include_items:
        logger.info(
            f"daily sync endpoint: symbol={symbol} fetched={sync_res.fetched_rows} "
            f"upserted={sync_res.upserted_rows} returned=0 (include_items=False)"
        )
        return SyncDailyResponse(
            sync=sync_res,
            items_included=False,
            returned_count=0,
            items=None,
        )

    if payload.return_all:
        q_from, q_to = None, None
    else:
        q_from = payload.date_from if payload.date_from is not None else sync_res.sync_start
        q_to = payload.date_to if payload.date_to is not None else sync_res.sync_end

    items_db = await list_candles_daily(
        session,
        instrument_id=inst.id,
        date_from=q_from,
        date_to=q_to,
    )
    items = [CandleDailyOut.model_validate(x) for x in items_db]

    logger.info(
        f"daily sync endpoint: symbol={symbol} fetched={sync_res.fetched_rows} "
        f"upserted={sync_res.upserted_rows} returned={len(items)}"
    )

    return SyncDailyResponse(
        sync=sync_res,
        items_included=True,
        returned_count=len(items),
        items=items,
    )
    
    
@router.get("/celery/status")
async def celery_status() -> dict[str, Any]:
    """
    Report whether Celery workers are reachable by sending a control "ping"
    and collecting replies.

    The endpoint is intended for health checks and operational monitoring.

    Returns:
        A dict with:
          - enabled: Whether Celery integration is enabled in this service.
          - online: True if at least one worker replied to ping.
          - workers: List of worker node names that replied.
          - detail: Short textual status ("pong", reason, error message).
    """
    logger.info("Request: celery_status")
  
    try:
        from app.core.celery_app import celery_app
        try:
            res = celery_app.control.broadcast("ping", reply=True, timeout=1)
        except Exception as ex:
            logger.warning(f"celery ping failed: {ex}")
            return {"enabled": True, "online": False, "workers": [], "detail": str(ex)}

        if not res:
            logger.info("celery_status: no ping response from celery workers")
            return {
                "enabled": True,
                "online": False,
                "workers": [],
                "detail": "No ping response from celery workers",
            }

        return {
            "enabled": True,
            "online": True,
            "workers": list(res.keys()),
            "detail": "pong",
        }

    except Exception as ex:
        logger.exception("celery_status failed")
        return {
            "enabled": True,
            "online": False,
            "workers": [],
            "detail": f"inspect failed: {ex!r}",
        }
        
        
@router.post("/ingest/start_manual")
async def start_manual_ingest(
    request: Request
) -> dict[str, Any]:
    """
    Start a manual ingestion job in the background.

    The endpoint uses a short-lived lock in storage to prevent multiple ingest
    jobs from running concurrently.

    Args:
        request: FastAPI request object (used to access application storage).

    Returns:
        A dict with:
          - ok: True if the job was started, False if it was blocked.
          - job_id: ID of the started job (only when ok=True).
          - detail: Optional error/diagnostic message.
    """
    logger.info("Request: start_manual_ingest")
    
    storage = request.app.storage

    if await storage.stock.exists("ingest:lock"):
        return {"ok": False, "detail": "ingest already running"}

    job_id = str(uuid.uuid4())
    job_key = "ingest:quotes:status"
    
    logger.info(f"start_manual_ingest: starting job_id={job_id!r}")

    await storage.stock.set("ingest:lock", {"job_id": job_id}, timeout=60 * 60)  
    
    now = datetime.now(timezone.utc).isoformat()
    
    await storage.stock.hmset(job_key, {"state": "running", "started_at": now}, ttl=60 * 60)

    async def _run():
        logger.info(f"start_manual_ingest._run: job started job_id={job_id!r}")
        try:
            provider = get_provider("market") 
            async with db.async_session() as session:
                all_processed = 0
                for market_key in ("pl-wse", "pl-newconnect", "commodities", "cpi"):
                    logger.debug(
                            f"ingest_quarter: processing market_key={market_key!r}"
                        )

                    all_processed += await ingest_market(session, provider, market_key, storage)

            await storage.stock.hmset(job_key, {"state": "done"}, ttl=60 * 60)

        except Exception as ex:
            logger.exception(f"start_manual_ingest._run: job failed job_id={job_id!r}")
            await storage.stock.hmset(job_key, {"state": "error", "detail": str(ex)}, ttl=60 * 60)

        finally:
            try:
                await storage.stock.clear("ingest:lock")
            except Exception as ex:
                logger.warning(
                    f"start_manual_ingest._run: failed to clear lock job_id={job_id!r}: {ex!r}"
                )

    asyncio.create_task(_run())
    return {"ok": True}
