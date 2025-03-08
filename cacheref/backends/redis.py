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

    def __init__(self, client: RedisClient, key_prefix: Optional[str] = None):
        """
        Initialize with a Redis client.

        Args:
            client: Any Redis-compatible client instance
                   Must implement: get, set, setex, delete, keys, sadd, smembers, expire
            key_prefix: Optional prefix to add to all keys (useful for namespacing)
        """
        self.client = client
        self.key_prefix = key_prefix or ""

        # Cache client capabilities for better performance
        self._has_pipeline = hasattr(self.client, 'pipeline')
        self._has_multi = hasattr(self.client, 'multi')

        logger.debug("Initialized RedisBackend with %s", client)

    def _prefix_key(self, key: str) -> str:
        """Add prefix to key if configured."""
        if not self.key_prefix:
            return key
        return f"{self.key_prefix}{key}"

    def get(self, key: str) -> RedisValue:
        """Get a value from Redis."""
        logger.debug("Redis GET %s", key)
        return self.client.get(self._prefix_key(key))

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiration."""
        logger.debug("Redis SET %s", key)
        prefixed_key = self._prefix_key(key)
        if expire:
            return self.client.setex(prefixed_key, expire, value)
        return self.client.set(prefixed_key, value)

    def setex(self, key: str, expiration_seconds: int, value: str) -> bool:
        """Set a value with expiration time."""
        logger.debug("Redis SETEX %s", key)
        return self.client.setex(self._prefix_key(key), expiration_seconds, value)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        if not keys:
            return 0

        logger.debug("Redis DELETE %s", keys)

        # Apply key prefix to all keys
        prefixed_keys = [self._prefix_key(key) for key in keys]
        return self.client.delete(*prefixed_keys)

    def keys(self, pattern: str) -> List[str]:
        """Find keys matching pattern."""
        logger.debug("Redis KEYS %s", pattern)

        # Apply key prefix to pattern
        prefixed_pattern = self._prefix_key(pattern)

        # Get keys and strip prefix if needed
        keys = self.client.keys(prefixed_pattern)

        # Remove prefix if it was added
        if self.key_prefix and keys:
            # Convert bytes to strings if needed
            if keys and isinstance(keys[0], bytes):
                keys = [k.decode('utf-8') for k in keys]

            # Strip prefix
            prefix_len = len(self.key_prefix)
            keys = [k[prefix_len:] if k.startswith(self.key_prefix) else k for k in keys]

        return keys

    def sadd(self, key: str, *values: str) -> int:
        """Add values to a set."""
        logger.debug("Redis SADD %s %s", key, values)
        return self.client.sadd(self._prefix_key(key), *values)

    def ttl(self, key: str) -> int:
        """Get the time-to-live for a key."""
        logger.debug("Redis TTL %s", key)
        return self.client.ttl(self._prefix_key(key))

    def smembers(self, key: str) -> Set[str]:
        """Get all members of a set."""
        logger.debug("Redis SMEMBERS %s", key)

        # Get members with prefixed key
        members = self.client.smembers(self._prefix_key(key))

        # If prefix was applied to key, and members might also contain
        # prefixed values (like cache keys that also need prefix handling),
        # we would handle that here. For now, return as-is since members
        # are typically not prefixed.
        return members

    def expire(self, key: str, expiration_seconds: int) -> bool:
        """Set expiration on a key."""
        logger.debug("Redis EXPIRE %s %s", key, expiration_seconds)
        return self.client.expire(self._prefix_key(key), expiration_seconds)

    def pipeline(self) -> RedisPipeline:
        """
        Get a pipeline/transaction object from the Redis client.

        Returns:
            A Redis pipeline or transaction object that implements the same
            methods as the Redis client and has an execute() method.
        """
        # Handle different client implementations
        if self._has_pipeline:
            logger.debug("Creating Redis pipeline")
            pipeline = self.client.pipeline()
            return RedisPrefixPipeline(pipeline, self.key_prefix)
        elif self._has_multi:
            logger.debug("Creating Redis multi transaction")
            multi = self.client.multi()
            return RedisPrefixPipeline(multi, self.key_prefix)
        else:
            logger.error("Redis client doesn't support pipeline, cnanot use batch operations")


class RedisPrefixPipeline:
    """Wrapper for Redis pipeline that applies key prefix automatically."""

    def __init__(self, pipeline: RedisPipeline, key_prefix: str = ""):
        """
        Initialize a prefix-aware Redis pipeline.

        Args:
            pipeline: Redis pipeline or transaction object
            key_prefix: Prefix to add to all keys
        """
        self.pipeline = pipeline
        self.key_prefix = key_prefix or ""

    def _prefix_key(self, key: str) -> str:
        """Add prefix to key if configured."""
        if not self.key_prefix:
            return key
        return f"{self.key_prefix}{key}"

    def __getattr__(self, name: str):
        """
        Proxy attribute access to the underlying pipeline.
        For operations taking a key as first argument, prefix the key.
        """
        # Get the original method
        orig_method = getattr(self.pipeline, name)

        # For methods that take a key as first arg, apply the prefix
        def wrapped_method(*args, **kwargs):
            if args and isinstance(args[0], str):
                # The first arg is the key, prefix it
                args = list(args)
                args[0] = self._prefix_key(args[0])
                args = tuple(args)
            return orig_method(*args, **kwargs)

        return wrapped_method

    def execute(self):
        """Execute the pipeline commands."""
        return self.pipeline.execute()
