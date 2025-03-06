# CacheRef

A caching library that tracks entity references for precise cache invalidation.

## Overview

CacheRef is a Python caching decorator that tracks which entities appear in function results, allowing for precise cache invalidation when entities change.

## Features

- 🔑 **Smart Invalidation**: Automatically tracks which entities appear in cached results
- 🚀 **Flexible Backends**: Use Redis, in-memory, or custom backends
- 📋 **Custom ID Fields**: Support for entities with non-standard ID field names
- 🔒 **Custom Serialization**: Cache objects that aren't JSON-serializable
- 🔍 **Debugging**: Detailed logging for debugging cache operations
- 🔄 **Cross-Service Compatible**: Share cache between different services
- 🧠 **Argument Normalization**: Normalize function arguments for consistent cache keys
- 🛡️ **Error Resilient**: Won't break your app if caching fails

## Installation

```bash
pip install cacheref
```

## Quick Start

```python
from redis import Redis
from cacheref import EntityCache, RedisBackend

# Initialize with Redis backend
redis_client = Redis(host='localhost', port=6379)
redis_backend = RedisBackend(redis_client)
cache = EntityCache(backend=redis_backend, prefix="app:", ttl=3600)

# Or use in-memory backend (default if no backend provided)
memory_cache = EntityCache()

@cache(entity="user")
def get_user(user_id):
    # Your database query here
    return {"id": user_id, "name": f"User {user_id}"}

# Later, when a user is updated
def update_user(user_id, data):
    # Update in database...
    # Then invalidate all caches containing this user
    cache.invalidate_entity("user", user_id)
```

## Advanced Usage

See the examples.py file for detailed examples including:
- Custom backend usage
- Cross-service caching
- Custom ID fields
- Custom serialization
- In-memory caching
- And more!

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

Apache 2.0