"""Memory backend implementation for cacheref."""

import fnmatch
import threading
import time
from typing import Any, Dict, List, Optional, Set, Union

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

    def __init__(self, key_prefix: Optional[str] = None):
        """
        Initialize an in-memory cache backend.
        
        Args:
            key_prefix: Optional prefix to add to all keys (useful for namespacing)
        """
        self.data: Dict[str, Any] = {}  # Main data store
        self.sets: Dict[str, Set[str]] = {}  # For set operations
        self.expires: Dict[str, float] = {}  # Expiration times
        self.lock = threading.RLock()  # For thread safety
        self.key_prefix = key_prefix or ""
        logger.debug("Initialized MemoryBackend")

    def _prefix_key(self, key: str) -> str:
        """Add prefix to key if configured."""
        if not self.key_prefix:
            return key
        return f"{self.key_prefix}{key}"
        
    def _strip_prefix(self, key: str) -> str:
        """Remove prefix from key if present."""
        if not self.key_prefix:
            return key
        if key.startswith(self.key_prefix):
            return key[len(self.key_prefix):]
        return key

    def _check_expiry(self, key: str) -> bool:
        """
        Check if key is expired and delete if so.

        IMPORTANT: This method assumes the lock is already held!

        Args:
            key: The key to check (with prefix already applied)

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
        prefixed_key = self._prefix_key(key)
        with self.lock:
            # Check expiry first (while holding the lock)
            self._check_expiry(prefixed_key)
            # Then return the value (or None if it doesn't exist)
            return self.data.get(prefixed_key)

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set a value in the in-memory cache with optional expiration."""
        logger.debug("Memory SET %s", key)
        prefixed_key = self._prefix_key(key)
        with self.lock:
            self.data[prefixed_key] = value
            if expire:
                self.expires[prefixed_key] = time.time() + expire
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
                prefixed_key = self._prefix_key(key)
                if prefixed_key in self.data:
                    del self.data[prefixed_key]
                    count += 1
                if prefixed_key in self.sets:
                    del self.sets[prefixed_key]
                if prefixed_key in self.expires:
                    del self.expires[prefixed_key]
        return count

    def keys(self, pattern: str) -> List[str]:
        """Find keys matching pattern using fnmatch."""
        logger.debug("Memory KEYS %s", pattern)
        
        # Apply key prefix to the pattern
        prefixed_pattern = self._prefix_key(pattern)
        
        with self.lock:
            # Check expiry for all keys first
            # Make a copy of keys since we might modify during iteration
            for key in list(self.data.keys()):
                self._check_expiry(key)

            # Return matching keys
            result = []
            for key in self.data:
                if fnmatch.fnmatch(key, prefixed_pattern):
                    # Return keys without the prefix
                    if self.key_prefix:
                        stripped_key = self._strip_prefix(key)
                        result.append(stripped_key)
                    else:
                        result.append(key)
            return result

    def sadd(self, key: str, *values: str) -> int:
        """Add values to a set."""
        logger.debug("Memory SADD %s %s", key, values)
        prefixed_key = self._prefix_key(key)
        with self.lock:
            # Check if key is expired and create a new set if it is or doesn't exist
            self._check_expiry(prefixed_key)

            if prefixed_key not in self.sets:
                self.sets[prefixed_key] = set()

            count = 0
            for val in values:
                if val not in self.sets[prefixed_key]:
                    self.sets[prefixed_key].add(val)
                    count += 1
            return count

    def smembers(self, key: str) -> Set[str]:
        """Get all members of a set."""
        logger.debug("Memory SMEMBERS %s", key)
        prefixed_key = self._prefix_key(key)
        with self.lock:
            # Check expiry first
            self._check_expiry(prefixed_key)
            # Return the set or empty set if it doesn't exist
            return self.sets.get(prefixed_key, set())

    def expire(self, key: str, expiration_seconds: int) -> bool:
        """Set expiration on a key."""
        logger.debug("Memory EXPIRE %s %s", key, expiration_seconds)
        prefixed_key = self._prefix_key(key)
        with self.lock:
            if prefixed_key in self.data or prefixed_key in self.sets:
                self.expires[prefixed_key] = time.time() + expiration_seconds
                return True
        return False
        
    def pipeline(self):
        """Get a pipeline for batched operations."""
        logger.debug("Creating Memory pipeline")
        return MemoryPipeline(self)


class MemoryPipeline:
    """Simple pipeline implementation for batched operations with the MemoryBackend."""
    
    def __init__(self, backend: MemoryBackend):
        """
        Initialize with a reference to the backend.
        
        Args:
            backend: The MemoryBackend instance
        """
        self.backend = backend
        self.commands = []
        
    def __getattr__(self, name: str):
        """Proxy attribute access to the backend."""
        # Get the method from the backend
        if not hasattr(self.backend, name):
            raise AttributeError(f"'{type(self.backend).__name__}' object has no attribute '{name}'")
            
        backend_method = getattr(self.backend, name)
        
        # Create a method that stores commands
        def method(*args: Any, **kwargs: Any) -> 'MemoryPipeline':
            self.commands.append((backend_method, args, kwargs))
            return self
            
        return method
        
    def execute(self) -> List[Any]:
        """Execute all queued commands."""
        results = []
        # Use a single lock acquisition for the entire batch
        with self.backend.lock:
            for method, args, kwargs in self.commands:
                # Call the actual backend method directly
                # We're bypassing the public method that would acquire the lock again
                results.append(method(*args, **kwargs))
                
        self.commands = []  # Clear commands after execution
        return results
