"""Tests for the RedisBackend implementation."""

import pytest

from cacheref import RedisBackend


@pytest.mark.redis
def test_redis_backend_init(redis_client):
    """Test RedisBackend initialization."""
    backend = RedisBackend(redis_client)
    assert isinstance(backend, RedisBackend)
    assert backend.client == redis_client


@pytest.mark.redis
def test_redis_backend_get_set(redis_client):
    """Test basic get/set operations with Redis backend."""
    backend = RedisBackend(redis_client)

    # Set value
    backend.set("test:key1", "value1")
    assert backend.get("test:key1") == b"value1"

    # Overwrite value
    backend.set("test:key1", "value2")
    assert backend.get("test:key1") == b"value2"

    # Get non-existent key
    assert backend.get("test:nonexistent") is None


@pytest.mark.redis
def test_redis_backend_setex(redis_client):
    """Test setting values with expiration."""
    backend = RedisBackend(redis_client)

    # Set with expiration
    backend.setex("test:key1", 5, "value1")
    assert backend.get("test:key1") == b"value1"

    # Check TTL is set
    ttl = redis_client.ttl("test:key1")
    assert 0 < ttl <= 5


@pytest.mark.redis
def test_redis_backend_delete(redis_client):
    """Test key deletion."""
    backend = RedisBackend(redis_client)

    # Set multiple keys
    backend.set("test:key1", "value1")
    backend.set("test:key2", "value2")
    backend.set("test:key3", "value3")

    # Delete one key
    count = backend.delete("test:key1")
    assert count == 1
    assert backend.get("test:key1") is None
    assert backend.get("test:key2") == b"value2"

    # Delete multiple keys
    count = backend.delete("test:key2", "test:key3", "test:nonexistent")
    assert count == 2
    assert backend.get("test:key2") is None
    assert backend.get("test:key3") is None


@pytest.mark.redis
def test_redis_backend_keys(redis_client):
    """Test pattern matching for keys."""
    backend = RedisBackend(redis_client)

    # Set keys with pattern
    backend.set("test:prefix:key1", "value1")
    backend.set("test:prefix:key2", "value2")
    backend.set("test:other:key3", "value3")

    # Match keys by pattern
    keys = backend.keys("test:prefix:*")
    assert len(keys) == 2
    assert b"test:prefix:key1" in keys
    assert b"test:prefix:key2" in keys

    # Match specific key
    keys = backend.keys("test:*key1")
    assert len(keys) == 1
    assert b"test:prefix:key1" in keys


@pytest.mark.redis
def test_redis_backend_set_operations(redis_client):
    """Test set operations (sadd, smembers)."""
    backend = RedisBackend(redis_client)

    # Add to set
    count = backend.sadd("test:set1", "value1", "value2")
    assert count == 2

    # Add again (shouldn't increase)
    count = backend.sadd("test:set1", "value2", "value3")
    assert count == 1

    # Get set members
    members = backend.smembers("test:set1")
    assert len(members) == 3
    assert b"value1" in members
    assert b"value2" in members
    assert b"value3" in members

    # Get non-existent set
    assert backend.smembers("test:nonexistent") == set()


@pytest.mark.redis
def test_redis_backend_expire(redis_client):
    """Test setting expiry on existing keys."""
    backend = RedisBackend(redis_client)

    # Set values
    backend.set("test:key1", "value1")
    backend.sadd("test:set1", "value1")

    # Set expiry
    result = backend.expire("test:key1", 5)
    assert result == 1  # Redis returns 1 for success
    result = backend.expire("test:set1", 5)
    assert result == 1
    result = backend.expire("test:nonexistent", 5)
    assert result == 0  # Redis returns 0 for non-existent keys

    # Check TTL is set
    ttl = redis_client.ttl("test:key1")
    assert 0 < ttl <= 5
    ttl = redis_client.ttl("test:set1")
    assert 0 < ttl <= 5


@pytest.mark.redis
def test_redis_backend_pipeline(redis_client):
    """Test pipeline operations."""
    backend = RedisBackend(redis_client)

    # Get pipeline
    pipeline = backend.pipeline()

    # Add operations to pipeline
    pipeline.set("test:pipe1", "value1")
    pipeline.set("test:pipe2", "value2")
    pipeline.sadd("test:pipeset", "value1", "value2")

    # Execute pipeline
    results = pipeline.execute()
    assert len(results) == 3

    # Verify results
    assert backend.get("test:pipe1") == b"value1"
    assert backend.get("test:pipe2") == b"value2"
    assert len(backend.smembers("test:pipeset")) == 2
