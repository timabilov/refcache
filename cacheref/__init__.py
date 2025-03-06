"""
CacheRef - A caching library that tracks entity references for precise invalidation.

This library provides a caching decorator that tracks which entities appear in
function results, enabling precise cache invalidation when entities change.
"""

__version__ = '0.1.0'

# Import main components
from .backends.base import CacheBackend
from .backends.memory import MemoryBackend
from .backends.redis import RedisBackend
from .cache import EntityCache

# Export public API
__all__ = [
    'EntityCache',
    'CacheBackend',
    'MemoryBackend',
    'RedisBackend',
]
