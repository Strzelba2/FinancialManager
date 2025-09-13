from nicegui.storage import Storage
import logging
from .session_persistent import SessionPersistent

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
        self._session = SessionPersistent(url=Storage.redis_url)
        logger.debug("SessionStorage initialized with Redis session handler.")

    @property
    def session(self):
        """
        Access the Redis session handler.

        Returns:
            SessionPersistent: The session handler instance.
        """
        return self._session
    
    async def on_shutdown(self) -> None:
        """
        Clean up resources on application shutdown.

        This method:
        - Calls the base class shutdown handler.
        - Closes the Redis session connection.
        """
        logger.debug("Shutting down SessionStorage...")
        await super().on_shutdown()
        await self._session.close()
        logger.debug("SessionStorage shutdown complete. Redis connection closed.")
