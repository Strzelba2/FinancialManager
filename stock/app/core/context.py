from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncIterator, Tuple
from contextlib import suppress
import time
import logging

from app.db.session import db   
from app.core.cache.redis import Storage 

logger = logging.getLogger(__name__)


@asynccontextmanager
async def market_lock(storage: Storage, market_id: str, ttl_sec: int = 13 * 60):
    """
    Distributed lock for market ingestion, backed by Storage (e.g. Redis).

    The lock is implemented using a simple SET NX + EX key.

    Usage:
        async with market_lock(storage, market_id) as acquired:
            if not acquired:
                # another worker is already ingesting this market
                return
            # do ingest work

    Args:
        storage: Storage instance providing access to the underlying key-value client.
        market_id: Logical market identifier (used in the lock key).
        ttl_sec: Lock TTL in seconds; after this time the lock expires automatically.

    Yields:
        bool: True if the lock was acquired, False otherwise.
    """
    key = f"lock:ingest:{market_id}"
    await storage._client.delete(key)
    logger.info(
        f"Trying to acquire market_lock for market_id={market_id!r}, ttl_sec={ttl_sec}"
    )
    ok = await storage._client.set(key, str(time.time()), nx=True, ex=ttl_sec)
    
    if not ok:
        logger.warning(
            f"market_lock not acquired for market_id={market_id!r} "
            "(lock already held)"
        )
        yield False
        return
    try:
        yield True
    finally:
        logger.info(f"Releasing market_lock for market_id={market_id!r}")
        with suppress(Exception):
            await storage._client.delete(key)
            logger.debug(
                f"Lock key deleted for market_id={market_id!r}"
            )


@asynccontextmanager
async def app_context() -> AsyncIterator[Tuple["AsyncSession", Storage]]:
    """
    Shared application context yielding a database session and storage instance.

    This is intended for use **outside** FastAPI (e.g. in Celery tasks,
    CLI scripts, or one-off ingestion jobs) where dependency injection is
    not available.

    It:
    - Initializes `Storage`
    - Initializes the database
    - Obtains an `AsyncSession` from the session generator
    - Ensures both session and storage are cleaned up on exit

    Yields:
        Tuple[AsyncSession, Storage]: `(session, storage)` pair ready for use.
    """
    logger.info("Creating app_context (session + storage)")
    
    storage = Storage()
    logger.debug("Storage instance created, initializing...")
    await storage.initialize()
    logger.info("Storage initialized")

    logger.debug("Initializing database (db.init_db)")
    await db.init_db() 
    logger.info("Database initialization completed")

    agen = db.get_session()
    session = await agen.__anext__() 
    logger.info("AsyncSession acquired from session generator")

    try:
        yield session, storage
    finally:
        logger.info("Cleaning up app_context (closing session + storage)")
        try:
            await agen.aclose()
            logger.info("DB session generator closed")
        except Exception:
            logger.exception("Error closing DB session generator")
        try:
            await storage.shutdown()
            logger.info("Storage shutdown completed")
        except Exception:
            logger.exception("Error shutting down storage")