"""Base cache backend interface for cacheref."""

import logging
from typing import Any, List, Optional, Set, Union

# Setup logger
logger = logging.getLogger("cacheref")

# Type aliases for cache values
CacheValue = Union[str, bytes, int, float, None]


class CacheBackend:
    """
    Base class for cache backends.
    All backends must implement these methods to be compatible with EntityCache.
    """

    def get(self, key: str) -> CacheValue:
        """
        Get a value from the cache.

        Args:
            key: The key to retrieve

        Returns:
            The cached value or None if not found
        """
        raise NotImplementedError("Backend must implement get()")

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """
        Set a value in the cache with optional expiration.

        Args:
            key: The key to set
            value: The value to store
            expire: Optional expiration time in seconds

        Returns:
            True if successful
        """
        raise NotImplementedError("Backend must implement set()")

    def setex(self, key: str, expiration_seconds: int, value: str) -> bool:
        """
        Set a value with expiration time.

        Args:
            key: The key to set
            expiration_seconds: Expiration time in seconds
            value: The value to store

        Returns:
            True if successful
        """
        raise NotImplementedError("Backend must implement setex()")

    def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Args:
            *keys: The keys to delete

        Returns:
            Number of keys deleted
        """
        raise NotImplementedError("Backend must implement delete()")

    def ttl(self, key: str) -> int:
        """
        Get the time-to-live for a key.

        Args:
            key: The key to check

        Returns:
            Time-to-live in seconds or -2 if key does not exist
        """
        raise NotImplementedError("Backend must implement ttl()")

    def keys(self, pattern: str) -> List[str]:
        """
        Find keys matching pattern.

        Args:
            pattern: Pattern to match (glob-style)

        Returns:
            List of matching keys
        """
        raise NotImplementedError("Backend must implement keys()")

    def sadd(self, key: str, *values: str) -> int:
        """
        Add values to a set.

        Args:
            key: The set key
            *values: Values to add to the set

        Returns:
            Number of values added
        """
        raise NotImplementedError("Backend must implement sadd()")

    def smembers(self, key: str) -> Set[str]:
        """
        Get all members of a set.

        Args:
            key: The set key

        Returns:
            Set of all members
        """
        raise NotImplementedError("Backend must implement smembers()")

    def expire(self, key: str, expiration_seconds: int) -> bool:
        """
        Set expiration on a key.

        Args:
            key: The key to set expiration on
            expiration_seconds: Expiration time in seconds

        Returns:
            True if successful
        """
        raise NotImplementedError("Backend must implement expire()")

    def pipeline(self) -> Any:
        """
        Get a pipeline/transaction object.

        Returns:
            A pipeline object that implements the same methods as the backend
        """
        return self  # Default implementation just returns self

    def execute(self) -> List[Any]:
        """
        Execute commands in a pipeline.

        Returns:
            Results of executed commands
        """
        return []  # Default implementation does nothing
