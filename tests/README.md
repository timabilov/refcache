# Tests for Cacheref

This directory contains tests for the `cacheref` package.

## Test Structure

- `test_memory_backend.py`: Tests for the in-memory backend implementation
- `test_redis_backend.py`: Tests for the Redis backend implementation
- `test_entity_cache.py`: Tests for the core EntityCache functionality
- `test_redis_integration.py`: Integration tests for Redis with more complex scenarios

## Running Tests

### Running all tests

```bash
# Run all tests
pytest

# Run with parallel execution
pytest -xvs -n auto

# Run with detailed output
pytest -v
```

### Running specific test groups

```bash
# Run only memory backend tests
pytest test_memory_backend.py

# Run only Redis tests
pytest -m redis

# Run Redis integration tests
pytest test_redis_integration.py
```

### Skipping Redis tests

Redis tests will be skipped automatically if Redis is not installed or if the Redis server is not running.

## Redis Test Configuration

By default, Redis tests use:
- Host: localhost
- Port: 6379
- Database: 15 (to avoid conflicts with other data)
- Prefix: "test:"

All test keys are automatically cleaned up before each test.

## Adding New Tests

When adding new tests:

1. Mark Redis tests with `@pytest.mark.redis`
2. Import from `conftest` instead of directly from the package to ensure consistent imports
3. Use the provided fixtures where possible (`memory_backend`, `memory_cache`, `redis_client`, `redis_backend`, `redis_cache`)
4. Keep tests independent - each test should clean up after itself

## Test Dependencies

- pytest
- pytest-xdist (for parallel testing)
- Redis (optional, for Redis tests)