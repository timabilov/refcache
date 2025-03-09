"""Tests for the EntityCache core functionality."""

import datetime
import json
import time
from unittest import mock

import msgspec.msgpack
from freezegun import freeze_time
from msgspec import msgpack

from cacheref import EntityCache, MemoryBackend


def test_entity_cache_init():
    """Test EntityCache initialization with defaults."""
    entity_cache: EntityCache = EntityCache()
    assert isinstance(entity_cache, EntityCache)
    assert isinstance(entity_cache.backend, MemoryBackend)
    assert entity_cache.ttl is None
    assert entity_cache.serializer == msgpack.encode
    assert entity_cache.deserializer == msgpack.decode


def test_get_cache_key(memory_cache):
    """Test getting cache key for a function."""
    call_count = 0

    @memory_cache()
    def calculate_value(x, y, z=0):
        nonlocal call_count
        call_count += 1
        return x + y + z

    # Get key by function object
    key1 = memory_cache.get_cache_key(calculate_value, 1, 2)

    # Get key by function name
    module_name = calculate_value.__module__
    func_name = f"{module_name}.{calculate_value.__name__}"
    key2 = memory_cache.get_cache_key(func_name, 1, 2)

    # Both should be the same
    assert key1 == key2

    # The key should be properly formatted
    assert key1.startswith(f"cache:{module_name}.calculate_value:")

    # Now use the key to make sure it actually works

    # Call the function to add it to cache
    result = calculate_value(1, 2)
    assert result == 3
    assert call_count == 1

    # Delete using our retrieved key
    memory_cache.backend.delete(key1)

    # Call again - should need to recalculate
    result2 = calculate_value(1, 2)
    assert result2 == 3
    assert call_count == 2


def test_entity_cache_custom_init():
    """Test EntityCache initialization with custom values."""
    backend = MemoryBackend()

    def custom_serializer(x):
        return json.dumps(x, indent=2)

    def custom_deserializer(x):
        return json.loads(x)

    entity_cache = EntityCache(
        backend=backend,
       locked_ttl=60,
        serializer=custom_serializer,
        deserializer=custom_deserializer,
        debug=True
    )

    assert entity_cache.backend == backend
    assert entity_cache.ttl == 60
    assert entity_cache.serializer == custom_serializer
    assert entity_cache.deserializer == custom_deserializer


def test_entity_cache_default_serializer():
    """Test default serializer selection."""

    entity_cache = EntityCache()

    assert entity_cache.serializer == msgspec.msgpack.encode
    assert entity_cache.deserializer == msgspec.msgpack.decode

    # Test round-trip serialization
    data = {"id": 123, "name": "Test", "values": [1, 2, 3]}
    serialized = entity_cache.serializer(data)
    deserialized = entity_cache.deserializer(serialized)
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

    @memory_cache(entity="user")
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


def test_plain_cache_without_entity(memory_cache):
    """Test using the cache as a plain function cache without entity."""
    call_count = 0

    @cache(entity="user", id_key='id')  # No entity specified
    def get_data(data_id):
        nonlocal call_count
        call_count += 1
        return {"id": 1, "value": f"Data {data_id}"}

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


def test_plain_cache_with_function_scope(memory_cache):
    """Test using the cache with entity but scope='function'."""
    call_count = 0

    @memory_cache(entity="product", scope="function")
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
    @memory_cache(entity="user")
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

    # Entity-tracked function with same entity type but scope='function'
    @memory_cache(entity="user", scope="function", id_key="user_id")
    def get_user_preferences(user_id):
        nonlocal call_count
        call_count += 1
        return {"user_id": user_id, "theme": "dark", "notifications": True}

    # Call all functions
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
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

    # Another Entity-tracked function. Invalidation expected
    get_user_preferences(1)
    assert call_count == 5

    # Invalidate a specific function - should only affect that function
    memory_cache.invalidate_func(get_user_stats)

    # This function should re-execute
    get_user_stats(1)
    assert call_count == 6

    # Other functions should still use cache
    get_user(1)
    get_user_preferences(1)
    assert call_count == 6

    # Invalidate all - should affect all functions
    memory_cache.invalidate_all()

    # All functions should re-execute
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 9


def test_entity_scope_cache(memory_cache):
    """Test using both entity-tracked and plain caching with checking global scope."""
    call_count = 0

    # Function with entity tracking
    @memory_cache(entity="user", scope="entity")
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

    # Entity-tracked function with same entity type but scope='entity'
    # meaning that
    @memory_cache(entity="user", scope="entity", id_key="user_id")
    def get_user_preferences(user_id):
        nonlocal call_count
        call_count += 1
        return {"user_id": user_id, "theme": "dark", "notifications": True}

    # Call all functions, last one should be cached because of entity + id link as key
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 2

    # Call again - all should be cached
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 2

    # Invalidate entity - should only affect entity-tracked functions!
    memory_cache.invalidate_entity("user", 1)

    # Entity-tracked but entity scope function should re-execute and cache entity
    get_user(1)
    assert call_count == 3

    # Plain cache functions should still use cache
    get_user_stats(1)
    assert call_count == 3

    # Another Entity-tracked function. but because of entity scope
    # it should not re-execute because of entity + user_id link link hit
    get_user_preferences(1)
    assert call_count == 3

    # Invalidate a specific function - should only affect that function
    memory_cache.invalidate_func(get_user_stats)

    # This function should re-execute
    get_user_stats(1)
    assert call_count == 4

    # Other functions should still use cache
    get_user(1)
    get_user_preferences(1)
    assert call_count == 4

    # Invalidate all - should affect all functions
    memory_cache.invalidate_all()

    # All functions should re-execute except last because of user + user_id link
    get_user(1)
    get_user_stats(1)
    get_user_preferences(1)
    assert call_count == 6

    # last one id is changed so all should re-execute
    get_user(1)
    get_user_stats(1)
    get_user_preferences(2)
    assert call_count == 7

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
    original_time = datetime.datetime.now(tz=datetime.timezone.utc)
    with freeze_time(original_time + datetime.timedelta(seconds=1)):
        # Call again - should re-execute
        result3 = test_func(1)
        assert result3 == 2
        assert call_count == 2


def test_entity_reverse_cache_prolong_ttl(memory_cache):
    """We test that the reverse cache TTL is extended when the cache is accessed."""

    call_count = 0
    entity = "user"
    entity_id = 1
    now = datetime.datetime.now()
    with freeze_time(now):
        @memory_cache(entity=entity, ttl=10)
        def test_func(a):
            nonlocal call_count
            call_count += 1
            return {"id": a, "name": f"User {a}"}

        @memory_cache(entity=entity, ttl=90)
        def test_func_2(a):
            nonlocal call_count
            call_count += 1
            return {"id": a, "name": f"User {a}"}
        # First call should execute the function and set
        # test_func.ttl + memory_cache.reverse_index_ttl_gap ttl for the reverse index
        test_func(entity_id)
        assert call_count == 1
        entity_key = f"entity:{entity}:{entity_id}"
        assert memory_cache.backend.ttl(entity_key) == test_func.ttl + memory_cache.reverse_index_ttl_gap == 310
        # now it should prolong the ttl for same entity
        test_func_2(entity_id)
        assert call_count == 2
        entity_key = f"entity:{entity}:{entity_id}"
        assert memory_cache.backend.ttl(entity_key) == test_func_2.ttl + memory_cache.reverse_index_ttl_gap == 390

def test_entity_reverse_cache_unchanged_ttl(redis_cache):
    """We test that the reverse cache entity TTL is not affected because of short new TTL."""
    call_count = 0
    entity = "user"
    entity_id = 1
    now = datetime.datetime.now()
    with freeze_time(now):
        @redis_cache(entity=entity, ttl=90)
        def test_func(a):
            nonlocal call_count
            call_count += 1
            return {"id": a, "name": f"User {a}"}

        @redis_cache(entity=entity, ttl=10)
        def test_func_2(a):
            nonlocal call_count
            call_count += 1
            return {"id": a, "name": f"User {a}"}
        # First call should execute the function and set
        # test_func.ttl + memory_cache.reverse_index_ttl_gap ttl for the reverse index
        test_func(entity_id)
        assert call_count == 1
        entity_key = f"entity:{entity}:{entity_id}"
        assert redis_cache.backend.ttl(entity_key) == test_func.ttl + redis_cache.reverse_index_ttl_gap == 390
        # now it should stick to old ttl for same entity, to not undermine test_func ttl record for reverse index
        test_func_2(entity_id)
        assert call_count == 2
        entity_key = f"entity:{entity}:{entity_id}"
        assert redis_cache.backend.ttl(entity_key) == test_func.ttl + redis_cache.reverse_index_ttl_gap == 390



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


    original_time = time.time()
    with mock.patch('time.time', return_value=original_time + 0.4):
        # Call again - should re-execute
        result3 = test_func(1)
        assert result3 == 2
        assert call_count == 2


def test_entity_cache_custom_id_key(memory_cache):
    """Test using a custom ID field for entity tracking."""
    call_count = 0

    @memory_cache(entity="customer", id_key="customer_id")
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

    @memory_cache(entity="user")
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


def test_entity_cache_extraction_wrong_non_supported_key(memory_cache, caplog):
    """Test extracting entity IDs from a list of objects."""
    call_count = 0

    @memory_cache(entity="user", supported_id_types=(str, int))
    def get_users():
        nonlocal call_count
        call_count += 1
        return [
            {"id": [1, 2, 3], "name": "User 1"},
            {"id": 2, "name": "User 2"},
            {"id": 3, "name": "User 3"}
        ]

    # First call should execute the function
    users = get_users()
    assert len(users) == 3
    assert call_count == 1

    # Second call should not use cache, because caching failed, but function was executed
    users_again = get_users()
    assert len(users_again) == 3
    assert call_count == 2
    assert "extracted_id=[1, 2, 3] got unsupported ID value <class 'list'>" in caplog.text


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


def test_invalidates_decorator(memory_cache):
    """Test the invalidates decorator for automatic cache invalidation."""
    call_count = 0

    # Create cached function that references a user entity
    @memory_cache(entity="user")
    def get_user(user_id):
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": f"User {user_id}"}

    # Create function that updates a user and invalidates the cache
    @memory_cache.invalidates("user")
    def update_user(user_id, new_name):
        # Return a user object with the ID that should be invalidated
        return {"id": user_id, "name": new_name}

    # First call caches the result
    user = get_user(1)
    assert user["name"] == "User 1"
    assert call_count == 1

    # Call again - should use cache
    user_again = get_user(1)
    assert user_again["name"] == "User 1"
    assert call_count == 1

    # Update the user, which should invalidate the cache
    updated_user = update_user(1, "Updated User 1")
    assert updated_user["name"] == "Updated User 1"

    # Call get_user again - should re-execute because cache was invalidated
    user_after_update = get_user(1)
    assert user_after_update["name"] == "User 1"  # Note: our test function still returns the original name
    assert call_count == 2


def test_invalidates_decorator_with_custom_id_key(memory_cache):
    """Test the invalidates decorator with a custom ID key."""
    call_count = 0

    # Cached function with custom ID key
    @memory_cache(entity="customer", id_key="customer_id")
    def get_customer(customer_id):
        nonlocal call_count
        call_count += 1
        return {"customer_id": customer_id, "name": f"Customer {customer_id}"}

    # Update function with matching ID key
    @memory_cache.invalidates("customer", id_key="customer_id")
    def update_customer(customer_id, new_name):
        return {"customer_id": customer_id, "name": new_name}

    # First call caches the result
    customer = get_customer(1)
    assert customer["name"] == "Customer 1"
    assert call_count == 1

    # Call again - should use cache
    customer_again = get_customer(1)
    assert customer_again["name"] == "Customer 1"
    assert call_count == 1

    # Update customer with different ID
    update_customer(2, "Updated Customer 2")

    # Original customer should still be cached
    get_customer(1)
    assert call_count == 1

    # Update the original customer
    update_customer(1, "Updated Customer 1")

    # Now the cache for customer 1 should be invalidated
    get_customer(1)
    assert call_count == 2


