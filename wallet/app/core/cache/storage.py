from redis.asyncio.client import Redis
from typing import Optional, Literal, Callable, Any
import json
import pickle
import logging

logger = logging.getLogger(__name__)


class RedisStorage:
    """
    A Redis-based key-value storage with support for pickle and JSON serialization.
    """

    def __init__(self, redis: Redis,
                 key_prefix: str = ':1:session:', 
                 serializer: Literal["pickle", "json"] = "pickle",) -> None:  
        """
        Initialize RedisStorage with a Redis client and serialization strategy.

        Args:
            redis (Redis): An instance of the Redis client (asyncio version).
            key_prefix (str): Prefix to apply to all stored keys.
            serializer (Literal["pickle", "json"]): Serialization method. Defaults to 'pickle'.

        Raises:
            ValueError: If an unsupported serializer is provided.
        """

        self.redis_client = redis
        self.key_prefix = key_prefix
        
        if serializer == "pickle":
            self._serialize: Callable[[Any], bytes] = pickle.dumps
            self._deserialize: Callable[[bytes], Any] = pickle.loads
        elif serializer == "json":
            self._serialize = lambda v: json.dumps(v).encode("utf-8")
            self._deserialize = lambda b: json.loads(b.decode("utf-8"))
        else:
            raise ValueError("Unsupported serializer. Choose 'pickle' or 'json'.")
        
        logger.debug(f"RedisStorage initialized with prefix '{key_prefix}' and serializer '{serializer}'.")

    def _make_key(self, key: str) -> str:
        """Return the full Redis key including the prefix."""
        return f"{self.key_prefix}{key}"
        
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve and deserialize the value associated with a Redis key.

        Args:
            key (str): The original (unprefixed) key.

        Returns:
            Optional[Any]: The deserialized value, or None if not found or on error.
        """
        redis_key = self._make_key(key)
        try:
            data = await self.redis_client.get(redis_key)
            if data is None:
                logger.debug("Key not found in Redis.")
                return None
            return self._deserialize(data)
        except Exception as e:
            logger.error(f"Error getting key {redis_key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, timeout: int = 3600) -> bool:
        """
        Serialize and store a value in Redis with an optional expiration.

        Args:
            key (str): The original (unprefixed) key.
            value (Any): The value to store.
            timeout (int): Expiration time in seconds. Default is 3600 (1 hour).

        Returns:
            bool: True if successful, False otherwise.
        """
        redis_key = self._make_key(key)
        try:
            data = self._serialize(value)
            if timeout:
                await self.redis_client.setex(redis_key, timeout, data)
            else:
                await self.redis_client.set(redis_key, data)
            logger.debug(f"Stored key with timeout {timeout}s.")
            return True
        except Exception as e:
            logger.error(f"Error setting key {redis_key}: {e}")
            return False
            
    async def clear(self, key: str) -> bool:
        """
        Remove a key from Redis.

        Args:
            key (str): The original (unprefixed) key.

        Returns:
            bool: True if the key was deleted, False if it did not exist or on error.
        """
        redis_key = self._make_key(key)
        try:
            result = await self.redis_client.delete(redis_key)
            if result:
                logger.debug("Deleted key .")
            else:
                logger.debug("Key did not exist.")
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting key : {e}")
            return False
            
    async def exists(self, key: str) -> bool:
        """
        Check if a Redis key exists.

        Args:
            key (str): The original (unprefixed) key.

        Returns:
            bool: True if the key exists, False otherwise.
        """
        redis_key = self._make_key(key)
        try:
            exists = await self.redis_client.exists(redis_key)
            logger.debug(f"Key existence: {bool(exists)}")
            return bool(exists)
        except Exception as e:
            logger.error(f"Error checking existence of session : {e}")
            return False
