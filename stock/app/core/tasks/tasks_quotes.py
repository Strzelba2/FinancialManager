import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.context import app_context, market_lock
from app.markerdata.registry import get_provider
from app.api.services.stock import ingest_market, ingest_gpw_quotes_from_html


logger = logging.getLogger(__name__)


@celery_app.task(
    name="ingest_gpw_quarter",
    acks_late=True,                
    time_limit=60 * 10,           
    soft_time_limit=60 * 9,         
    autoretry_for=(Exception,),   
    retry_backoff=True,       
    retry_backoff_max=600,        
    retry_jitter=True,
    max_retries=3,
)
def ingest_gpw_quarter() -> int:
    """
    Celery task: ingest GPW and NewConnect quotes using the browser-based provider.

    This task:
    - Creates an application context (DB session + storage).
    - Resolves the "market" provider.
    - For each supported `market_key` ("pl-wse", "pl-newconnect"):
        * Acquires a distributed lock via `market_lock`.
        * Runs `ingest_market` to fetch and store quotes.
    - Sums up all processed rows and returns the total.

    Returns:
        Total number of processed quotes across all markets.
    """
    async def _run() -> int: 
        logger.info("ingest_gpw_quarter: started")
        provider = get_provider("market")
        async with app_context() as (session, storage):
            all_processed = 0

            for market_key in ("pl-wse", "pl-newconnect"):
                logger.info(
                    f"ingest_gpw_quarter: processing market_key={market_key!r}"
                )
                async with market_lock(storage, market_key) as acquired:
                    if not acquired:
                        logger.warning(
                            f"ingest_gpw_quarter: skipping market_key={market_key!r} "
                            "(lock already held by another worker)"
                        )
                        continue
                    processed = await ingest_market(session, provider, market_key, storage)
                    logger.info(
                        f"ingest_gpw_quarter: market_key={market_key!r} "
                        f"processed={processed}"
                    )
                    all_processed += processed

            logger.info(
                f"ingest_gpw_quarter: finished, total_processed={all_processed}"
            )
            return all_processed
    return asyncio.run(_run())


@celery_app.task(
    name="ingest_gpw_quarter_alt",
    acks_late=True,                
    time_limit=60 * 10,           
    soft_time_limit=60 * 9,         
    autoretry_for=(Exception,),   
    retry_backoff=True,       
    retry_backoff_max=600,        
    retry_jitter=True,
    max_retries=3,
)
def ingest_gpw_quarter_alt() -> int:
    """
    Celery task: ingest GPW/NC quotes from HTML symbol maps.

    This alternative pipeline:
    - Uses `ingest_gpw_quotes_from_html` instead of a browser provider.
    - Runs for each MIC in ("XWAR", "XNCO").
    - Acquires a distributed lock per MIC via `market_lock`.
    - Sums all processed rows and returns the total.

    Returns:
        Total number of processed quotes across all MICs.
    """
    async def _run() -> int: 
        logger.info("ingest_gpw_quarter_alt: started")
        async with app_context() as (session, storage):
            all_processed = 0
            for mic in ("XWAR", "XNCO"):
                logger.info(f"ingest_gpw_quarter_alt: processing mic={mic!r}")
                async with market_lock(storage, mic) as acquired:
                    if not acquired:
                        logger.warning(
                            f"ingest_gpw_quarter_alt: skip mic={mic!r}, "
                            "another run in progress."
                        )
                        continue
                    processed = await ingest_gpw_quotes_from_html(session, storage, mic)
                    logger.info(
                        f"ingest_gpw_quarter_alt: mic={mic!r} processed={processed}"
                    )
                    all_processed += processed

            logger.info(
                f"ingest_gpw_quarter_alt: finished, total_processed={all_processed}"
            )
            return all_processed
    return asyncio.run(_run())
