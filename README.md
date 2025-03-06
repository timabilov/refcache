# CacheRef

A Python caching decorator that tracks which entities appear in function results, allowing for precise cache invalidation when entities change.

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

Basic installation (in-memory cache only):
```bash
pip install cacheref
```

With Redis support:
```bash
pip install cacheref[redis]
```

With all supported backends:
```bash
pip install cacheref[all]
```

## Quick Start

```python
from redis import Redis
from cacheref import EntityCache, RedisBackend

# Initialize with Redis backend and namespacing
redis_client = Redis(host='localhost', port=6379)
backend = RedisBackend(redis_client, key_prefix="app:")
cache = EntityCache(backend=backend, ttl=3600)

# Or use in-memory backend for testing (default if no backend is provided)
from cacheref import MemoryBackend
test_cache = EntityCache(backend=MemoryBackend(key_prefix="test:"))
memory_cache = EntityCache()  # Uses in-memory backend by default
```

## Usage Examples

### Basic Usage

#### With Entity Tracking

```python
@cache(entity_type="user")
def get_user(user_id):
    # Your database query here
    return {"id": user_id, "name": f"User {user_id}"}

# Get user (will be cached)
user = get_user(42)

# Update user and invalidate cache
def update_user(user_id, data):
    # Update in database...
    # Then invalidate all caches containing this user
    cache.invalidate_entity("user", user_id)
```

#### Plain Caching

You can also use refcache as a traditional function cache without entity tracking:

```python
# Simple function cache (no entity tracking)
@cache()
def calculate_value(x, y):
    # Expensive computation here
    return x * y * 100

# Invalidate by function name
cache.invalidate_func(calculate_value)

# Or with entity_type but disabled entity tracking
@cache(entity_type="product", func_key_only=True)
def get_product(product_id):
    # This has entity_type but won't be part of entity-based invalidation
    # Useful when you want consistent naming but don't need tracking
    return {"id": product_id, "name": f"Product {product_id}"}
```

### Custom ID Fields

```python
@cache(entity_type="customer", id_field="customer_id")
def get_customer(customer_id):
    # Your database query here
    return {"customer_id": customer_id, "name": f"Customer {customer_id}"}
```
## How It Works

When a function is decorated with `@cache(entity_type="user")`:

1. The decorator **caches the function result**
2. It **extracts entity IDs** from the result (e.g., `{"id": 42, ...}` or using a custom ID field)
3. It **creates an index** mapping each entity to cache keys containing it

When an entity changes:

1. You call `cache.invalidate_entity("user", 42)`
2. The library **finds all cache keys** containing this entity
3. Only those **specific caches are invalidated**


This means you don't need to remember all the different ways an entity might be cached - just invalidate by entity ID, and all relevant caches are automatically cleared.

## Advanced Usage

### Cross-Service Caching

By default, functions that access the same entity will share cache entries across different functions:

```python
# In service A
@cache(entity_type="user")
def get_user(user_id):
    return {"id": user_id, "name": "User from Service A"}

# In service B
@cache(entity_type="user")
def fetch_user(id):  # Different function name
    return {"id": id, "name": "User from Service B"}
```

Both services will share the same cache entries automatically when accessing the same entity ID. 

For more complex parameters or to disable this behavior, use `func_key_only=True`:

```python
# This function will use its own function-specific cache, not shared with others
@cache(entity_type="user", func_key_only=True)
def get_filtered_users(user_id, filters=None):
    # Complex filtering operation that shouldn't share cache with other functions
    return filtered_results
```

For backward compatibility, you can also use the explicit `cache_key` approach:

```python
# Using explicit cache key for complex cases
@cache(entity_type="user", cache_key="user.get_by_id", normalize_args=True)
def get_user_with_extra_data(user_id, include_details=False):
    return {"id": user_id, "name": "User with details", "details": {...} if include_details else None}
```
### Custom Entity Extraction

```python
class CustomCache(EntityCache):
    def _extract_entity_ids(self, result, id_field='id'):
        ids = super()._extract_entity_ids(result, id_field)
        
        # Extract product IDs from order items
        if isinstance(result, dict) and "items" in result:
            for item in result["items"]:
                if "product_id" in item:
                    ids.add(f"product:{item['product_id']}")
        
        return ids
```

### Custom Serialization

For caching objects that aren't JSON-serializable (like datetime, sets, or custom classes):

```python
# Define custom serializer and deserializer
import pickle
import base64

def pickle_serializer(obj):
    """Serialize using pickle and encode as base64 string."""
    return base64.b64encode(pickle.dumps(obj)).decode('ascii')

def pickle_deserializer(data):
    """Deserialize from base64-encoded pickle data."""
    if isinstance(data, bytes):
        data = data.decode('ascii')
    return pickle.loads(base64.b64decode(data.encode('ascii')))

# Create cache with custom serializers
cache = EntityCache(
    backend=redis_backend,
    serializer=pickle_serializer,
    deserializer=pickle_deserializer
)

# Now you can cache objects that aren't JSON-serializable
@cache(entity_type="event")
def get_event(event_id):
    return {
        "id": event_id,
        "start_time": datetime.now(),  # Not JSON serializable
        "attendees": set([1, 2, 3])    # Not JSON serializable
    }
```
## API Reference

### EntityCache

Main class for creating cache decorators.

```python
cache = EntityCache(
    backend=None,  # CacheBackend instance (optional, will use in-memory if None)
    ttl=3600,  # Default TTL in seconds (optional)
    serializer=json.dumps,  # Custom serializer function (optional)
    deserializer=json.loads,  # Custom deserializer function (optional)
    debug=False  # Enable debug logging (optional)
)
```

### @cache()

Decorator for caching function results.

```python
@cache(
    entity_type="user",  # Type of entity returned (optional)
    cache_key=None,  # Custom cache key for function (optional)
    normalize_args=False,  # Whether to normalize arguments (optional)
    ttl=None,  # Override default TTL (optional)
    id_field="id",  # Field name containing entity IDs (optional)
    func_key_only=False  # If True, disables cross-function sharing (optional)
)
def my_function():
    # ...
```
### Invalidation Methods

```python
# Invalidate all caches containing a specific entity
cache.invalidate_entity("user", 42)

# Invalidate all caches for a specific function
cache.invalidate_function("get_user")

# Invalidate a specific function call
cache.invalidate_key("get_user", 42)

# Invalidate all caches
cache.invalidate_all()
```
### Cache Backends

The library has a flexible backend system with no mandatory dependencies:

#### 1. Redis Backend (Optional)

Redis backend requires the redis package to be installed (`pip install cacheref[redis]`):

```python
from redis import Redis
from cacheref import EntityCache, RedisBackend

# Create a Redis backend with a namespace
redis_client = Redis(host='localhost', port=6379)
backend = RedisBackend(redis_client, key_prefix="app:")
cache = EntityCache(backend=backend)

# Works with any Redis-compatible client
from valkey import Client
valkey_client = Client(host='localhost', port=6379)
valkey_backend = RedisBackend(valkey_client, key_prefix="app:")
cache = EntityCache(backend=valkey_backend)
```

The RedisBackend works with any Redis-compatible client (redis-py, valkey, etc) that implements the basic Redis commands. It doesn't directly import Redis, so you can provide any client that follows the Redis interface.

The `key_prefix` parameter allows for more efficient namespacing directly at the backend level, which can improve performance when working with many keys.

#### 2. In-Memory Backend (great for testing or small applications)

```python
from cacheref import EntityCache, MemoryBackend

# With namespace
memory_backend = MemoryBackend(key_prefix="app:")
cache = EntityCache(backend=memory_backend)

# Or with default namespace
memory_backend = MemoryBackend(key_prefix="cache:")
cache = EntityCache(backend=memory_backend)
```

#### 3. Custom Backends

Create your own backend by implementing the CacheBackend interface:

```python
from cacheref import CacheBackend, EntityCache

class MyCustomBackend(CacheBackend):
    # Implement required methods
    def get(self, key): ...
    def set(self, key, value, expire=None): ...
    def setex(self, key, time, value): ...
    def delete(self, *keys): ...
    def keys(self, pattern): ...
    def sadd(self, key, *values): ...
    def smembers(self, key): ...
    def expire(self, key, time): ...
    
    # Optional methods
    def pipeline(self): ...
    def execute(self): ...

cache = EntityCache(backend=MyCustomBackend())
```

The backend must implement Redis-compatible commands:

- `get`, `set`, `setex`
- `sadd`, `smembers`
- `keys`, `delete`
- `expire`
- `pipeline` and `execute` (optional, for better performance)

### Logging and Debugging

The library includes built-in logging for debugging cache operations:

```python
import logging
from cacheref import EntityCache, MemoryBackend

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Enable debug mode for detailed cache operation logging
cache = EntityCache(
    backend=MemoryBackend(),
    debug=True  # Enables detailed logging
)

# Or configure the logger directly
logger = logging.getLogger("cacheref")
logger.setLevel(logging.DEBUG)
```

Log levels:
- **DEBUG**: Detailed operation logs (get, set, cache hits/misses)
- **INFO**: General cache operations (invalidations, initialization)
- **WARNING**: Non-critical issues (serialization failures, etc.)
- **ERROR**: Critical failures (backend unavailable, etc.)

## Performance Optimizations

CacheRef includes several performance optimizations:

### 1. Backend Namespacing

All backends support namespacing through the `key_prefix` parameter:

```python
# Redis backend with namespace
redis_backend = RedisBackend(redis_client, key_prefix="app:")

# Memory backend with namespace
memory_backend = MemoryBackend(key_prefix="testing:")  
```

Benefits of backend namespacing:
- Isolated key spaces for different applications
- Efficient batch operations
- Transparent key management
- Consistent interface across backends

Both Redis and Memory backends automatically handle prefixing and stripping of prefixes, making namespacing fully transparent to application code.

### 2. Additional Optimizations

- **Efficient Pipeline Usage**: Redis operations are automatically batched through pipelines
- **Lazy Logging**: Debug logging only occurs when debug mode is enabled
- **Automatic Type Conversion**: Redis backends handle byte/string conversions automatically
- **msgspec Integration**: Uses fast msgspec.msgpack serialization when available

## Development and Testing

### Docker Setup

The repository includes a Docker Compose configuration for easy development and testing with Redis:

```bash
# Start Redis and Redis Commander UI
docker-compose up -d

# Access Redis Commander UI at http://localhost:8081
# Username: admin
# Password: refcache123
```

### Running Tests

```bash
# Run tests with Redis using the convenience script
./run_tests.sh

# Run specific tests
./run_tests.sh tests/test_redis_backend.py

# Or run pytest directly (with Redis running)
pytest tests/test_redis_backend.py
```

## License

MIT
