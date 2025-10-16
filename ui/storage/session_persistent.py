from nicegui import optional_features
import pickle
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


try:
    import redis.asyncio as redis
    optional_features.register('redis')
except ImportError:
    pass


class SessionPersistent:
    """
    Manages session storage in Redis using pickle serialization.
    """

    def __init__(self, *, url: str, key_prefix: str = ':1:session:') -> None: 
        """
        Initialize Redis client with session key prefix.

        Args:
            url (str): Redis connection URL.
            key_prefix (str): Prefix for session keys in Redis. Default is ':1:session:'.

        Raises:
            ImportError: If Redis support is not available in the environment.
        """
        if not optional_features.has('redis'):
            raise ImportError('Redis is not installed. Please run "pip install nicegui[redis]".')
        self.url = url
        self.redis_client = redis.from_url(
            url,
            decode_responses=False
        )
        self.key_prefix = key_prefix
        
        logger.debug("Initialized SessionPersistent with Redis URL and key prefix.",
                     extra={"key_prefix": key_prefix})
        
    async def get(self, session_key: str) -> Optional[Any]:
        """
        Retrieve and deserialize session data from Redis.

        Args:
            session_key (str): The session key to fetch.

        Returns:
            The deserialized session object if found, otherwise None.
        """
        key = f"{self.key_prefix}{session_key}"
        try:
            data = await self.redis_client.get(key)
            if data:
                return pickle.loads(data)
            logger.debug("No session found for key ")
        except Exception as e:
            logger.error(f"Error retrieving session for key {e}")
        return None
    
    async def set(self, session_key: str, value: Any, timeout: int = 3600) -> bool:
        """
        Serialize and store session data in Redis with a timeout.

        Args:
            session_key (str): The session key to store.
            value (Any): The session data to serialize and store.
            timeout (int): Expiration time in seconds (default is 3600s).

        Returns:
            bool: True if successfully stored, False on error.
        """
        key = f"{self.key_prefix}{session_key}"
        try:
            pickled = pickle.dumps(value)
            await self.redis_client.setex(key, timeout, pickled)
        except Exception as e:
            logger.error(f"Error setting session: {e}")
            
    async def delete(self, session_key: str) -> bool:
        """
        Delete a session key from Redis.

        Args:
            session_key (str): The session key to delete.

        Returns:
            bool: True if a key was removed, False otherwise.
        """
        key = f"{self.key_prefix}{session_key}"
        try:
            removed = await self.redis_client.delete(key)  
            if removed:
                logger.debug("Deleted session for key %s", key)
            else:
                logger.debug("No session to delete for key %s", key)
            return bool(removed)
        except Exception as e:
            logger.error("Error deleting session key %s: %s", key, e)
            return False
            
    async def exists(self, session_key: str) -> bool:
        """
        Check if a session key exists in Redis.

        Args:
            session_key (str): The session key to check.

        Returns:
            bool: True if the key exists, False otherwise.
        """
        key = f"{self.key_prefix}{session_key}"
        try:
            exists = await self.redis_client.exists(key)
            logger.debug("Session stored for key")
            return bool(exists)
        except Exception as e:
            logger.error(f"Error checking existence of session key : {e}")
            return False

    async def close(self) -> None:
        """Close Redis connection and subscription."""
        await self.redis_client.close()
