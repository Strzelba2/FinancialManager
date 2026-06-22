from fastapi import APIRouter, HTTPException, Query, Depends, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, date
from typing import Annotated, List, Any, Optional
import asyncio
import uuid
import logging

from app.models.models import Market
from app.api.services.quotes import get_latest_quote_service, get_latest_bulk_service
from app.db.session import db
from app.schemas.schemas import (
    MarketCreate,
    MarketOut,
    InstrumentCreate,
    InstrumentManualCreate,
    InstrumentOptionOut,
    InstrumentSearchRead,
    InstrumentRead,
    InstrumentShortnameUpdate,
)
from app.schemas.quotes import (
    LatestQuoteBySymbol, QuotesBySymbolsRequest, CandleDailyOut, SyncDailyResponse,
    SyncDailyRequest, ImportDailyCsvRequest, SyncDailyResult
)
from app.schemas.volume_zones import AnalysisMode, VolumeZonesResponse
from app.crud.market import create_market, get_market_id_by_mic, list_markets
from app.crud.instrument import (
    create_instrument, list_instruments, search_instruments_by_shortname_or_name, get_instrument_by_symbol,
    get_instrument_with_market_by_mic_symbol, update_instrument_shortname,
)
from app.api.services.quotes import (
    get_latest_quotes_by_symbols, sync_daily_by_symbol, import_daily_csv_by_symbol,
)
from app.crud.candle_daily import list_candles_daily
from app.crud.report_snapshot import get_latest_ready_report_ai_snapshot
from app.markerdata.registry import get_provider
from app.models.enums import ReportAssetClass
from app.api.services.stock import ingest_market, refresh_quote_source_instruments
from app.analysis.volume_zones import analyze_volume_zones
from app.analysis.volume_zones.cache import CACHE_TTL_SECONDS, volume_zones_cache_key
from app.analysis.volume_zones.free_float import extract_free_float_snapshot
from app.core.config import settings
from app.reports.equity.schemas import EquityReportResponse
from app.reports.equity.service import (
    ReportConflictError,
    ReportGenerationError,
    ReportNotFoundError,
    get_equity_report,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _instrument_read_with_mic(inst: Any, mic: str) -> InstrumentRead:
    if inst.currency is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Instrument currency must be set in stock.",
        )
    return InstrumentRead(
        **inst.model_dump(),
        mic=mic,
    )


async def _build_sync_daily_response(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    sync_res: SyncDailyResult,
    include_items: bool,
    return_all: bool,
    date_from: date | None,
    date_to: date | None,
) -> SyncDailyResponse:
    if not include_items:
        return SyncDailyResponse(
            sync=sync_res,
            items_included=False,
            returned_count=0,
            items=None,
        )

    if return_all:
        q_from, q_to = None, None
    else:
        q_from = date_from if date_from is not None else sync_res.sync_start
        q_to = date_to if date_to is not None else sync_res.sync_end

    items_db = await list_candles_daily(
        session,
        instrument_id=instrument_id,
        date_from=q_from,
        date_to=q_to,
    )
    items = [CandleDailyOut.model_validate(x) for x in items_db]

    return SyncDailyResponse(
        sync=sync_res,
        items_included=True,
        returned_count=len(items),
        items=items,
    )


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

    data = await get_latest_bulk_service(session, mic)
    if data is None or not data.root:
        logger.warning(f"No bulk quotes found for mic={mic!r}")
        raise HTTPException(status_code=404, detail="No quotes for MIC")

    root = data.model_dump(mode="json")
    logger.debug(f"Bulk latest quotes response for mic={mic!r}: {root}")
    return root


@router.get("/markets", response_model=list[MarketOut])
async def get_list_markets(
    only_with_instruments: bool = Query(False),
    session: AsyncSession = Depends(db.get_session),
) -> list[MarketOut]:
    """
    List all configured markets.

    Args:
        session: SQLAlchemy async database session.

    Returns:
        A list of markets as `MarketOut` models.

    Raises:
        HTTPException(404): If there are no markets to display.
    """
    logger.info("Request: get_list_markets only_with_instruments=%r", only_with_instruments)
    
    list_of_markets = await list_markets(
        session,
        only_with_instruments=only_with_instruments,
    )
    if not list_of_markets:
        logger.warning("No markets found in database")
        raise HTTPException(status_code=404, detail="No markets to display")
    
    result = [MarketOut.model_validate(m) for m in list_of_markets]
    logger.debug(f"Markets response with {len(result)} items")
    return result


@router.post(
    "/markets",
    response_model=MarketOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_market_endpoint(
    payload: MarketCreate,
    session: AsyncSession = Depends(db.get_session),
) -> MarketOut:
    logger.info("Request: create_market_endpoint mic=%r", payload.mic)
    try:
        async with session.begin():
            market = await create_market(session, payload)
        return MarketOut.model_validate(market)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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


@router.post(
    "/instruments",
    response_model=InstrumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_instrument_endpoint(
    payload: InstrumentManualCreate,
    session: AsyncSession = Depends(db.get_session),
) -> InstrumentRead:
    market_id = payload.market_id
    if market_id is None:
        if not payload.market_mic:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="market_id or market_mic is required",
            )
        market_id = await get_market_id_by_mic(session, payload.market_mic.strip().upper())
        await session.rollback()

    if market_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Market not found.",
        )

    market = await session.get(Market, market_id)
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Market not found.",
        )
    market_mic = market.mic
    await session.rollback()
    if payload.currency is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Instrument currency is required.",
        )

    data = InstrumentCreate(
        **payload.model_dump(exclude={"market_id", "market_mic"}),
        market_id=market_id,
    )

    try:
        async with session.begin():
            instrument = await create_instrument(session, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _instrument_read_with_mic(instrument, market_mic)


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

    return _instrument_read_with_mic(inst, market.mic)


@router.patch("/instruments/{symbol}/shortname", response_model=InstrumentRead)
async def api_update_instrument_shortname(
    symbol: Annotated[str, Path(min_length=1, max_length=12)],
    payload: InstrumentShortnameUpdate,
    mic: Annotated[str, Query(min_length=4, max_length=4, pattern=r"^[A-Za-z0-9]{4}$")],
    session: AsyncSession = Depends(db.get_session),
) -> InstrumentRead:
    """Update the quote display name with optimistic concurrency protection."""
    mic_u = mic.strip().upper()
    symbol_u = symbol.strip().upper()

    try:
        async with session.begin():
            result = await update_instrument_shortname(
                session=session,
                mic=mic_u,
                symbol=symbol_u,
                shortname=payload.shortname,
                expected_shortname=payload.expected_shortname,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")

    instrument, market = result
    return _instrument_read_with_mic(instrument, market.mic)


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


@router.get("/reports/{mic}/{symbol}", response_model=EquityReportResponse)
async def get_equity_report_endpoint(
    mic: str,
    symbol: str,
    request: Request,
    period: Optional[str] = Query(default=None, description="Quarter key in YYYY-QN format"),
    session: AsyncSession = Depends(db.get_session),
) -> EquityReportResponse:
    logger.info(
        "Request: get_equity_report mic=%r symbol=%r period=%r",
        mic,
        symbol,
        period,
    )
    try:
        return await get_equity_report(
            session=session,
            storage=request.app.storage,
            mic=mic,
            symbol=symbol,
            period=period,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReportGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/analysis/{mic}/{symbol}/volume-zones", response_model=VolumeZonesResponse)
async def get_volume_zones_endpoint(
    mic: str,
    symbol: str,
    request: Request,
    mode: AnalysisMode = Query(default="summary"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_timeline: bool = Query(default=False),
    max_zones: int = Query(default=3, ge=1, le=20),
    session: AsyncSession = Depends(db.get_session),
) -> VolumeZonesResponse:
    logger.info(
        "Request: get_volume_zones mic=%r symbol=%r mode=%r date_from=%r date_to=%r",
        mic,
        symbol,
        mode,
        date_from,
        date_to,
    )
    resolved = await get_instrument_with_market_by_mic_symbol(
        session=session,
        mic=mic.strip().upper(),
        symbol=symbol.strip().upper(),
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Instrument not found")

    inst, market = resolved
    candles = list(
        await list_candles_daily(
            session,
            instrument_id=inst.id,
            date_from=date_from,
            date_to=date_to,
        )
    )
    last_candle_date = candles[-1].date_quote if candles else None
    ai_snapshot = await get_latest_ready_report_ai_snapshot(
        session=session,
        instrument_id=inst.id,
        asset_class=ReportAssetClass.EQUITY,
        schema_version=settings.REPORT_SCHEMA_VERSION,
    )
    free_float = extract_free_float_snapshot(
        ai_snapshot.ai_payload if ai_snapshot is not None else None,
        source="report_ai_snapshot",
    )
    free_float_version = (
        f"{ai_snapshot.id}:{ai_snapshot.generated_at.isoformat()}"
        if ai_snapshot is not None and free_float is not None
        else None
    )
    cache_key = volume_zones_cache_key(
        mic=market.mic,
        symbol=inst.symbol,
        mode=mode,
        date_from=date_from,
        date_to=date_to,
        include_timeline=include_timeline,
        max_zones=max_zones,
        last_candle_date=last_candle_date,
        free_float_version=free_float_version,
    )
    cached = await request.app.storage.stock.get(cache_key)
    if cached is not None:
        return VolumeZonesResponse.model_validate(cached)

    try:
        response = analyze_volume_zones(
            candles,
            symbol=inst.symbol,
            mic=market.mic,
            mode=mode,
            include_timeline=include_timeline,
            max_zones=max_zones,
            free_float=free_float,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await request.app.storage.stock.set(
        cache_key,
        response.model_dump(mode="json"),
        timeout=CACHE_TTL_SECONDS,
    )
    return response


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
    try:
        sync_res = await sync_daily_by_symbol(
            session,
            symbol=symbol,
            overlap_days=payload.overlap_days,
        )
    except HTTPException:
        # Persist sync-state failure details written inside the service so the
        # next request and diagnostics can see the real upstream error.
        await session.commit()
        raise
    except Exception:
        await session.rollback()
        raise
    else:
        await session.commit()

    response = await _build_sync_daily_response(
        session=session,
        instrument_id=inst.id,
        sync_res=sync_res,
        include_items=payload.include_items,
        return_all=payload.return_all,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )

    logger.info(
        f"daily sync endpoint: symbol={symbol} fetched={sync_res.fetched_rows} "
        f"upserted={sync_res.upserted_rows} returned={response.returned_count}"
    )
    return response


@router.post("/instruments/{symbol}/candles/daily/import_csv", response_model=SyncDailyResponse)
async def import_daily_candles_csv(
    symbol: str,
    payload: ImportDailyCsvRequest,
    session: AsyncSession = Depends(db.get_session),
) -> SyncDailyResponse:
    logger.info(
        f"Request: import_daily_candles_csv symbol={symbol} filename={payload.filename!r}"
    )
    inst = await get_instrument_by_symbol(session, symbol=symbol)

    if inst is None:
        logger.warning(f"Instrument not found: import_daily_candles_csv symbol={symbol}")
        raise HTTPException(status_code=404, detail=f"Instrument not found: {symbol}")

    await session.rollback()
    try:
        sync_res = await import_daily_csv_by_symbol(
            session,
            symbol=symbol,
            content_b64=payload.content_b64,
            filename=payload.filename,
        )
    except HTTPException:
        await session.commit()
        raise
    except Exception:
        await session.rollback()
        raise
    else:
        await session.commit()

    response = await _build_sync_daily_response(
        session=session,
        instrument_id=inst.id,
        sync_res=sync_res,
        include_items=payload.include_items,
        return_all=payload.return_all,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )

    logger.info(
        f"daily import endpoint: symbol={symbol} fetched={sync_res.fetched_rows} "
        f"upserted={sync_res.upserted_rows} returned={response.returned_count}"
    )
    return response
    
    
@router.get("/celery/status")
async def celery_status() -> dict[str, Any]:
    """
    Report whether STOCK Celery workers are reachable on the stock queue.

    The endpoint is intended for health checks and operational monitoring.

    Returns:
        A dict with:
          - enabled: Whether Celery integration is enabled in this service.
          - online: True if at least one worker replied to ping and listens on
            the STOCK queue.
          - workers: List of STOCK worker node names.
          - detail: Short textual status ("pong", reason, error message).
    """
    logger.info("Request: celery_status")
  
    try:
        from app.core.celery_app import celery_app
        stock_queue = str(celery_app.conf.task_default_queue or "stock_tasks")

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

        workers: list[str] = []
        if isinstance(res, dict):
            workers = list(res.keys())
        elif isinstance(res, list):
            for item in res:
                if isinstance(item, dict):
                    workers.extend(str(name) for name in item.keys())

        if not workers:
            logger.warning(f"celery_status: unexpected ping payload shape: {type(res)!r}")

        inspect = celery_app.control.inspect(timeout=1)
        try:
            active_queues = inspect.active_queues() or {}
        except Exception as ex:
            logger.warning(f"celery active_queues inspect failed: {ex}")
            active_queues = {}

        stock_workers: list[str] = []
        for worker_name in workers:
            queues = active_queues.get(worker_name) or []
            queue_names = {
                str(q.get("name"))
                for q in queues
                if isinstance(q, dict) and q.get("name")
            }
            if stock_queue in queue_names:
                stock_workers.append(worker_name)

        if not stock_workers:
            logger.info(
                f"celery_status: ping replies received from non-stock workers only: "
                f"workers={workers}, stock_queue={stock_queue!r}"
            )
            return {
                "enabled": True,
                "online": False,
                "workers": [],
                "detail": f"No worker subscribed to queue {stock_queue}",
            }

        return {
            "enabled": True,
            "online": True,
            "workers": stock_workers,
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

                quote_source_result = await refresh_quote_source_instruments(session, storage)

            await storage.stock.hmset(
                job_key,
                {
                    "state": "done",
                    "processed": all_processed,
                    "quote_source_processed": quote_source_result["processed"],
                    "quote_source_failed": quote_source_result["failed"],
                    "quote_source_errors": quote_source_result["errors"][:10],
                },
                ttl=60 * 60,
            )

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
    return {"ok": True, "job_id": job_id}


@router.get("/ingest/status")
async def get_manual_ingest_status(request: Request) -> dict[str, Any]:
    """
    Return the current manual quotes ingestion status stored in app storage.

    Returns:
        A dict describing the current ingest status. If there is no recorded
        job state yet, returns `{"state": "idle"}`.
    """
    logger.info("Request: get_manual_ingest_status")

    storage = request.app.storage
    data = await storage.stock.hgetall("ingest:quotes:status")

    if not data:
        return {"state": "idle"}

    return dict(data)
