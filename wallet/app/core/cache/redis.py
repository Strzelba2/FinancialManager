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
        self._session: Optional[RedisStorage] = None
        self._user: Optional[RedisStorage] = None
        
        logger.debug("Storage instance created. Awaiting initialize().")
        
    async def initialize(self) -> None:
        """
        Initialize the Redis connection and data namespaces.

        Raises:
            Exception: If Redis connection or initialization fails.
        """
        try:
            self._client = redis.from_url(Storage.redis_url, decode_responses=False)
            self._session = RedisStorage(self._client)
            self._user = RedisStorage(self._client, key_prefix=':1:client:', serializer='json')
            logger.info("Redis connection established and storage initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    @property
    def session(self) -> RedisStorage:
        """
        Access the Redis-based session storage namespace.

        Returns:
            RedisStorage: The session storage handler.

        Raises:
            RuntimeError: If called before `initialize()`.
        """
        if not self._session:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._session
    
    @property
    def user(self) -> RedisStorage:
        """
        Access the Redis-based user/client storage namespace.

        Returns:
            RedisStorage: The user/client storage handler.

        Raises:
            RuntimeError: If called before `initialize()`.
        """
        if not self._user:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        return self._user

    async def shutdown(self) -> None:
        """
        Gracefully close Redis connections.
        """
        if self._client:
            await self._client.close()
            await self._client.connection_pool.disconnect()
            logger.info("Redis connection closed.")
