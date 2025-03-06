
# Example 1: Basic usage with Redis using backend-level namespacing
from redis import Redis

from cacheref import EntityCache, RedisBackend

# Initialize Redis client and backend with namespace
redis_client = Redis(host='localhost', port=6379, db=0)
# Namespace is configured at the backend level
redis_backend = RedisBackend(redis_client, key_prefix="app:")

# Create cache with the Redis backend
cache = EntityCache(backend=redis_backend, ttl=3600)

@cache(entity_type="user")
def get_user(user_id):
    """Get a single user by ID."""
    # Your actual database query here
    return {"id": user_id, "name": f"User {user_id}", "active": True}


# Example 2: Using with ValKey
from valkey import Client

from cacheref import EntityCache, RedisBackend

# Initialize ValKey client and backend
valkey_client = Client(host='localhost', port=6379)
# Create backend with namespace
valkey_backend = RedisBackend(valkey_client, key_prefix="app:")

# Create cache with the ValKey backend
cache = EntityCache(backend=valkey_backend, ttl=3600)

@cache(entity_type="product")
def get_product(product_id):
    """Get a product by ID."""
    return {"id": product_id, "name": f"Product {product_id}", "price": 19.99}


# Example 3: Cross-service cache sharing
# In service A:
# from common.cache import cache  # Shared cache instance
# (Imaginary shared import - just for example purposes)

# Simulating a shared cache instance with namespace isolation
from cacheref import EntityCache, RedisBackend

redis_client = Redis(host='localhost', port=6379, db=0)
# Create isolated namespace for services
redis_backend = RedisBackend(redis_client, key_prefix="services:")
cache = EntityCache(backend=redis_backend)

# No need for explicit cache_key - entity-based caching is now automatic
@cache(
    entity_type="user",
    normalize_args=True
)
def get_user_details(user_id):
    """Get user details in service A."""
    return {"id": user_id, "name": "User Name", "email": "user@example.com"}

# In service B:
# from common.cache import cache  # Same shared cache instance

# This will automatically share cache with get_user_details when accessing same user_id
@cache(
    entity_type="user",
    normalize_args=True
)
def fetch_user(id):  # Different parameter name
    """Get user in service B."""
    return {"id": id, "name": "User Name", "email": "user@example.com"}

# For functions where sharing is not desired, use func_key_only=True
@cache(
    entity_type="user",
    func_key_only=True,  # Prevents sharing with other functions
    normalize_args=True
)
def get_user_with_filtering(user_id, include_details=False):
    """Get user with additional filtering - not suitable for sharing."""
    result = {"id": user_id, "name": "User Name"}
    if include_details:
        result["details"] = {"email": "user@example.com", "address": "123 Main St"}
    return result


# Example 4: Complex filtering with multiple entities
@cache(entity_type="user")
def find_users_by_filters(status=None, region=None, tags=None):
    """Find users matching various filters."""
    # Your database query here
    users = [
        {"id": 1, "name": "User 1", "status": "active", "region": "west"},
        {"id": 2, "name": "User 2", "status": "inactive", "region": "east"},
        {"id": 3, "name": "User 3", "status": "active", "region": "west"}
    ]

    # Apply filters
    if status:
        users = [u for u in users if u["status"] == status]
    if region:
        users = [u for u in users if u["region"] == region]
    if tags:
        # Assume users have tags field
        users = [u for u in users if any(tag in u.get("tags", []) for tag in tags)]

    return users


# Example 5: Invalidating cache entries
def update_user(user_id, data):
    """Update a user and invalidate related caches."""
    # Update user in database
    # ...

    # Invalidate all caches containing this user
    cache.invalidate_entity("user", user_id)

    # You can also invalidate a specific function using the convenience method
    # This is better than using the name directly as it handles module paths
    cache.invalidate_func(get_user)

    # Or invalidate a specific function call
    cache.invalidate_func_call(get_user, user_id)

    return {"status": "success", "id": user_id}


# Example 6: Working with multiple entities
@cache(entity_type="order")
def get_order_with_items(order_id):
    """Get an order with all its items."""
    # This would be a database query joining orders and items
    order = {
        "id": order_id,
        "date": "2023-04-15",
        "items": [
            {"id": 101, "product_id": 42, "quantity": 2},
            {"id": 102, "product_id": 57, "quantity": 1}
        ]
    }

    return order

# Note: With the current implementation, only the order ID would be tracked
# To track item IDs as well, you would need to extend _extract_entity_ids


# Example 7: Custom entity extraction
from cacheref import EntityCache


class CustomCache(EntityCache):
    """Extended cache with custom entity extraction."""

    def _extract_entity_ids(self, result, id_field='id'):
        """Extract multiple types of entity IDs from the result."""
        ids = super()._extract_entity_ids(result, id_field)

        try:
            # Extract order item IDs
            if isinstance(result, dict) and "items" in result:
                for item in result["items"]:
                    if isinstance(item, dict) and "id" in item:
                        # Add with a prefix to distinguish from order IDs
                        ids.add(f"item:{item['id']}")

            # Extract product IDs from order items
            if isinstance(result, dict) and "items" in result:
                for item in result["items"]:
                    if isinstance(item, dict) and "product_id" in item:
                        # Add with a prefix
                        ids.add(f"product:{item['product_id']}")
        except Exception:
            pass

        return ids


# Example 8: Using custom ID fields
@cache(entity_type="customer", id_field="customer_id")
def get_customer(customer_id):
    """Get a customer using a non-standard ID field."""
    # Your actual database query here
    return {
        "customer_id": customer_id,
        "name": f"Customer {customer_id}",
        "tier": "premium"
    }

# Example of a database using UUID as _id
@cache(entity_type="document", id_field="_id")
def get_document(doc_id):
    """Get a document from a MongoDB-like database."""
    # Your actual database query here
    return {
        "_id": doc_id,
        "title": f"Document {doc_id}",
        "content": "Lorem ipsum dolor sit amet..."
    }


# Example 9: Using msgspec as the default serializer
from cacheref import EntityCache, MemoryBackend

# Create cache with default serializers (uses msgspec if available)
# Note: We use the backend's key_prefix parameter for namespacing
memory_backend = MemoryBackend(key_prefix="default:")
cache = EntityCache(
    backend=memory_backend,
    ttl=3600
)

@cache()
def get_data(data_id):
    """Get data using default serialization."""
    return {
        "id": data_id,
        "items": [{"id": i, "value": f"Item {i}"} for i in range(10)]
    }

# Example 10: Custom serialization for non-JSON-serializable objects
import base64
import pickle
from datetime import datetime

from cacheref import EntityCache, RedisBackend


# Define custom serializer and deserializer for pickle
def pickle_serializer(obj):
    """Serialize using pickle and encode as base64 string."""
    return base64.b64encode(pickle.dumps(obj)).decode('ascii')

def pickle_deserializer(data):
    """Deserialize from base64-encoded pickle data."""
    if isinstance(data, bytes):
        data = data.decode('ascii')
    return pickle.loads(base64.b64decode(data.encode('ascii')))

# Create cache with custom serializers
redis_client = Redis(host='localhost', port=6379, db=0)
# Use the backend's key_prefix parameter for namespacing
redis_backend = RedisBackend(redis_client, key_prefix="pickle:")
pickle_cache = EntityCache(
    backend=redis_backend,
    serializer=pickle_serializer,
    deserializer=pickle_deserializer
)

@pickle_cache(entity_type="event")
def get_event(event_id):
    """Get an event with datetime objects."""
    # Your actual database query here
    return {
        "id": event_id,
        "name": f"Event {event_id}",
        "start_time": datetime.now(),  # Not JSON serializable
        "attendees": set([1, 2, 3])    # Not JSON serializable
    }


# Example 11: Performance comparison between serializers
import json
import time

try:
    import msgspec.msgpack
    HAS_MSGSPEC = True
except ImportError:
    HAS_MSGSPEC = False

def performance_benchmark():
    """Compare performance of different serializers."""
    backend = MemoryBackend()

    # Generate a large test dataset
    large_data = {
        "id": 42,
        "items": [{"id": i, "value": f"Item value {i}", "active": i % 2 == 0} for i in range(1000)],
        "metadata": {
            "created_at": "2023-05-15T12:00:00Z",
            "tags": ["benchmark", "performance", "cache", "serialization"],
            "settings": {k: f"value_{k}" for k in range(50)}
        }
    }

    # Create caches with different serializers
    # Create backends with appropriate key prefixes
    json_backend = MemoryBackend(key_prefix="json:")
    json_cache = EntityCache(
        backend=json_backend,
        serializer=json.dumps,
        deserializer=json.loads
    )

    # Skip msgspec testing if not available
    if HAS_MSGSPEC:
        msgpack_backend = MemoryBackend(key_prefix="msgpack:")
        msgpack_cache = EntityCache(
            backend=msgpack_backend,
            serializer=msgspec.msgpack.encode,
            deserializer=msgspec.msgpack.decode
        )

    # Test JSON
    json_start = time.time()
    for i in range(1000):
        serialized = json_cache.serializer(large_data)
        _ = json_cache.deserializer(serialized)  # Result not used, just testing performance
    json_time = time.time() - json_start

    results = {
        "json": {
            "time": json_time,
            "size": len(json_cache.serializer(large_data))
        }
    }

    # Test msgpack if available
    if HAS_MSGSPEC:
        msgpack_start = time.time()
        for i in range(1000):
            serialized = msgpack_cache.serializer(large_data)
            _ = msgpack_cache.deserializer(serialized)  # Result not used, just testing performance
        msgpack_time = time.time() - msgpack_start

        results["msgpack"] = {
            "time": msgpack_time,
            "size": len(msgpack_cache.serializer(large_data))
        }

    return results

# Run the benchmark when this file is executed directly
if __name__ == "__main__":
    results = performance_benchmark()

    print("Serialization Performance Benchmark:")
    print("------------------------------------")

    for name, data in results.items():
        print(f"{name.upper()}:")
        print(f"  Time for 1000 serializations: {data['time']:.4f} seconds")
        print(f"  Serialized data size: {data['size']} bytes")

    if "msgpack" in results and "json" in results:
        speedup = results["json"]["time"] / results["msgpack"]["time"]
        size_reduction = (1 - results["msgpack"]["size"] / results["json"]["size"]) * 100
        print("\nComparison:")
        print(f"  msgpack is {speedup:.2f}x faster than JSON")
        print(f"  msgpack data is {size_reduction:.2f}% smaller than JSON")


# Example 12: Using the in-memory backend with logging
import logging

from cacheref import EntityCache, MemoryBackend

# Configure logging for cache operations
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("cacheref")
logger.setLevel(logging.DEBUG)

# Create cache with in-memory backend
memory_backend = MemoryBackend(key_prefix="memory:")
memory_cache = EntityCache(
    backend=memory_backend,
    debug=True  # Enable debug logging
)

@memory_cache(entity_type="product")
def get_product_memory(product_id):
    """Get a product using memory cache."""
    # Your actual database query here
    return {
        "id": product_id,
        "name": f"Product {product_id}",
        "price": 19.99
    }

# Example usage
product = get_product_memory(42)  # First call will cache
product_again = get_product_memory(42)  # Second call will use cache

# Invalidate the cache
memory_cache.invalidate_entity("product", 42)
