"""Integration tests for Redis backend with EntityCache."""

import pytest
import redis
from cacheref import EntityCache, RedisBackend
import msgspec.msgpack


@pytest.mark.redis
def test_redis_cache_basic_functionality(redis_cache):
    """Test basic caching with Redis backend."""
    call_count = 0

    @redis_cache()
    def test_func(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # First call should execute the function
    result1 = test_func(1, 2)
    assert result1 == 3
    assert call_count == 1

    # Second call with same args should use cache
    result2 = test_func(1, 2)
    assert result2 == 3
    assert call_count == 1

    # Call with different args should execute again
    result3 = test_func(2, 3)
    assert result3 == 5
    assert call_count == 2


@pytest.mark.redis
def test_redis_entity_tracking(redis_cache):
    """Test entity tracking with Redis backend."""
    call_count = 0

    @redis_cache(entity_type="user")
    def get_user(user_id):
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": f"User {user_id}"}

    # First call should execute the function
    user1 = get_user(1)
    assert user1["id"] == 1
    assert call_count == 1

    # Second call with same args should use cache
    user1_again = get_user(1)
    assert user1_again["id"] == 1
    assert call_count == 1

    # Invalidate user 1 and verify it causes a re-fetch
    redis_cache.invalidate_entity("user", 1)
    user1_refetch = get_user(1)
    assert user1_refetch["id"] == 1
    assert call_count == 2


@pytest.mark.redis
def test_redis_cross_process_caching(redis_client):
    """Test that caching works across different cache instances (simulating different processes)."""
    # Create two separate cache instances that share the same Redis
    cache1 = EntityCache(
        backend=RedisBackend(redis_client),
        prefix="test:",
        ttl=60
    )

    cache2 = EntityCache(
        backend=RedisBackend(redis_client),
        prefix="test:",
        ttl=60
    )

    # Define functions with both caches
    call_count = 0

    @cache1(entity_type="user")
    def get_user_cache1(user_id):
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": f"User {user_id}"}

    @cache2(entity_type="user")
    def get_user_cache2(user_id):
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": f"User {user_id}"}

    # First call with cache1 should execute
    user1 = get_user_cache1(1)
    assert user1["id"] == 1
    assert call_count == 1

    # Call with cache2 should use the shared Redis cache
    user1_from_cache2 = get_user_cache2(1)
    assert user1_from_cache2["id"] == 1
    assert call_count == 1  # Should still be 1

    # Invalidate from cache1
    cache1.invalidate_entity("user", 1)

    # Both caches should now re-fetch
    user1_after_invalidate1 = get_user_cache1(1)
    assert user1_after_invalidate1["id"] == 1
    assert call_count == 2

    user1_after_invalidate2 = get_user_cache2(1)
    assert user1_after_invalidate2["id"] == 1
    assert call_count == 2  # No additional execution


@pytest.mark.redis
def test_redis_msgspec_serialization(redis_client):
    """Test using msgspec.msgpack as default serializer with Redis."""

    

    # Create a cache with default settings (should use msgspec)
    backend = RedisBackend(redis_client)
    cache = EntityCache(backend=backend, prefix="test:", ttl=60)

    # Verify msgspec is being used
    assert cache.serializer == msgspec.msgpack.encode
    assert cache.deserializer == msgspec.msgpack.decode

    call_count = 0

    @cache(entity_type="product")
    def get_product(product_id):
        nonlocal call_count
        call_count += 1
        return {
            "id": product_id,
            "name": f"Product {product_id}",
            "price": 19.99,
            "tags": ["sale", "featured"],
            "meta": {
                "created_at": "2023-01-01",
                "updated_at": "2023-01-02"
            }
        }

    # First call should serialize using msgspec.msgpack
    product = get_product(42)
    assert product["id"] == 42
    assert call_count == 1

    # Get the raw data from Redis to verify it's msgpack format, not JSON
    # Note: We don't know the exact key, so we search for all cache keys
    keys = redis_client.keys("test:c:*")
    assert len(keys) > 0

    # Get the value and verify it's binary msgpack data, not JSON string
    raw_value = redis_client.get(keys[0])
    assert isinstance(raw_value, bytes)
    # JSON would start with { (123 in ASCII) or [ (91 in ASCII) if it was a string
    # msgpack binary format is more compact and doesn't follow JSON text patterns
    assert raw_value[0] != 123 and raw_value[0] != 91

    # Deserialize manually with msgpack to verify it works
    decoded = msgspec.msgpack.decode(raw_value)
    assert isinstance(decoded, dict)
    assert decoded["id"] == 42
    assert decoded["tags"] == ["sale", "featured"]

    # Second call should use cached msgpack data
    product_again = get_product(42)
    assert product_again["id"] == 42
    assert call_count == 1  # Verify cache was used


@pytest.mark.redis
def test_redis_error_handling(redis_client, monkeypatch):
    """Test error handling with Redis backend."""
    backend = RedisBackend(redis_client)
    cache = EntityCache(backend=backend, prefix="test:", ttl=60)

    call_count = 0

    @cache()
    def test_func():
        nonlocal call_count
        call_count += 1
        return {"result": "success"}

    # First call should execute normally
    result = test_func()
    assert result["result"] == "success"
    assert call_count == 1

    # Simulate Redis connection error for get operation
    def mock_get_error(key):
        raise redis.exceptions.ConnectionError("Simulated Redis connection error")

    monkeypatch.setattr(backend, "get", mock_get_error)

    # Call should execute function again since Redis get fails
    result = test_func()
    assert result["result"] == "success"
    assert call_count == 2

    # Restore get method
    monkeypatch.undo()

    # Simulate Redis error during set operation
    def mock_setex_error(key, expiration_seconds, value):
        raise redis.exceptions.ConnectionError("Simulated Redis connection error")

    monkeypatch.setattr(backend, "setex", mock_setex_error)

    # Call should execute function and return result even if cache set fails
    result = test_func()
    assert result["result"] == "success"
    assert call_count == 3


@pytest.mark.redis
def test_redis_normalize_args(redis_client):
    """Test normalize_args feature with Redis backend."""
    backend = RedisBackend(redis_client)
    cache = EntityCache(backend=backend, prefix="test:", ttl=60)

    call_count = 0

    # Use normalize_args=True to get consistent caching across parameter styles
    @cache(normalize_args=True)
    def search_products(filters=None, sort=None, limit=10):
        nonlocal call_count
        call_count += 1
        return {
            "count": 42,
            "results": [f"Product {i}" for i in range(1, limit + 1)]
        }

    # Call with positional args
    result1 = search_products({"category": "electronics"}, "price_asc", 5)
    assert len(result1["results"]) == 5
    assert call_count == 1

    # Call with named args (different order)
    result2 = search_products(
        limit=5,
        sort="price_asc",
        filters={"category": "electronics"}
    )
    assert len(result2["results"]) == 5
    assert call_count == 1  # Should use cache due to normalize_args=True

    # Call with mixed args
    result3 = search_products({"category": "electronics"}, sort="price_asc", limit=5)
    assert len(result3["results"]) == 5
    assert call_count == 1  # Should still use cache

    # Call with different parameters (should increase count)
    search_products(
        {"category": "electronics", "in_stock": True},
        "price_asc",
        5
    )
    assert call_count == 2  # Different filters, should not use cache

    # Call again with same parameters but different dict order (should use cache)
    search_products(
        {"in_stock": True, "category": "electronics"},
        "price_asc",
        5
    )
    assert call_count == 2  # Should use cache due to dict key normalization

    # Test with lists and sets (should be normalized)
    call_count = 0

    @cache(normalize_args=True)
    def search_by_ids(ids, include_details=False):
        nonlocal call_count
        call_count += 1
        return [f"Item {id_}" for id_ in ids]

    # Call with list
    result1 = search_by_ids([3, 1, 2])
    assert "Item 1" in result1
    assert call_count == 1

    # Call with same list but different order
    result2 = search_by_ids([1, 2, 3])
    assert call_count == 1  # Should use cache due to list normalization

    # Call with tuple (converted to list internally)
    result3 = search_by_ids((1, 2, 3))
    assert call_count == 1  # Should use cache

    # Call with set (converted to sorted list internally)
    _ = search_by_ids({3, 1, 2})  # Result not used here, just testing caching behavior
    assert call_count == 1  # Should use cache
