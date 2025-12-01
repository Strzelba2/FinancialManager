from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import async_playwright
from contextlib import suppress
from typing import Any, Dict, Optional
import logging

from app.markerdata.provider import MarketProvider
from app.core.cache.redis import Storage
from app.crud.quote_latest import upsert_quote_latest
from app.crud.market import get_market_id_by_mic
from app.crud.instrument import count_by_market_id, get_by_symbol_in_market, create_instrument
from app.schemas.schemas import QuoteLatesInput
from app.core.clients.gpw_client import GpwListingsClient
from app.utils.numbers import parse_float_pl, parse_int_pl
from app.utils.dates import parse_last_trade_at

logger = logging.getLogger(__name__)


async def ingest_market(session: AsyncSession, 
                        provider: MarketProvider, 
                        market_key: str, storage: Storage, ) -> int:
    """
    Ingest the latest quotes for a given market using a browser-based provider.

    This function:
    - Resolves the market configuration from the `provider` and `market_key`
    - Ensures the market exists in the database
    - Optionally loads GPW symbol map (for XWAR/XNCO) to fill in missing ISINs
    - Iterates over provider rows and:
        * Creates instruments if missing
        * Upserts latest quote records
        * Stores latest quote snapshots in the `storage` (e.g. Redis)

    Args:
        session: Async SQLAlchemy session.
        provider: Market provider capable of yielding instrument/quote rows.
        market_key: Provider-specific key identifying the market configuration.
        storage: Storage backend (e.g. Redis wrapper) for caching quotes.

    Returns:
        Number of successfully processed rows (quotes).

    Raises:
        ValueError: If the market cannot be found in the database.
        Exception: If nothing is processed and too many rows fail.
    """ 
    
    processed = 0
    failed = 0
    
    logger.info(
        f"Starting ingest_market for market_key={market_key!r}, "
        f"provider={provider.__class__.__name__}"
    )
    
    config = provider.get_config(market_key)
    
    market_uuid = await get_market_id_by_mic(session, config.mic)
    if not market_uuid:
        logger.error(
            f"Market with MIC={config.mic!r} not found; "
            f"make sure markets are seeded before ingestion."
        )
        raise ValueError(f"Market with MIC={config.mic} not found; seed markets first.")

    existing = await count_by_market_id(session, market_id=market_uuid)
    await session.rollback()
    logger.info(
        f"Existing instruments for market mic={config.mic!r}: count={existing}"
    )
    
    symbol_map: Dict[str, Dict[str, Any]] = {}
    gpw_client: Optional[GpwListingsClient] = None
    
    if config.mic in ("XWAR", "XNCO"):
        logger.info(
            f"Loading GPW symbol map for mic={config.mic!r} "
            "(used to fill missing ISINs)."
        )
        gpw_client = GpwListingsClient()
        try:
            symbol_map = await gpw_client.get_symbol_map()
        finally:
            await gpw_client.aclose()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ],
        )
        ctx = await browser.new_context(locale="pl-PL")
        page = await ctx.new_page()
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(10000)
        
        logger.info(
            f"Browser started for ingest_market, mic={config.mic!r}, "
            "beginning row iteration."
        )
        
        try:
            async for instrument, quate_latest in provider.iter_rows_mapped(page, config, market_id=market_uuid):

                try:
                    async with session.begin():
                        inst = await get_by_symbol_in_market(session, market_id=market_uuid, symbol=instrument.symbol)
            
                        if not inst:
                            logger.info(
                                f"Instrument not found in DB for symbol={instrument.symbol!r}; "
                                "attempting to create."
                            )
                            try:
                                rec = symbol_map.get(instrument.symbol)
                                if rec:
                                    if getattr(instrument, "isin", None) is None:
                                        isin = rec["ISIN"]
                                        if isin != "nan":
                                            instrument = instrument.model_copy(
                                                update={
                                                    "isin": rec["ISIN"],
                                                }
                                            )
                                            logger.info(
                                                f"Assigned ISIN={isin!r} "
                                                f"to instrument symbol={instrument.symbol!r}"
                                            )
                            except Exception:
                                logger.warning(f"Can not assigne ISIN for {instrument.symbol}")
                                
                            logger.debug(
                                f"Creating instrument in DB: "
                                f"symbol={instrument.symbol!r}, isin={instrument.isin!r}"
                            )
                            inst = await create_instrument(session, instrument)
                            
                            logger.info(
                                f"Created instrument id={inst.id}, symbol={inst.symbol!r}, "
                                f"isin={inst.isin!r}"
                            )
                            
                        latest = await upsert_quote_latest(session, inst.id, quate_latest)
                        
                    await storage.stock.hset(
                        key=f"latest_quote:{config.mic}",      
                        field=inst.symbol,
                        value={
                            "name": inst.shortname,
                            "last_price": str(latest.last_price),
                            "change_pct": str(latest.change_pct),
                            "volume": latest.volume,
                            "last_trade_at": latest.last_trade_at.isoformat(),
                        },
                        ttl=3600, 
                    )
                    
                    processed += 1
  
                except Exception as row_err:
                    failed += 1
                    logger.exception(
                        f"Row failed for symbol={instrument.symbol!r}: {row_err}"
                    )
               
        finally:
            logger.info("Cleaning up Playwright browser context for ingest_market.")
            with suppress(Exception):
                await page.close()
            with suppress(Exception): 
                await ctx.close()
            with suppress(Exception): 
                await browser.close()
        
    logger.info(
        f"ingest_market finished for mic={config.mic!r}: "
        f"processed={processed}, failed={failed}"
    )       
    if processed == 0 and failed > 10:
        logger.error(
            "Ingestion failed: no rows processed and more than 10 rows failed "
            "for ingest_market."
        )
        raise Exception("The update of the quotations failed.")
    return processed  


async def ingest_gpw_quotes_from_html(
    session: AsyncSession,
    storage: Storage,
    mic: str = "XWAR",  
) -> int:
    """
    Ingest GPW quotes from pre-parsed HTML listings for a given MIC.

    This function:
    - Resolves market ID for the MIC
    - Fetches symbol map from `GpwListingsClient`
    - Parses numeric values from PL-formatted strings
    - Upserts latest quotes and caches them in `storage`

    Args:
        session: Async SQLAlchemy session.
        storage: Storage backend (e.g. Redis wrapper) for caching quotes.
        mic: Market MIC, only 'XWAR' and 'XNCO' are supported.

    Returns:
        Number of successfully processed rows (quotes).

    Raises:
        ValueError: If market is missing or MIC is not supported.
        Exception: If nothing is processed and too many rows fail.
    """
    processed = 0
    failed = 0
    
    logger.info(f"Starting ingest_gpw_quotes_from_html for mic={mic!r}")
    
    market_uuid = await get_market_id_by_mic(session, mic)
    await session.rollback()
    if not market_uuid:
        logger.error(
            f"Market with MIC={mic!r} not found; "
            "make sure markets are seeded before ingestion."
        )
        raise ValueError(f"Market with MIC={mic} not found; seed markets first.")
    
    if mic not in ("XWAR", "XNCO"):
        logger.error(
            f"Unsupported MIC={mic!r} for ingest_gpw_quotes_from_html "
            "(only XWAR and XNCO are supported)."
        )
        raise ValueError("Service works only with with XWAR and XNCO mic.")

    client = GpwListingsClient()
    try:
        symbol_map: Dict[str, Dict[str, Any]] = await client.get_symbol_map(mic)
        logger.info(
            f"Fetched symbol map for mic={mic!r}: entries={len(symbol_map)}"
        )
    finally:
        await client.aclose()

    for symbol, rec in symbol_map.items():
        symbol = symbol.strip()
        if not symbol:
            continue

        try:
            last_price = rec.get("Last / Closing")
            if not isinstance(last_price, float):
                last_price = parse_float_pl(last_price)
            if last_price is None:
                logger.debug(
                    f"Skipping symbol={symbol!r}: missing or invalid last price."
                )
                continue

            change_pct_raw = str(rec.get("% change", "")).replace("%", "").strip()
            change_pct = parse_float_pl(change_pct_raw)
            if change_pct is None:
                logger.debug(
                    f"Skipping symbol={symbol!r}: missing or invalid change_pct."
                )
                continue

            volume = parse_int_pl(rec.get("Cumulated volume"))
            last_trade_at = parse_last_trade_at(rec.get("Last transaction time", ""))

            qin = QuoteLatesInput(
                last_price=last_price,
                change_pct=change_pct,
                volume=volume,
                last_trade_at=last_trade_at,
            )

            async with session.begin():
                inst = await get_by_symbol_in_market(
                    session,
                    market_id=market_uuid,
                    symbol=symbol,
                )
                if not inst:
                    logger.warning(
                        f"Instrument {symbol} not found in market {mic}; skipping quote."
                    )
                    failed += 1
                    continue

                latest = await upsert_quote_latest(session, inst.id, qin)

            await storage.stock.hset(
                key=f"latest_quote:{mic}",
                field=inst.symbol,
                value={
                    "name": inst.shortname,
                    "last_price": str(latest.last_price),
                    "change_pct": str(latest.change_pct),
                    "volume": latest.volume,
                    "last_trade_at": latest.last_trade_at.isoformat(),
                },
                ttl=3600,
            )

            processed += 1

        except Exception as e:
            failed += 1
            logger.exception(f"Row failed for {symbol}: {e}")

    logger.info(
        f"ingest_gpw_quotes_from_html finished for mic={mic!r}: "
        f"processed={processed}, failed={failed}"
    )
    if processed == 0 and failed > 10:
        logger.error(
            "Ingestion failed: no rows processed and more than 10 rows failed "
            "for ingest_gpw_quotes_from_html."
        )
        raise Exception("The update of the quotations failed (symbol_map).")
    return processed

     
        