import redis.asyncio as redis
import logging
from typing import Optional

from .storage import RedisStorage
from app.core.config import settings

logger = logging.getLogger(__name__)


class Storage():
    """
    Base storage layer managing Redis connection and structured access
    to session and user-specific storage namespaces.
    """
    redis_url = settings.REDIS_URL
    
    def __init__(self):
        """
        Initialize the Storage class without connecting to Redis immediately.
        """
        if not Storage.redis_url:
            raise ValueError("REDIS_URL environment variable is not set.")
        
        self._client: Optional[redis.Redis] = None
        self._stock: Optional[RedisStorage] = None
        
        logger.debug("Storage instance created. Awaiting initialize().")
        
    async def initialize(self) -> None:
        """
        Initialize the Redis connection and data namespaces.

        Raises:
            Exception: If Redis connection or initialization fails.
        """
        try:
            self._client = redis.from_url(Storage.redis_url, decode_responses=False)
            self._stock = RedisStorage(self._client, key_prefix=':1:stock:', serializer='json')
            logger.info("Redis connection established and storage initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise
    
    @property
    def stock(self) -> RedisStorage:
        """
        Access the Redis-based stock/client storage namespace.

        Returns:
            RedisStorage: The stock/client storage handler.

        Raises:
            RuntimeError: If called before `initialize()`.
        """
        if not self._stock:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._stock

    async def shutdown(self) -> None:
        """
        Gracefully close Redis connections.
        """
        if self._client:
            await self._client.close()
            await self._client.connection_pool.disconnect()
            logger.info("Redis connection closed.")
