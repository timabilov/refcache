"""Tests for the EntityCache core functionality."""

import json
import time

import msgspec.msgpack
from msgspec import msgpack

from cacheref import EntityCache, MemoryBackend


def test_entity_cache_init():
    """Test EntityCache initialization with defaults."""
    cache = EntityCache()
    assert isinstance(cache, EntityCache)
    assert isinstance(cache.backend, MemoryBackend)
    assert cache.ttl == 3600
    assert cache.serializer == msgpack.encode
    assert cache.deserializer == msgpack.decode


def test_entity_cache_custom_init():
    """Test EntityCache initialization with custom values."""
    backend = MemoryBackend()

    def custom_serializer(x):
        return json.dumps(x, indent=2)

    def custom_deserializer(x):
        return json.loads(x)

    cache = EntityCache(
        backend=backend,
        ttl=60,
        serializer=custom_serializer,
        deserializer=custom_deserializer,
        debug=True
    )

    assert cache.backend == backend
    assert cache.ttl == 60
    assert cache.serializer == custom_serializer
    assert cache.deserializer == custom_deserializer


def test_entity_cache_default_serializer():
    """Test default serializer selection."""

    cache = EntityCache()

    assert cache.serializer == msgspec.msgpack.encode
    assert cache.deserializer == msgspec.msgpack.decode

    # Test round-trip serialization
    data = {"id": 123, "name": "Test", "values": [1, 2, 3]}
    serialized = cache.serializer(data)
    deserialized = cache.deserializer(serialized)
    assert deserialized == data


def test_entity_cache_basic_caching(memory_cache):
    """Test basic function caching without entities."""
    call_count = 0

    @memory_cache()
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


def test_entity_cache_with_entities(memory_cache):
    """Test caching with entity tracking."""
    call_count = 0

    @memory_cache(entity_type="user")
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

    # Call with different ID should execute again
    user2 = get_user(2)
    assert user2["id"] == 2
    assert call_count == 2

    # Invalidate user 1 and verify it causes a re-fetch
    memory_cache.invalidate_entity("user", 1)
    user1_refetch = get_user(1)
    assert user1_refetch["id"] == 1
    assert call_count == 3

    # User 2 should still be cached
    user2_again = get_user(2)
    assert user2_again["id"] == 2
    assert call_count == 3


def test_entity_cache_invalidate_function(memory_cache):
    """Test invalidating all cached results for a function."""
    call_count = 0

    @memory_cache()
    def test_func(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # Make multiple calls to cache different arg combinations
    test_func(1, 2)
    test_func(2, 3)
    test_func(3, 4)
    assert call_count == 3

    # Call again - should all be cached
    test_func(1, 2)
    test_func(2, 3)
    test_func(3, 4)
    assert call_count == 3

    # Invalidate the function using the convenience method
    memory_cache.invalidate_func(test_func)

    # Call again - should all re-execute
    test_func(1, 2)
    test_func(2, 3)
    test_func(3, 4)
    assert call_count == 6


def test_entity_cache_invalidate_key(memory_cache):
    """Test invalidating specific cache key."""
    call_count = 0

    @memory_cache()
    def test_func(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # Make multiple calls to cache different arg combinations
    test_func(1, 2)
    test_func(2, 3)
    assert call_count == 2

    # Call again - should all be cached
    test_func(1, 2)
    test_func(2, 3)
    assert call_count == 2

    # Invalidate specific key using the convenience method
    memory_cache.invalidate_func_call(test_func, 1, 2)

    # Call again - only the invalidated key should re-execute
    test_func(1, 2)
    test_func(2, 3)
    assert call_count == 3


def test_plain_cache_without_entity_type(memory_cache):
    """Test using the cache as a plain function cache without entity type."""
    call_count = 0

    @memory_cache()  # No entity_type specified
    def get_data(data_id):
        nonlocal call_count
        call_count += 1
        return {"id": data_id, "value": f"Data {data_id}"}

    # First call should execute the function
    data1 = get_data(1)
    assert data1["id"] == 1
    assert call_count == 1

    # Second call with same args should use cache
    data1_again = get_data(1)
    assert data1_again["id"] == 1
    assert call_count == 1

    # Call with different id should execute again
    data2 = get_data(2)
    assert data2["id"] == 2
    assert call_count == 2

    # Verify that invalidate_entity doesn't affect this cache
    # because it's not using entity tracking
    memory_cache.invalidate_entity("data", 1)
    data1_after = get_data(1)
    assert data1_after["id"] == 1
    # should be cached because we above function is not linked to "data" entity!
    assert call_count == 2

    # Function-specific invalidation should work
    memory_cache.invalidate_func(get_data)
    data1_refetch = get_data(1)
    assert data1_refetch["id"] == 1
    assert call_count == 3  # Should increase after invalidation


def test_plain_cache_with_func_key_only(memory_cache):
    """Test using the cache with entity_type but func_key_only=True."""
    call_count = 0

    @memory_cache(entity_type="product", func_key_only=True)
    def get_product(product_id):
        nonlocal call_count
        call_count += 1
        return {"id": product_id, "name": f"Product {product_id}"}

    # First call should execute the function
    product1 = get_product(1)
    assert product1["id"] == 1
    assert call_count == 1

    # Second call with same args should use cache
    product1_again = get_product(1)
    assert product1_again["id"] == 1
    assert call_count == 1

    # Verify that invalidate_entity also *invalidates* entity cache
    memory_cache.invalidate_entity("product", 1)
    product1_after = get_product(1)
    assert product1_after["id"] == 1
    assert call_count == 2  # Should not be cached.

    # Function-specific invalidation should work
    memory_cache.invalidate_func(get_product)
    product1_refetch = get_product(1)
    assert product1_refetch["id"] == 1
    assert call_count == 3  # Should increase after invalidation


def test_mixed_entity_and_plain_caching(memory_cache):
    """Test using both entity-tracked and plain caching in the same environment."""
    call_count = 0

    # Function with entity tracking
    @memory_cache(entity_type="user")
    def get_user(user_id):
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": f"User {user_id}"}

    # Function with plain caching (no entity tracking)
    @memory_cache()
    def get_user_stats(user_id):
        nonlocal call_count
        call_count += 1
        return {"user_id": user_id, "logins": 10, "last_seen": "2023-01-01"}

    # Entity-tracked function with same entity type but func_key_only=True
    @memory_cache(entity_type="user", func_key_only=True)
    def get_user_preferences(user_id):
        nonlocal call_count
        call_count += 1
        return {"user_id": user_id, "theme": "dark", "notifications": True}

    # Call all functions
    user = get_user(1)
    stats = get_user_stats(1)
    prefs = get_user_preferences(1)
    assert call_count == 3

    # Call again - all should be cached
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 3

    # Invalidate entity - should only affect entity-tracked function
    memory_cache.invalidate_entity("user", 1)
    
    # Entity-tracked function should re-execute
    get_user(1)
    assert call_count == 4
    
    # Plain cache functions should still use cache
    get_user_stats(1)
    assert call_count == 4
    
    # func_key_only=True function should still use cache despite having entity_type
    get_user_preferences(1)
    assert call_count == 4

    # Invalidate a specific function - should only affect that function
    memory_cache.invalidate_func(get_user_stats)
    
    # This function should re-execute
    get_user_stats(1)
    assert call_count == 5
    
    # Other functions should still use cache
    get_user(1)
    get_user_preferences(1)
    assert call_count == 5

    # Invalidate all - should affect all functions
    memory_cache.invalidate_all()
    
    # All functions should re-execute
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 8


def test_plain_cache_custom_key_name(memory_cache):
    """Test using a custom cache_key with plain caching."""
    call_count = 0

    @memory_cache(cache_key="custom_cache_key")
    def function_with_long_name(data_id):
        nonlocal call_count
        call_count += 1
        return {"id": data_id, "value": f"Data {data_id}"}

    # First call should execute the function
    data = function_with_long_name(1)
    assert data["id"] == 1
    assert call_count == 1

    # Second call should use cache
    data_again = function_with_long_name(1)
    assert data_again["id"] == 1
    assert call_count == 1

    # Invalidate using the custom cache key
    memory_cache.invalidate_function("custom_cache_key")
    
    # Function should re-execute
    function_with_long_name(1)
    assert call_count == 2

    # The convenience method should also work with the function object
    memory_cache.invalidate_func(function_with_long_name)
    
    # Function should re-execute
    function_with_long_name(1)
    assert call_count == 3


def test_entity_cache_invalidate_all(memory_cache):
    """Test invalidating all cache entries."""
    call_count = 0

    @memory_cache()
    def test_func1(a):
        nonlocal call_count
        call_count += 1
        return a * 2

    @memory_cache()
    def test_func2(a):
        nonlocal call_count
        call_count += 1
        return a * 3

    # Make multiple calls to cache different functions/args
    test_func1(1)
    test_func1(2)
    test_func2(1)
    test_func2(2)
    assert call_count == 4

    # Call again - should all be cached
    test_func1(1)
    test_func1(2)
    test_func2(1)
    test_func2(2)
    assert call_count == 4

    # Invalidate all cache entries
    memory_cache.invalidate_all()

    # Call again - should all re-execute
    test_func1(1)
    test_func1(2)
    test_func2(1)
    test_func2(2)
    assert call_count == 8


def test_entity_cache_ttl(memory_cache):
    """Test cache entry expiration."""
    # Use a short TTL
    memory_cache.ttl = 0.3

    call_count = 0

    @memory_cache()
    def test_func(a):
        nonlocal call_count
        call_count += 1
        return a * 2

    # First call should execute the function
    result1 = test_func(1)
    assert result1 == 2
    assert call_count == 1

    # Second call should use cache
    result2 = test_func(1)
    assert result2 == 2
    assert call_count == 1

    # Wait for TTL to expire
    time.sleep(0.4)

    # Call again - should re-execute
    result3 = test_func(1)
    assert result3 == 2
    assert call_count == 2


def test_entity_cache_function_ttl_override(memory_cache):
    """Test TTL override at function level."""
    call_count = 0

    @memory_cache(ttl=0.3)  # Override default TTL
    def test_func(a):
        nonlocal call_count
        call_count += 1
        return a * 2

    # First call should execute the function
    result1 = test_func(1)
    assert result1 == 2
    assert call_count == 1

    # Second call should use cache
    result2 = test_func(1)
    assert result2 == 2
    assert call_count == 1

    # Wait for TTL to expire
    time.sleep(0.4)

    # Call again - should re-execute
    result3 = test_func(1)
    assert result3 == 2
    assert call_count == 2


def test_entity_cache_custom_id_field(memory_cache):
    """Test using a custom ID field for entity tracking."""
    call_count = 0

    @memory_cache(entity_type="customer", id_field="customer_id")
    def get_customer(customer_id):
        nonlocal call_count
        call_count += 1
        return {"customer_id": customer_id, "name": f"Customer {customer_id}"}

    # First call should execute the function
    customer1 = get_customer(1)
    assert customer1["customer_id"] == 1
    assert call_count == 1

    # Second call with same args should use cache
    customer1_again = get_customer(1)
    assert customer1_again["customer_id"] == 1
    assert call_count == 1

    # Invalidate customer 1 and verify it causes a re-fetch
    memory_cache.invalidate_entity("customer", 1)
    customer1_refetch = get_customer(1)
    assert customer1_refetch["customer_id"] == 1
    assert call_count == 2


def test_entity_cache_extraction_from_list(memory_cache):
    """Test extracting entity IDs from a list of objects."""
    call_count = 0

    @memory_cache(entity_type="user")
    def get_users():
        nonlocal call_count
        call_count += 1
        return [
            {"id": 1, "name": "User 1"},
            {"id": 2, "name": "User 2"},
            {"id": 3, "name": "User 3"}
        ]

    # First call should execute the function
    users = get_users()
    assert len(users) == 3
    assert call_count == 1

    # Second call should use cache
    users_again = get_users()
    assert len(users_again) == 3
    assert call_count == 1

    # Invalidate user 2 and verify it causes a re-fetch
    memory_cache.invalidate_entity("user", 2)
    users_refetch = get_users()
    assert len(users_refetch) == 3
    assert call_count == 2


def test_convenience_invalidation_methods(memory_cache):
    """Test the convenience methods for invalidation."""
    call_count = 0

    @memory_cache()
    def add(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    @memory_cache()
    def multiply(a, b):
        nonlocal call_count
        call_count += 1
        return a * b

    # Cache some values
    add(1, 2)
    add(3, 4)
    multiply(2, 3)
    multiply(4, 5)
    assert call_count == 4

    # Call again - should use cache
    add(1, 2)
    add(3, 4)
    multiply(2, 3)
    multiply(4, 5)
    assert call_count == 4

    # Test invalidate_func
    memory_cache.invalidate_func(add)

    # Add calls should re-execute, multiply should still be cached
    add(1, 2)
    add(3, 4)
    multiply(2, 3)
    multiply(4, 5)
    assert call_count == 6

    # Reset for next test
    call_count = 0
    add(1, 2)
    add(3, 4)
    multiply(2, 3)
    multiply(4, 5)
    assert call_count == 0  # All cached

    # Test invalidate_func_call
    memory_cache.invalidate_func_call(multiply, 2, 3)

    # Only multiply(2, 3) should re-execute
    add(1, 2)
    add(3, 4)
    multiply(2, 3)
    multiply(4, 5)
    assert call_count == 1
