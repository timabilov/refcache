"""Pytest configuration for cacheref tests."""

import pytest

# Import from cacheref
from cacheref import EntityCache
from cacheref.backends.memory import MemoryBackend
from cacheref.backends.redis import RedisBackend

# Check if msgspec is available
try:
    import msgspec.msgpack  # noqa
    HAS_MSGSPEC = True
except ImportError:
    HAS_MSGSPEC = False

# Add fixtures that should be available for all tests here

@pytest.fixture
def memory_backend():
    """Return a fresh memory backend for each test."""
    return MemoryBackend()

@pytest.fixture
def memory_cache():
    """Return an EntityCache with memory backend."""
    return EntityCache(backend=MemoryBackend(), prefix="test:", ttl=60, debug=True)

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

@pytest.fixture
def redis_client():
    """Return a Redis client for testing if Redis is available."""
    if not HAS_REDIS:
        pytest.skip("Redis is not installed")
    try:
        client = redis.Redis(host='localhost', port=6379, db=15)  # Use DB 15 for testing
        client.ping()  # Check connection
        # Clear test database
        for key in client.keys("test:*"):
            client.delete(key)
        return client
    except redis.ConnectionError:
        pytest.skip("Redis server is not running")
    except Exception as e:
        pytest.skip(f"Error connecting to Redis: {e}")

@pytest.fixture
def redis_backend(redis_client):
    """Return a RedisBackend for testing if Redis is available."""
    return RedisBackend(redis_client)

@pytest.fixture
def redis_cache(redis_backend):
    """Return an EntityCache with Redis backend."""
    return EntityCache(backend=redis_backend, prefix="test:", ttl=60, debug=True)

# Add a marker for Redis tests
def pytest_configure(config):
    config.addinivalue_line("markers", "redis: mark test as requiring Redis")
