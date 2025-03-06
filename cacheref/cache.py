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
from typing import Any, Callable, Dict, Literal, Optional, Tuple

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
        ttl: int = 3600,
        serializer: Optional[Callable] = None,
        deserializer: Optional[Callable] = None,
        debug: bool = False,
    ):
        """
        Initialize the cache decorator.

        Args:
            backend: CacheBackend instance (if not provided, will use in-memory backend with default prefix)
            ttl: Default Time-to-live in seconds (default: 1 hour)
            serializer: Function to serialize data (default: msgspec.msgpack.encode if available, or json.dumps)
            deserializer: Function to deserialize data (default: msgspec.msgpack.decode if available, or json.loads)
            debug: Enable debug logging
        """
        # Set up logger
        if debug:
            logger.setLevel(logging.DEBUG)
            # Add a handler if none exists
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)

        # If backend is not provided, create memory backend with default prefix
        if backend is None:
            logger.info("No backend provided, using in-memory backend")
            backend = MemoryBackend(key_prefix="cache:")
            
        self.backend = backend
        self.ttl = ttl

        # Set serializer/deserializer with msgspec.msgpack as default if available
        if serializer is None:
            if HAS_MSGSPEC:
                # logger.debug("Using msgspec.msgpack.encode as default serializer")
                self.serializer = msgspec.msgpack.encode
            else:
                self.serializer = json.dumps
                logger.debug("msgspec not available, using json.dumps as fallback serializer")
        else:
            self.serializer = serializer

        if deserializer is None:
            if HAS_MSGSPEC:
                self.deserializer = msgspec.msgpack.decode
                # logger.debug("Using msgspec.msgpack.decode as default deserializer")
            else:
                self.deserializer = json.loads
                logger.debug("msgspec not available, using json.loads as fallback deserializer")
        else:
            self.deserializer = deserializer

        logger.debug("EntityCache initialized with %s backend", backend.__class__.__name__)

    def __call__(
        self,
        entity: Optional[str] = None,
        cache_key: Optional[str] = None,
        normalize_args: bool = False,
        ttl: Optional[int] = None,
        id_field: str = 'id',
        scope: Literal['function', 'entity'] = 'function',
    ):
        """
        Main decorator that caches function results.

        Args:
            entity: The primary entity type this function deals with
                  (e.g., 'user', 'product')
            cache_key: Optional custom key name for the cache to unify caching
                      across services or functions
            normalize_args: Whether to normalize argument values for consistent
                           cache keys across services
            ttl: Optional override for TTL (defaults to instance TTL)
            id_field: Name of the field containing entity IDs (default: 'id')
            scope: Determines the scope of cache sharing, with two possible values:
                  - 'function' (default): Function first caching with no cache sharing between same entity signatures
                  - 'entity': Entity first caching - different functions with same entity and arguments share cache

        Returns:
            Decorated function
        """
        effective_ttl = ttl if ttl is not None else self.ttl

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Get normalized parameters for the key
                processed_args, processed_kwargs = self._normalize_params(
                    func, args, kwargs, normalize=normalize_args
                )

                # Construct the appropriate cache key using the function object directly
                effective_func_key = self.construct_key(
                    func=func,
                    cache_key=cache_key,
                    entity=entity, 
                    scope=scope,
                    args=processed_args, 
                    kwargs=processed_kwargs
                )
                # Try to get the cached result
                try:
                    cached = self.backend.get(effective_func_key)
                    if cached:
                        logger.debug("[HIT]  %s %s %s", func.__name__, processed_args, processed_kwargs)
                        try:
                            return self.deserializer(cached)
                        except Exception as e:
                            logger.warning("Failed to deserialize cached data: %s", e)
                    else:
                        logger.debug("Cache miss for function: %s %s", func.__name__, effective_func_key)
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
                            effective_func_key,
                            effective_ttl,
                            serialized_result
                        )

                        # Register this key with entity index if an entity type is specified
                        if entity and result:
                            # Get any entity IDs from the results
                            entity_ids = self._extract_entity_ids(result, id_field)

                            if entity_ids:
                                logger.debug("[Reverse index] Found entity IDs: %s", entity_ids)
                                for entity_id in entity_ids:
                                    # Create a direct index from entity to cache keys
                                    # Format: entity:type:id for consistent, clear naming
                                    entity_key = f"entity:{entity}:{entity_id}"
                                    pipeline.sadd(entity_key, effective_func_key)

                                    # Set TTL on the entity index slightly longer than the cache TTL
                                    # This helps prevent orphaned indices
                                    pipeline.expire(entity_key, effective_ttl + 300)  # 5 minutes longer

                        pipeline.execute()
                        logger.debug("[Reverse index] recached successfully")
                    except Exception as e:
                        logger.warning("Cache backend operations failed: %s", e)
                except Exception as e:
                    # Log error but don't fail the function if caching fails
                    logger.error("Caching error: %s", e)

                return result
            # Store all key construction parameters on the wrapper
            # This ensures consistency between decorator usage and direct key construction
            wrapper.cache_key = cache_key
            wrapper.entity = entity
            wrapper.scope = scope
            wrapper.normalize_args = normalize_args
            wrapper.id_field = id_field
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

    def construct_key(self, func, cache_key: Optional[str] = None, entity: Optional[str] = None, 
                    scope: str = 'function', args: Tuple = (), kwargs: Dict = {}) -> str:
        """
        Construct a cache key based on function, entity, scope, and arguments.
        
        Priority for parameters (highest to lowest):
        1. Function attributes from wrapper (func.cache_key, func.entity, func.scope)
        2. Explicitly passed parameters (cache_key, entity, scope)
        3. Defaults (function name with module, no entity, 'function' scope)
        
        Args:
            func: The function object
            cache_key: Optional custom cache key
            entity: Optional entity type
            scope: Scope of caching ('function' or 'entity')
            args: Function positional arguments
            kwargs: Function keyword arguments
            
        Returns:
            A unique and consistent cache key string
        """
        # Check for wrapper attributes first with highest priority
        effective_cache_key = getattr(func, 'cache_key', None) or cache_key
        effective_entity = getattr(func, 'entity', None) or entity
        effective_scope = getattr(func, 'scope', None) or scope
        
        # Determine the prefix based on scope and entity
        if effective_cache_key:
            # If cache_key is provided or set on wrapper, use it
            prefix = effective_cache_key
        elif effective_scope == 'entity' and effective_entity:
            # If using entity scope, use entity type as prefix
            prefix = f"entity:{effective_entity}"
        else:
            # Default to function name with module
            prefix = f"{func.__module__}.{func.__name__}"
        
        # Generate the key with the determined prefix
        return self._generate_key(prefix, args, kwargs)
    
    def _generate_key(self, prefix: str, args: Tuple, kwargs: Dict) -> str:
        """
        Generate a unique cache key.
        
        Args:
            prefix: String to use as the key prefix (function name or entity type)
            args: Function positional arguments
            kwargs: Function keyword arguments
            
        Returns:
            A unique cache key string with consistent format
        """
        # Create a hash of the arguments
        args_str = str(args) if args else ""
        kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
        params_str = f"{args_str}{kwargs_str}"
        
        # Create a hash for the parameters
        if params_str:
            params_hash = hashlib.md5(params_str.encode()).hexdigest()
        else:
            params_hash = "noargs"
        
        # Format: cache:prefix:params_hash
        # Consistent format makes debugging easier
        key = f"cache:{prefix}:{params_hash}"
        
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

    def invalidate_entity(self, entity: str, entity_id: Any):
        """
        Invalidate all cached entries containing this entity.

        Args:
            entity: Type of entity (e.g., 'user')
            entity_id: ID of the entity

        Returns:
            Number of keys invalidated
        """
        # Get the key for this entity
        entity_key = f"entity:{entity}:{entity_id}"
        logger.debug("Invalidating entity %s:%s", entity, entity_id)

        try:
            # Get all cache keys directly for this entity
            cache_keys = self.backend.smembers(entity_key)

            if not cache_keys:
                logger.debug("No cache keys found for entity %s:%s", entity, entity_id)
                return 0

            # Convert from bytes if needed
            cache_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in cache_keys]
            logger.debug("Found %d cache keys to invalidate", len(cache_keys))
            # cache:tests.test_redis_integration.get_user_isolated:c0a8a20f903a4915b94db8de3ea63195
            # Delete all these specific cache keys and the entity index
            try:
                pipeline = self._pipeline()
                
                if cache_keys:
                    # This is not consistent, for each run not deletes all!
                    # pipeline.delete(*cache_keys)
                    for key in cache_keys:
                        pipeline.delete(key)
                    # pipeline.delete(cache_keys[1])
                # Delete the entity key itself
                pipeline.delete(entity_key)

                result = pipeline.execute()
                logger.info("Invalidated %d cache entries for %s:%s", len(cache_keys), entity, entity_id)
                logger.debug("Keys invalidated: %s result: %s", cache_keys, result)
                for key in self.backend.keys(f"*"):
                    try:
                        print(key , '-> ',self.backend.smembers(key), '\n')
                    except:
                        print(key , '-> ', msgspec.msgpack.decode(self.backend.get(key)), '\n')
                    print('-------------------')
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
            func_name: Fully qualified name of the function (module.function) or cache_key.
                      For example: "myapp.utils.get_user" not just "get_user".
                      You can use `f"{func.__module__}.{func.__name__}"` to get this.

        Returns:
            Number of keys invalidated
        """
        logger.debug("Invalidating all cache entries for function: %s", func_name)
        try:
            # Find all cache keys for this function name pattern
            pattern = f"cache:{func_name}:*"
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

    def invalidate_key(self, func_name_or_obj, *args, **kwargs):
        """
        Invalidate a specific cache key.

        Args:
            func_name_or_obj: Either a fully qualified function name (str) or a function object.
                      If string, it should be in format "myapp.utils.get_user" not just "get_user".
            *args, **kwargs: Arguments that were passed to the function

        Returns:
            Whether a key was invalidated
        """
        try:
            # Get the appropriate key to invalidate (reusing get_cache_key for consistency)
            key = self.get_cache_key(func_name_or_obj, *args, **kwargs)
            
            # Get an appropriate name for logging
            if callable(func_name_or_obj):
                func_name = f"{func_name_or_obj.__module__}.{func_name_or_obj.__name__}"
            else:
                func_name = func_name_or_obj

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
        logger.debug("Invalidating all cached entries")
        try:
            # Get all cache entries (c: for function caches, e: for entity indices)
            keys = self.backend.keys("*")

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
        # Get the appropriate function name based on cache_key attribute or module+name
        if getattr(func, 'cache_key', None):
            func_name = func.cache_key
        else:
            func_name = f"{func.__module__}.{func.__name__}"
        
        return self.invalidate_function(func_name)

    def invalidate_func_call(self, func, *args, **kwargs):
        """
        Invalidate a specific cache key by passing the function object directly.

        This is a convenience method that directly uses the function object.

        Args:
            func: The function object whose cache entry should be invalidated
            *args, **kwargs: Arguments that were passed to the function

        Returns:
            Whether a key was invalidated
        """
        # Use the function object directly with the new invalidate_key method
        return self.invalidate_key(func, *args, **kwargs)
        
    def get_cache_key(self, func_or_name, *args, **kwargs):
        """
        Get the cache key for a function call without invalidating it.
        
        This is useful for testing and debugging to see what key will be used.
        
        Args:
            func_or_name: Either a function object or a string with the fully qualified name.
            *args, **kwargs: Arguments that were passed to the function
            
        Returns:
            The cache key that would be used for this function and arguments
        """
        if callable(func_or_name):
            # We have a function object - use construct_key for full consistency
            # This will check for wrapper attributes automatically
            return self.construct_key(
                func=func_or_name, 
                args=args, 
                kwargs=kwargs
            )
        else:
            # We have a function name string
            return self._generate_key(func_or_name, args, kwargs)
