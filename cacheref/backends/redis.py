"""Redis backend implementation for cacheref."""

from typing import Any, List, Optional, Set, Union

from .base import CacheBackend, logger

# Type aliases to help with type checking without importing Redis types
RedisClient = Any  # Any Redis-compatible client
RedisPipeline = Any  # Any Redis-compatible pipeline/transaction
RedisValue = Union[str, bytes, int, float, None]  # Values that can be stored in Redis


class RedisBackend(CacheBackend):
    """
    Redis-compatible backend using a Redis client.
    Works with any Redis-compatible client (Redis, ValKey, etc).

    This backend doesn't directly import Redis to avoid a hard dependency.
    It works with any object that provides Redis-compatible methods.
    """

    def __init__(self, client: RedisClient):
        """
        Initialize with a Redis client.

        Args:
            client: Any Redis-compatible client instance
                   Must implement: get, set, setex, delete, keys, sadd, smembers, expire
        """
        self.client = client
        logger.debug("Initialized RedisBackend with %s", client)

    def get(self, key: str) -> RedisValue:
        """Get a value from Redis."""
        logger.debug("Redis GET %s", key)
        return self.client.get(key)

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiration."""
        logger.debug("Redis SET %s", key)
        if expire:
            return self.client.setex(key, expire, value)
        return self.client.set(key, value)

    def setex(self, key: str, expiration_seconds: int, value: str) -> bool:
        """Set a value with expiration time."""
        logger.debug("Redis SETEX %s", key)
        return self.client.setex(key, expiration_seconds, value)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        logger.debug("Redis DELETE %s", keys)
        if not keys:
            return 0
        return self.client.delete(*keys)

    def keys(self, pattern: str) -> List[str]:
        """Find keys matching pattern."""
        logger.debug("Redis KEYS %s", pattern)
        return self.client.keys(pattern)

    def sadd(self, key: str, *values: str) -> int:
        """Add values to a set."""
        logger.debug("Redis SADD %s %s", key, values)
        return self.client.sadd(key, *values)

    def smembers(self, key: str) -> Set[str]:
        """Get all members of a set."""
        logger.debug("Redis SMEMBERS %s", key)
        return self.client.smembers(key)

    def expire(self, key: str, expiration_seconds: int) -> bool:
        """Set expiration on a key."""
        logger.debug("Redis EXPIRE %s %s", key, expiration_seconds)
        return self.client.expire(key, expiration_seconds)

    def pipeline(self) -> RedisPipeline:
        """
        Get a pipeline/transaction object from the Redis client.

        Returns:
            A Redis pipeline or transaction object that implements the same
            methods as the Redis client and has an execute() method.
        """
        # Handle different client implementations
        if hasattr(self.client, 'pipeline'):
            logger.debug("Creating Redis pipeline")
            return self.client.pipeline()
        elif hasattr(self.client, 'multi'):
            logger.debug("Creating Redis multi transaction")
            return self.client.multi()
        else:
            # Fallback: simple wrapper that just executes commands immediately
            logger.warning("Redis client doesn't support pipeline, using fake pipeline")
            class FakePipeline:
                def __init__(self, redis: RedisClient):
                    self.redis = redis
                    self.commands = []

                def __getattr__(self, name: str):
                    def method(*args: Any, **kwargs: Any) -> 'FakePipeline':
                        self.commands.append((name, args, kwargs))
                        return self
                    return method

                def execute(self) -> List[Any]:
                    results = []
                    for cmd, args, kwargs in self.commands:
                        method = getattr(self.redis, cmd)
                        results.append(method(*args, **kwargs))
                    self.commands = []
                    return results

            return FakePipeline(self.client)
