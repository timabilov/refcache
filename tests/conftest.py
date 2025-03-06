"""Pytest configuration for cacheref tests."""

import logging
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
logging.getLogger("cacheref").setLevel(logging.DEBUG)


@pytest.fixture
def memory_backend(request):
    """Return a fresh memory backend for each test.
    
    Uses worker-specific namespace if tests are run in parallel.
    """
    worker_id = getattr(request.config, 'workerinput', {}).get('workerid', '')
    namespace = f"test:{worker_id}" if worker_id else "test"
    return MemoryBackend(key_prefix=f"{namespace}:")

@pytest.fixture
def memory_cache(memory_backend):
    """Return an EntityCache with memory backend.
    
    Uses the memory_backend fixture for proper namespacing in parallel tests.
    """
    return EntityCache(backend=memory_backend, ttl=60, debug=True)

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

@pytest.fixture
def redis_client(request):
    """Return a Redis client for testing if Redis is available.
    
    The fixture automatically:
    1. Uses a dedicated DB for testing
    2. Flushes the DB before each test
    3. Creates namespaced keys based on worker ID for parallel testing
    4. Cleans up after the test is finished
    """
    if not HAS_REDIS:
        pytest.skip("Redis is not installed")
    try:
        # Use test DB 15
        client = redis.Redis(host='localhost', port=6379, db=15)
        client.ping()  # Check connection
        
        # FLUSH THE ENTIRE TEST DB to ensure clean state
        # This is required since we're running tests with different key prefixes
        client.flushdb()
        
        # Run the test
        yield client
        
        # Clean up after the test
        client.flushdb()
    except redis.ConnectionError:
        pytest.skip("Redis server is not running")
    except Exception as e:
        pytest.skip(f"Error connecting to Redis: {e}")

@pytest.fixture
def redis_backend(redis_client, request):
    """Return a RedisBackend for testing if Redis is available.
    
    Uses worker-specific namespace if tests are run in parallel.
    """
    worker_id = getattr(request.config, 'workerinput', {}).get('workerid', '')
    namespace = f"test:{worker_id}" if worker_id else "test"
    return RedisBackend(redis_client, key_prefix=f"{namespace}:")

@pytest.fixture
def redis_cache(redis_backend):
    """Return an EntityCache with Redis backend."""
    return EntityCache(backend=redis_backend, ttl=60, debug=True)

# Add a marker for Redis tests
def pytest_configure(config):
    config.addinivalue_line("markers", "redis: mark test as requiring Redis")
