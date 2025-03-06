"""Memory backend implementation for cacheref."""

import fnmatch
import threading
import time
from typing import Any, Dict, List, Optional, Set

from .base import CacheBackend, CacheValue, logger


class MemoryBackend(CacheBackend):
    """
    In-memory backend implementation.
    Useful for testing or applications that don't need persistence.

    This backend stores all data in memory and is not persistent.
    It's thread-safe and supports all the same operations as the Redis backend.

    This implementation uses a single RLock to protect all operations.
    The lock ensures that compound operations are executed atomically.
    Keep in mind that this implementation is simple, you can override it to your needs.

    The _check_expiry method is an internal method that assumes the lock is already
    held by the caller. All public methods acquire the lock before performing
    any operations on the shared data structures.
    """

    def __init__(self):
        """Initialize an in-memory cache backend."""
        self.data: Dict[str, Any] = {}  # Main data store
        self.sets: Dict[str, Set[str]] = {}  # For set operations
        self.expires: Dict[str, float] = {}  # Expiration times
        self.lock = threading.RLock()  # For thread safety
        logger.debug("Initialized MemoryBackend")

    def _check_expiry(self, key: str) -> bool:
        """
        Check if key is expired and delete if so.

        IMPORTANT: This method assumes the lock is already held!

        Args:
            key: The key to check

        Returns:
            True if the key was expired and removed, False otherwise
        """
        if key in self.expires and self.expires[key] < time.time():
            logger.debug("Key %s expired, removing", key)
            if key in self.data:
                del self.data[key]
            if key in self.sets:
                del self.sets[key]
            del self.expires[key]
            return True
        return False

    def get(self, key: str) -> CacheValue:
        """Get a value from the in-memory cache."""
        logger.debug("Memory GET %s", key)
        with self.lock:
            # Check expiry first (while holding the lock)
            self._check_expiry(key)
            # Then return the value (or None if it doesn't exist)
            return self.data.get(key)

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set a value in the in-memory cache with optional expiration."""
        logger.debug("Memory SET %s", key)
        with self.lock:
            self.data[key] = value
            if expire:
                self.expires[key] = time.time() + expire
        return True

    def setex(self, key: str, expiration_seconds: int, value: str) -> bool:
        """Set a value with expiration time."""
        logger.debug("Memory SETEX %s", key)
        return self.set(key, value, expiration_seconds)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        logger.debug("Memory DELETE %s", keys)
        count = 0
        with self.lock:
            for key in keys:
                if key in self.data:
                    del self.data[key]
                    count += 1
                if key in self.sets:
                    del self.sets[key]
                if key in self.expires:
                    del self.expires[key]
        return count

    def keys(self, pattern: str) -> List[str]:
        """Find keys matching pattern using fnmatch."""
        logger.debug("Memory KEYS %s", pattern)
        with self.lock:
            # Check expiry for all keys first
            # Make a copy of keys since we might modify during iteration
            for key in list(self.data.keys()):
                self._check_expiry(key)

            # Return matching keys
            result = []
            for key in self.data:
                if fnmatch.fnmatch(key, pattern):
                    result.append(key)
            return result

    def sadd(self, key: str, *values: str) -> int:
        """Add values to a set."""
        logger.debug("Memory SADD %s %s", key, values)
        with self.lock:
            # Check if key is expired and create a new set if it is or doesn't exist
            self._check_expiry(key)

            if key not in self.sets:
                self.sets[key] = set()

            count = 0
            for val in values:
                if val not in self.sets[key]:
                    self.sets[key].add(val)
                    count += 1
            return count

    def smembers(self, key: str) -> Set[str]:
        """Get all members of a set."""
        logger.debug("Memory SMEMBERS %s", key)
        with self.lock:
            # Check expiry first
            self._check_expiry(key)
            # Return the set or empty set if it doesn't exist
            return self.sets.get(key, set())

    def expire(self, key: str, expiration_seconds: int) -> bool:
        """Set expiration on a key."""
        logger.debug("Memory EXPIRE %s %s", key, expiration_seconds)
        with self.lock:
            if key in self.data or key in self.sets:
                self.expires[key] = time.time() + expiration_seconds
                return True
        return False
