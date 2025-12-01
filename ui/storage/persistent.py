import pickle
import logging
from typing import Optional, Literal, Callable, Any, Dict
import json
from redis.asyncio.client import Redis

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
        
    async def hset(self, key: str, field: str, value: Any, *, ttl: Optional[int] = None) -> None:
        """
        Store a single field in a HASH; optionally set a TTL on the whole hash key.

        Args:
            key: The original (unprefixed) hash key.
            field: Hash field name.
            value: Value to store (will be serialized).
            ttl: Optional TTL (in seconds) for the entire hash key.
        """
        k = self._make_key(key)
        await self.redis_client.hset(k, field, self._serialize(value))
        if ttl is not None:
            await self.redis_client.expire(k, ttl)

    async def hmset(self, key: str, mapping: Dict[str, Any], *, ttl: Optional[int] = None) -> None:
        """
        Store many fields at once into a HASH; mapping values are serialized.

        Args:
            key: The original (unprefixed) hash key.
            mapping: Dictionary of field -> value pairs to store.
            ttl: Optional TTL (in seconds) for the entire hash key.
        """
        k = self._make_key(key)
        ser_map = {f: self._serialize(v) for f, v in mapping.items()}
        if ser_map:
            await self.redis_client.hset(k, mapping=ser_map)
        if ttl is not None:
            await self.redis_client.expire(k, ttl)

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """
        Retrieve and deserialize a single field from a HASH.

        Args:
            key: The original (unprefixed) hash key.
            field: Hash field name.

        Returns:
            The deserialized value for the field, or None if not found.
        """
        k = self._make_key(key)
        val = await self.redis_client.hget(k, field)
        return None if val is None else self._deserialize(val)

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """
        Retrieve all fields from a HASH and deserialize values.

        Args:
            key: The original (unprefixed) hash key.

        Returns:
            A dictionary mapping field names (str) to deserialized values.
        """
        k = self._make_key(key)
        raw = await self.redis_client.hgetall(k)  
        out: Dict[str, Any] = {}
        for fb, vb in raw.items():
            f = fb.decode("utf-8") if isinstance(fb, (bytes, bytearray)) else str(fb)
            out[f] = self._deserialize(vb)
        return out
    
    async def scan(self, pattern: str, count: int = 200) -> list[str]:
        """
        Scan for keys matching a pattern and return *unprefixed* keys.

        Internally this uses Redis SCAN with the configured key prefix:

        - The `pattern` is first converted to a full Redis pattern via `_make_key`.
        - SCAN is called repeatedly until the cursor returns to 0.
        - Returned keys are stripped of `self.key_prefix` before being added to the result.

        Args:
            pattern: Pattern to match (without prefix); e.g. "user:*".
            count: Hint for the number of keys Redis should return per SCAN iteration.

        Returns:
            List of key names without the configured prefix.
        """
        full_pattern = self._make_key(pattern)
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self.redis_client.scan(cursor=cursor, match=full_pattern, count=count)
            for k in batch:
                k_str = k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
                if k_str.startswith(self.key_prefix):
                    k_str = k_str[len(self.key_prefix):]
                keys.append(k_str)
            if cursor == 0:
                break
        return keys

    async def ttl(self, key: str) -> int:
        """
        Get time-to-live (TTL) in seconds for a given key.

        Semantics (Redis):
            - > 0 : number of seconds to expire.
            - -1  : key exists but has no associated expire.
            - -2  : key does not exist.

        Args:
            key: Logical (unprefixed) key.

        Returns:
            TTL in seconds as an integer.
        """
        return int(await self.redis_client.ttl(self._make_key(key)))

    async def hkeys(self, key: str) -> list[str]:
        """
        Return a list of field names for a HASH key (unserialized).

        Args:
            key: Logical (unprefixed) key of the Redis HASH.

        Returns:
            List of field names (decoded to str).
        """
        raw = await self.redis_client.hkeys(self._make_key(key))
        return [f.decode("utf-8") if isinstance(f, (bytes, bytearray)) else str(f) for f in raw]

    async def hlen(self, key: str) -> int:
        """
        Get the number of fields in a HASH.

        Args:
            key: Logical (unprefixed) key of the Redis HASH.

        Returns:
            Number of fields in the hash (0 if the key does not exist).
        """
        return int(await self.redis_client.hlen(self._make_key(key)))

    async def hexists(self, key: str, field: str) -> bool:
        """
        Check whether a given field exists in a HASH.

        Args:
            key: Logical (unprefixed) key of the Redis HASH.
            field: Field name to check.

        Returns:
            True if the field exists, False otherwise.
        """
        return bool(await self.redis_client.hexists(self._make_key(key), field))
