from nicegui.storage import Storage
from typing import Optional
import redis.asyncio as redis
import logging
from .persistent import RedisStorage

logger = logging.getLogger(__name__)


class SessionStorage(Storage):
    """
    A storage backend that manages session persistence using Redis.

    Inherits from:
        Storage: Base class providing the Redis configuration.

    Attributes:
        _session (SessionPersistent): Redis-backed session handler.
    """
    def __init__(self):
        """
        Initialize the session storage with a Redis session handler.
        """
        super().__init__()
        self._client: Optional[redis.Redis] = None
        self._session: Optional[RedisStorage] = None
        self._stock: Optional[RedisStorage] = None
        logger.debug("SessionStorage initialized with Redis session handler.")
        
    async def initialize(self) -> None:
        """
        Initialize the Redis connection and data namespaces.

        Raises:
            Exception: If Redis connection or initialization fails.
        """
        try:
            self._client = redis.from_url(Storage.redis_url, decode_responses=False)
            self._session = RedisStorage(self._client)
            self._stock = RedisStorage(self._client, key_prefix=':1:stock:', serializer='json')
            logger.info("Redis connection established and storage initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    @property
    def session(self):
        """
        Access the Redis session handler.

        Returns:
            SessionPersistent: The session handler instance.
        """
        return self._session
    
    @property
    def stock(self) -> Optional[RedisStorage]:
        return self._stock
    
    async def on_shutdown(self) -> None:
        """
        Clean up resources on application shutdown.

        This method:
        - Calls the base class shutdown handler.
        - Closes the Redis session connection.
        """
        logger.debug("Shutting down SessionStorage...")
        try:
            await super().on_shutdown()
        finally:
            for store in (self._session, self._stock):
                if hasattr(store, "close"):
                    maybe_close = getattr(store, "close")
                    if callable(maybe_close):
                        res = maybe_close()
                        if hasattr(res, "__await__"):
                            await res  
                            
            if self._client is not None:
                if hasattr(self._client, "aclose"):
                    await self._client.aclose()
                elif hasattr(self._client, "close"):
                    self._client.close()
                self._client = None
            logger.debug("SessionStorage shutdown complete.")
