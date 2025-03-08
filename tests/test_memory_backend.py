"""Tests for the MemoryBackend implementation."""

import datetime
import time

from freezegun import freeze_time

from cacheref import MemoryBackend


def test_memory_backend_init():
    """Test MemoryBackend initialization."""
    backend = MemoryBackend()
    assert isinstance(backend, MemoryBackend)
    assert backend.data == {}
    assert backend.sets == {}
    assert backend.expires == {}


def test_memory_backend_get_set():
    """Test basic get/set operations."""
    backend = MemoryBackend()

    # Set value
    backend.set("key1", "value1")
    assert backend.get("key1") == "value1"

    # Overwrite value
    backend.set("key1", "value2")
    assert backend.get("key1") == "value2"

    # Get non-existent key
    assert backend.get("nonexistent") is None


def test_memory_backend_expiry():
    """Test expiration of keys."""
    backend = MemoryBackend()

    # Set with expiration
    backend.set("key1", "value1", expire=0.2)
    assert backend.get("key1") == "value1"

    # Wait for expiration
    now = datetime.datetime.now()
    with freeze_time(now + datetime.timedelta(seconds=0.3)):
        assert backend.get("key1") is None

    # Test setex directly
    backend.setex("key2", 0.3, "value2")
    assert backend.get("key2") == "value2"
    now = datetime.datetime.now()
    with freeze_time(now + datetime.timedelta(seconds=0.4)):
        assert backend.get("key2") is None


def test_memory_backend_delete():
    """Test key deletion."""
    backend = MemoryBackend()

    # Set multiple keys
    backend.set("key1", "value1")
    backend.set("key2", "value2")
    backend.set("key3", "value3")

    # Delete one key
    count = backend.delete("key1")
    assert count == 1
    assert backend.get("key1") is None
    assert backend.get("key2") == "value2"

    # Delete multiple keys
    count = backend.delete("key2", "key3", "nonexistent")
    assert count == 2
    assert backend.get("key2") is None
    assert backend.get("key3") is None


def test_memory_backend_keys():
    """Test pattern matching for keys."""
    backend = MemoryBackend()

    # Set keys with pattern
    backend.set("prefix:key1", "value1")
    backend.set("prefix:key2", "value2")
    backend.set("other:key3", "value3")

    # Match keys by pattern
    keys = backend.keys("prefix:*")
    assert len(keys) == 2
    assert "prefix:key1" in keys
    assert "prefix:key2" in keys

    # Match specific key
    keys = backend.keys("*key1")
    assert len(keys) == 1
    assert "prefix:key1" in keys

    # Match with expiry
    backend.set("expires:key", "value", expire=0.2)
    assert "expires:key" in backend.keys("expires:*")
    # try sleep just as a case
    time.sleep(0.3)
    assert "expires:key" not in backend.keys("expires:*")


def test_memory_backend_set_operations():
    """Test set operations (sadd, smembers)."""
    backend = MemoryBackend()

    # Add to set
    count = backend.sadd("set1", "value1", "value2")
    assert count == 2

    # Add again (shouldn't increase)
    count = backend.sadd("set1", "value2", "value3")
    assert count == 1

    # Get set members
    members = backend.smembers("set1")
    assert len(members) == 3
    assert "value1" in members
    assert "value2" in members
    assert "value3" in members

    # Get non-existent set
    assert backend.smembers("nonexistent") == set()

    # Test set expiry
    backend.sadd("set2", "value1")
    backend.expire("set2", 0.2)
    assert len(backend.smembers("set2")) == 1
    time.sleep(0.3)
    assert len(backend.smembers("set2")) == 0


def test_memory_backend_expire():
    """Test setting expiry on existing keys."""
    backend = MemoryBackend()

    # Set values
    backend.set("key1", "value1")
    backend.sadd("set1", "value1")

    # Set expiry
    result = backend.expire("key1", 0.2)
    assert result is True
    result = backend.expire("set1", 0.2)
    assert result is True
    result = backend.expire("nonexistent", 0.2)
    assert result is False

    # Check expiry works
    assert backend.get("key1") == "value1"
    assert len(backend.smembers("set1")) == 1
    original_time = datetime.datetime.now()
    with freeze_time(original_time + datetime.timedelta(seconds=0.3)):
        assert backend.get("key1") is None
        assert len(backend.smembers("set1")) == 0
