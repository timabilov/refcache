"""
Main cache implementation for cacheref.

This module contains the EntityCache decorator that tracks entity references
for precise cache invalidation.
"""

import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple

try:
    import msgspec.msgpack
    HAS_MSGSPEC = True
except ImportError:
    HAS_MSGSPEC = False

from .backends.base import CacheBackend
from .backends.memory import MemoryBackend

# Setup logger
logger = logging.getLogger("cacheref")


class EntityCache:
    """
    A caching decorator that tracks which entities appear in function results,
    allowing for precise cache invalidation when entities change.

    Works with any backend that implements the CacheBackend interface.
    """

    def __init__(
        self,
        backend: Optional[CacheBackend] = None,
        prefix: str = "cache:",
        ttl: int = 3600,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        debug: bool = False,
    ):
        """
        Initialize the cache decorator.

        Args:
            backend: CacheBackend instance (if not provided, will use in-memory backend)
            prefix: Prefix for all cache keys
            ttl: Default Time-to-live in seconds (default: 1 hour)
            serializer: Function to serialize data (default: msgspec.msgpack.encode if available, or json.dumps)
            deserializer: Function to deserialize data (default: msgspec.msgpack.decode if available, or json.loads)
            debug: Enable debug logging
        """
        if backend is None:
            logger.info("No backend provided, using in-memory backend")
            backend = MemoryBackend()

        # Set up logger
        if debug:
            logger.setLevel(logging.DEBUG)
            # Add a handler if none exists
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)

        self.backend = backend
        self.prefix = prefix
        self.ttl = ttl

        # Set serializer/deserializer with msgspec.msgpack as default if available
        if serializer is None:
            if HAS_MSGSPEC:
                self.serializer = msgspec.msgpack.encode
                logger.debug("Using msgspec.msgpack.encode as default serializer")
            else:
                self.serializer = json.dumps
                logger.debug("msgspec not available, using json.dumps as fallback serializer")
        else:
            self.serializer = serializer

        if deserializer is None:
            if HAS_MSGSPEC:
                self.deserializer = msgspec.msgpack.decode
                logger.debug("Using msgspec.msgpack.decode as default deserializer")
            else:
                self.deserializer = json.loads
                logger.debug("msgspec not available, using json.loads as fallback deserializer")
        else:
            self.deserializer = deserializer

        logger.debug("EntityCache initialized with %s backend", backend.__class__.__name__)

    def __call__(
        self,
        entity_type: Optional[str] = None,
        key_prefix: Optional[str] = None,
        normalize_args: bool = False,
        ttl: Optional[int] = None,
        id_field: str = 'id',
    ):
        """
        Main decorator that caches function results.

        Args:
            entity_type: The primary entity type this function deals with
                        (e.g., 'user', 'product')
            key_prefix: Optional custom prefix for the cache key to unify caching
                       across services or functions
            normalize_args: Whether to normalize argument values for consistent
                           cache keys across services
            ttl: Optional override for TTL (defaults to instance TTL)
            id_field: Name of the field containing entity IDs (default: 'id')

        Returns:
            Decorated function
        """
        effective_ttl = ttl if ttl is not None else self.ttl

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Use custom key prefix if provided, otherwise use function name
                func_key_name = key_prefix or func.__module__ + "." + func.__name__

                # Get normalized parameters for the key
                processed_args, processed_kwargs = self._normalize_params(
                    func, args, kwargs, normalize=normalize_args
                )

                # Generate function-specific key
                func_key = self._generate_key(func_key_name, processed_args, processed_kwargs)

                # Try to get the cached result
                try:
                    cached = self.backend.get(func_key)
                    if cached:
                        logger.debug("[HIT]  %s %s %s", func.__name__, processed_args, processed_kwargs)
                        try:
                            return self.deserializer(cached)
                        except Exception as e:
                            logger.warning("Failed to deserialize cached data: %s", e)
                    else:
                        logger.debug("Cache miss for function: %s %s", func.__name__, func_key)
                except Exception as e:
                    logger.warning("Cache get operation failed: %s", e)

                # Call the function
                result = func(*args, **kwargs)

                try:
                    # Cache the result
                    logger.debug("Caching result for function: %s", func.__name__)
                    try:
                        serialized_result = self.serializer(result)
                    except Exception as e:
                        logger.warning("Failed to serialize result: %s", e)
                        return result

                    try:
                        pipeline = self.backend.pipeline()
                        pipeline.setex(
                            func_key,
                            effective_ttl,
                            serialized_result
                        )

                        # Register this key with entity index if an entity type is specified
                        if entity_type and result:
                            # Get any entity IDs from the results
                            entity_ids = self._extract_entity_ids(result, id_field)

                            if entity_ids:
                                logger.debug("Found entity IDs: %s", entity_ids)
                                for entity_id in entity_ids:
                                    # Create a direct index from entity to cache keys
                                    entity_key = f"{self.prefix}e:{entity_type}:{entity_id}"
                                    pipeline.sadd(entity_key, func_key)

                                    # Set TTL on the entity index slightly longer than the cache TTL
                                    # This helps prevent orphaned indices
                                    pipeline.expire(entity_key, effective_ttl + 300)  # 5 minutes longer

                        pipeline.execute()
                        logger.debug("Reverse index recached successfully")
                    except Exception as e:
                        logger.warning("Cache backend operations failed: %s", e)
                except Exception as e:
                    # Log error but don't fail the function if caching fails
                    logger.error("Caching error: %s", e)

                return result

            return wrapper
        return decorator

    def _pipeline(self):
        """Get a pipeline/transaction object from the backend."""
        logger.debug("Getting pipeline from backend")
        return self.backend.pipeline()

    def _normalize_params(self, func, args, kwargs, normalize=False):
        """
        Normalize parameters to ensure consistent cache keys across services.

        If normalize=True, it:
        - Converts positional args to named kwargs when possible
        - Sorts lists/sets in parameters
        - Sorts dict keys

        This helps unify cache entries across different services.
        """
        if not normalize:
            return args, kwargs

        # Copy kwargs to avoid modifying the original
        processed_kwargs = kwargs.copy()

        # Convert positional args to kwargs where possible for consistency
        try:
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())

            # Only convert args that have parameter names
            for i, arg in enumerate(args):
                if i < len(param_names):
                    param_name = param_names[i]
                    # Skip 'self' or 'cls' in method calls
                    if param_name not in ('self', 'cls'):
                        processed_kwargs[param_name] = arg

            # No positional args in the processed version (all converted to kwargs)
            processed_args = ()
        except Exception:
            # Fall back to original args if signature inspection fails
            processed_args = args

        # Normalize argument values to ensure cache key consistency
        normalized_kwargs = {}
        for key, value in processed_kwargs.items():
            normalized_kwargs[key] = self._normalize_value(value)

        return processed_args, normalized_kwargs

    def _normalize_value(self, value):
        """
        Normalize a value for consistent hashing.
        - Sorts lists and sets
        - Sorts dictionary keys
        - Converts tuples to lists (for sorting)
        """
        if isinstance(value, list):
            try:
                return sorted(value)
            except TypeError:  # If items aren't comparable
                return value
        elif isinstance(value, tuple):
            try:
                return sorted(list(value))
            except TypeError:  # If items aren't comparable
                return value
        elif isinstance(value, set):
            try:
                return sorted(list(value))
            except TypeError:  # If items aren't comparable
                return list(value)
        elif isinstance(value, dict):
            return {k: self._normalize_value(v) for k, v in sorted(value.items())}
        else:
            return value

    def _generate_key(self, func_name: str, args: Tuple, kwargs: Dict) -> str:
        """Generate a unique cache key."""
        # Start with function name
        key = f"{self.prefix}c:{func_name}:"

        # Add a hash of the arguments
        args_str = str(args) if args else ""
        kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
        params_str = f"{args_str}{kwargs_str}"

        if params_str:
            # Create a hash for the parameters
            params_hash = hashlib.md5(params_str.encode()).hexdigest()
            key += params_hash
        else:
            key += "noargs"

        return key

    def _extract_entity_ids(self, result, id_field='id'):
        """
        Extract entity IDs from the result in various formats.

        Args:
            result: The data to extract IDs from
            id_field: The field name containing the ID (default: 'id')
        """
        ids = set()

        try:
            # Handle single object
            if isinstance(result, dict) and id_field in result:
                ids.add(result[id_field])

            # Handle list of objects
            elif isinstance(result, (list, tuple)):
                for item in result:
                    if isinstance(item, dict) and id_field in item:
                        ids.add(item[id_field])

            # Handle simple ID value
            elif isinstance(result, (int, str)):
                ids.add(result)
        except Exception:
            # If any error occurs during extraction, just continue
            pass

        return ids

    def invalidate_entity(self, entity_type: str, entity_id: Any):
        """
        Invalidate all cached entries containing this entity.

        Args:
            entity_type: Type of entity (e.g., 'user')
            entity_id: ID of the entity

        Returns:
            Number of keys invalidated
        """
        # Get the key for this entity
        entity_key = f"{self.prefix}e:{entity_type}:{entity_id}"
        logger.debug("Invalidating entity %s:%s", entity_type, entity_id)

        try:
            # Get all cache keys directly for this entity
            cache_keys = self.backend.smembers(entity_key)

            if not cache_keys:
                logger.debug("No cache keys found for entity %s:%s", entity_type, entity_id)
                return 0

            # Convert from bytes if needed
            cache_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in cache_keys]
            logger.debug("Found %d cache keys to invalidate", len(cache_keys))

            # Delete all these specific cache keys and the entity index
            try:
                pipeline = self._pipeline()

                if cache_keys:
                    pipeline.delete(*cache_keys)

                # Delete the entity key itself
                pipeline.delete(entity_key)

                pipeline.execute()
                logger.info("Invalidated %d cache entries for %s:%s", len(cache_keys), entity_type, entity_id)
                return len(cache_keys)
            except Exception as e:
                logger.error("Error in pipeline execution: %s", e)
                return 0

        except Exception as e:
            logger.error("Error invalidating entity: %s", e)
            return 0

    def invalidate_function(self, func_name: str):
        """
        Invalidate all cache entries for a specific function.

        Args:
            func_name: Fully qualified name of the function (module.function) or key_prefix.
                      For example: "myapp.utils.get_user" not just "get_user".
                      You can use `f"{func.__module__}.{func.__name__}"` to get this.

        Returns:
            Number of keys invalidated
        """
        logger.debug("Invalidating all cache entries for function: %s", func_name)
        try:
            # Find all cache keys for this function name pattern
            pattern = f"{self.prefix}c:{func_name}:*"
            func_keys = self.backend.keys(pattern)

            if not func_keys:
                logger.debug("No cache keys found for function: %s", func_name)
                return 0

            # Convert from bytes if needed
            func_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in func_keys]
            logger.debug("Found %d cache keys to invalidate", len(func_keys))

            # Delete all those cache keys
            if func_keys:
                self.backend.delete(*func_keys)

            logger.info("Invalidated %d cache entries for function: %s", len(func_keys), func_name)
            return len(func_keys)  # Number of cache keys deleted

        except Exception as e:
            logger.error("Error invalidating function: %s", e)
            return 0

    def invalidate_key(self, func_name, *args, **kwargs):
        """
        Invalidate a specific cache key.

        Args:
            func_name: Fully qualified name of the function (module.function) or key_prefix.
                      For example: "myapp.utils.get_user" not just "get_user".
                      You can use `f"{func.__module__}.{func.__name__}"` to get this.
            *args, **kwargs: Arguments that were passed to the function

        Returns:
            Whether a key was invalidated
        """
        try:
            key = self._generate_key(func_name, args, kwargs)

            logger.debug("Invalidating specific cache key: %s %s ", f'{func_name}:({args}, {kwargs})', key)

            # Delete the specific cache key
            self.backend.delete(key)

            # Note: This doesn't remove the key from entity indices
            # Those will expire based on TTL or be overwritten on next cache
            logger.debug("Cache key invalidated: %s", key)

            return True

        except Exception as e:
            logger.error("Error invalidating key: %s", e)
            return False

    def invalidate_all(self):
        """
        Invalidate all cached entries.

        Returns:
            Number of keys invalidated
        """
        logger.debug("Invalidating all cache entries with prefix: %s", self.prefix)
        try:
            keys = self.backend.keys(f"{self.prefix}*")

            if not keys:
                logger.debug("No cache keys found to invalidate")
                return 0

            # Convert from bytes if needed
            keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
            logger.debug("Found %d cache keys to invalidate", len(keys))

            result = self.backend.delete(*keys)
            logger.info("Invalidated %d cache entries", result)
            return result

        except Exception as e:
            logger.error("Error invalidating all: %s", e)
            return 0

    def invalidate_func(self, func):
        """
        Invalidate all cache entries for a function by passing the function object directly.

        This is a convenience method that extracts the module and name automatically.

        Args:
            func: The function object whose cache entries should be invalidated

        Returns:
            Number of keys invalidated
        """
        func_name = f"{func.__module__}.{func.__name__}"
        return self.invalidate_function(func_name)

    def invalidate_func_call(self, func, *args, **kwargs):
        """
        Invalidate a specific cache key by passing the function object directly.

        This is a convenience method that extracts the module and name automatically.

        Args:
            func: The function object whose cache entry should be invalidated
            *args, **kwargs: Arguments that were passed to the function

        Returns:
            Whether a key was invalidated
        """
        func_name = f"{func.__module__}.{func.__name__}"
        return self.invalidate_key(func_name, *args, **kwargs)
