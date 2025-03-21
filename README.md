# CacheRef
<!-- COVERAGE_BADGE -->
[![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen)](https://github.com/timabilov/refcache)

#### Entity driven read-through cache decorator tailored and optimized for event-driven invalidations 🚀

You can think of it as old good cache decorator but with steroids 💊. It ensures fresh records with real-time update & synchronization support across your ecosystem without extra effort.

To understand its mechanics, see [How It Works](#how-it-works) and Check [Why this library?](#why-this-library)

> Note: This project is under active development. Use with caution.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
  - [Basic Usage](#basic-usage)
    - [With Entity Tracking](#with-entity-tracking)
    - [Plain Caching](#plain-caching)
  - [Custom ID Fields](#custom-id-fields)
  - [ORM Integration](#orm-integration)
    - [SQLAlchemy Integration](#sqlalchemy-integration)
    - [Django Integration](#django-integration)
- [How It Works](#how-it-works)
- [Why this library?](#why-this-library)
  - [ORM limitations](#orm-limitations)
  - [Write-Through vs. Read-Through Tradeoffs](#write-through-vs-read-through-tradeoffs)
  - [What it does?](#what-it-does)
- [Advanced Usage](#advanced-usage)
  - [Cross-Service Caching](#cross-service-caching)
  - [Custom Serialization](#custom-serialization)
- [API Reference](#api-reference)
  - [EntityCache](#entitycache)
  - [@cache()](#cache)
  - [Invalidation Methods](#invalidation-methods)
  - [Cache Backends](#cache-backends)
    - [1. Redis Backend (Optional)](#1-redis-backend-optional)
    - [2. In-Memory Backend](#2-in-memory-backend-great-for-testing-or-small-applications)
    - [3. Custom Backends](#3-custom-backends)
  - [Logging and Debugging](#logging-and-debugging)
- [Development and Testing](#development-and-testing)
  - [Running Tests](#running-tests)
- [License](#license)

## Features

- 🔑 **Smart Invalidation**: Instantly clears all unique function call caches tied to an entity’s footprint
- 📋 **Custom ID Fields**: Support for entities with non-standard/composite ID field names
- 🔒 **Custom Backend**: Custom backend support with Built-in Redis/Memory backends 
- 🔄 **Cross-Service Compatible**: Designed to play nice across services with traditional and simple payloads
- 🧩 **ORM Integration**: Optional support for SQLAlchemy and Django models with auto primary key extraction

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
cache = EntityCache(backend=backend, locked_ttl=3600)

# Or use in-memory backend for testing (default)
memory_cache = EntityCache()
```

## Usage Examples

### Basic Usage

#### With Entity Tracking

```python
# Cache function results and track entity reference *only* for targeted invalidation
@cache('user')  # or `@cache.tracks('user')`
def get_user(user_id): 
    # db/interservice query...
    # 'id' = default id_key of entity
    return {"id": user_id, "name": f"User {user_id}"}

# Get user (will be cached)
user = get_user(42)

# Update user and automatically invalidate cache
@cache.invalidates('user')
def update_users(user_ids, data):
    # Update in database...
    # The return value is used to invalidate all cached functions that was containing this user ids
    return [{"id": user_ids[0], "name": data.get("name")},  {"id": user_ids[1], "name": data.get("name")}]

# Or manually invalidate
def delete_user(user_id):
    # Delete from database...
    # Then invalidate all cached functions that was containing this user id in return
    cache.invalidate_entity("user", user_id)
```


#### Plain Caching

You can also use cacheref as a traditional function cache without entity tracking:

```python
# Simple function cache (no entity tracking)
@cache()
def calculate_value(x, y):
    # Expensive computation here
    return x * y * 100

# Invalidate by function name
cache.invalidate_func(calculate_value)

```

### Custom ID Fields

```python

@cache(entity="customer", id_key="customer_id")
def get_customer(customer_id):
    # Your database query here
    return {"customer_id": customer_id, "name": f"Customer {customer_id}"}

@cache(entity="transaction", id_key=("product_id", "user_id"))  # composite id fields supported
def get_user_transactions(user_id):
    # Your database query here
    return [
        {"product_id": 1, "user_id": user_id, "value": 20.54},
        {"product_id": 2, "user_id": user_id, "value": 30.54}
    ]

@cache(entity="customer", id_key=lambda item: item["customer_id"])
def get_customer_callable_id(customer_id):
    # Your database query here
    return {"customer_id": customer_id, "name": f"Customer {customer_id}"}


```

### ORM Integration

Cacheref doesn’t interact closely with ORM internals by still being able to cache almost any of your query results. Just send  model classes as entity to SQLAlchemy or Django ORM and it will extract entity name and primary keys (or composite)  without needing extensive integration. This approach helps it remain lightweight and independent of those libraries!

> Note: 
> * Pickle is used as default serializer/deserializer. It can be customized
> * Retrieved ORM objects are detached from their original database session.
> * Dependency/Relations of entities are not tracked.

#### SQLAlchemy Integration

```python
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    name = Column(String)

# Pass the model class directly - no need to specify entity name or id_key
@cache.tracks(User)
def get_user(user_id):
    return session.query(User).get(user_id)  # you can return list too

# Automatically invalidates cache based on primary key
@cache.invalidates(User)
def update_user(user_id, name):
    user = session.query(User).get(user_id)
    user.name = name
    session.commit()
    return user # if list is provided, it invalidates all items

# For manually resetting entity pass table name
# for composite key pass tuple
cache.invalidate_entity(User.__table__, user_id)  



# Complex queries

# Here we explicitly *have* to say that we stick to order entity to be tracked for changes
@memory_cache(Order, id_key=lambda item: item[0].id)
def get_orders_with_user(session: Session, order_id: str) -> List[Row[Tuple[Order, User]]]:
    return session.query(Order, User).join(User).filter(Order.id == order_id).all()

```

#### Django Integration

```python
from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()

# Pass the model class directly - no need to specify entity name or id_key
@cache.tracks(Article)
def get_article(article_id):
    return Article.objects.get(id=article_id) # you can return list too

# Automatically invalidates cache based on primary key
@cache.invalidates(Article)
def update_article(article_id, title):
    article = Article.objects.get(id=article_id)
    article.title = title
    article.save()
    return article # if list is provided, it invalidates all items
```

The ORM integration is optional - SQLAlchemy and Django are not required dependencies.

## How It Works

### Use-case

Let's say you have a lot of functions, all centered around returning same logical `User` entity, but in different shape and forms. All of them returns same `User` data.

Now, imagine caching the varied outputs of these functions while maintaining invalidation control: when a User changes, you want all related caches (unique function calls) to clear automatically, guided by events - a.k.a implement event-driven invalidation. Here, we cannot use basic cache decorator libraries as they lack the ability to link functions to the entities they involve. This is where this library got you covered.

When a function is decorated with `@cache(entity="user")`:

1. The decorator **caches the function result as usual**
2. It **extracts entity reference IDs** from any result (e.g., `[{"id": 42, ...}, ...]` or `[User(id=42,...), ...]`)
3. It **creates an reverse index** mapping for each entity to cache specific **function calls** containing it

When an entity changes:

1. You call `cache.invalidate_entity("user", 42)` (see examples for more)
2. The library **finds all cache keys** - function calls that decorated with `@cache()` containing this entity whether it list or single value (see specifications)
3. Only those **specific caches/function calls are invalidated** 


Effectively, you end up using traditional cache decorator that can be granularly invalidated within your ecosystem giving you near real-time data consistency. This means you don't need to remember all the different ways an entity might be cached and glue that into your read codebase - just invalidate by entity ID, and all relevant caches are automatically cleared.

>❗ To ensure cache consistency across the system, please bear in mind these rules:
>* Ensure entity identity consistency - an entity with a specific ID must represent the identical data object across all system components.

## Why this library?

Simple caching libraries often lack event-driven invalidation, while ORM-integrated solutions are *tied* to specific frameworks and struggle with non-ORM traditional data format which still can hold entity references across other services - a quite common case. This lightweight library fills that gap.

### ORM limitations

Unlike ORM-specific caching tools, this library supports any data format—Django models, SQLAlchemy objects, or plain dictionaries—without tying you to a framework. It abstracts ORM internals, enabling caching and invalidation with just a data reference.


### Write-Through vs. Read-Through Tradeoffs

Write-through caching keeps data consistent but couples your read and cache layers together, complicating each read component in a different way. On the other side, plain read-through caching can leave you with stale data. This library blends read-through caching with event-driven invalidation to deliver near real-time consistency, without lock-in.

### What it does?

This library provides the classic and convenient read-through caching decorator for your functions with significant enhancement. When an entity is updated, it traces all function calls containing this entity and clears the cache either automatically or manually, as long as you provide the reference to track it in function decorator. It integrates seamleassly into your existing codebase—unlike write-through caching—and supports a wide range of data structures, including Django ORM models, SQLAlchemy objects, or basic lists of dictionaries, with minimal overhead. This approach allows to use write-around caching very effectively by tracking all invalidation points across your platform while maintaining the same flexibility of read-through cache

## Advanced Usage

### Cross-Service Caching

No special treatment needed, it just works! As an example, given that you use same prefix in all of your services, on update of the particular user - cache is able to identify all function call points that it needs to invalidate for a given user.


```python
# In service A

UserEntity = "user"
@cache(entity=UserEntity)
def get_user_from_auth(user_id):
    # get data from service C or any source basically
    return {"id": user_id, "name": "Sam Jones"}

get_user_from_auth(1) # cached now, and "user" = 1 now references function with this parameter

# In service B
UserEntity = "user"
@cache(entity=UserEntity)
def get_filtered_users(user_ids):  # Completely different function, but same logical entities
    
    return [{"id": user_ids[0], "name": "Sam Jones"}, {"id": user_ids[2], "name": "Another Sam Jones"}]

get_filtered_user([1, 2])  # cached now, also 2 entities are referencing this function call.

# In any of your services

# Given that your key_prefix is same everywhere,
# it will invalidate *all* function calls in your platform where it returned user with ID of 1.
# see @cache.invalidates for more
cache.invalidate("user", 1)

```

> 💡 Note: Optionally if you want to share the *same* cache result between functions use `cache_key`, but in this case make sure to keep them idempotent

### Custom Entity Extraction (TODO)

```python
class CustomCache(EntityCache):
    def extract_entity_ids():
        #
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
@cache(entity="event")
def get_event(event_id):
    return {
        "id": event_id,
        "start_time": datetime.now(),  # Not JSON serializable
        "attendees": set([1, 2, 3]) # same here
    }
```

> Note: pickle is used by default if ORM Integration is used

## API Reference

### EntityCache

Main class for creating cache decorators.

```python
cache = EntityCache(
    backend=None,  # CacheBackend instance (optional, will use in-memory if None)
    global_supported_id_types=(int, str, UUID)  # Tuple of primitive types that are considered valid entity IDs.
    locked_ttl=3600,  # Default locked TTL in seconds, in case if set, decorator cannot override this value (optional)
    fail_on_missing_id=True, # Raise an error if an ID cannot be extracted from the result
    serializer=json.dumps,  # Custom serializer function (optional)
    deserializer=json.loads,  # Custom deserializer function (optional)
    debug=False,  # Enable debug logging (optional)
    enabled=True, # Enable or disable caching (useful for testing or development)
)
```

### Cache Decorators

EntityCache provides several decorator methods for caching function results:

#### @cache() / @cache.\_\_call\_\_()

The traditional decorator for caching function results:

```python
@cache(
    entity="user",  # Type of entity returned (string) or ORM model class (optional)
    id_key=None,  # default = 'id'. Field name or callable resolved to entity ID, not relevant on flat lists (optional)
    supported_id_types = (int, str, UUID) # Types that are treated as valid entity IDs when extracted
    cache_key=None,  # Custom cache key for function (optional)
    normalize_args=False,  # Whether to normalize arguments (optional)
    ttl=None,  # Override default TTL, raises error if locked_ttl is set (optional)
)
def my_function():
    # ...
```

You can also use an ORM model class directly:

```python
# Using SQLAlchemy model
from myapp.models import User  # SQLAlchemy model

@cache(entity=User)
def get_user(user_id):
    # ...

# Using Django model
from myapp.models import Article  # Django model

@cache(entity=Article)
def get_article(article_id):
    # ...
```

#### @cache.tracks()

A more expressive alias for `@cache()`

#### @cache.invalidates()

Automatically invalidates entity caches based on the function's return value:

```python
@cache.invalidates(
    entity="user",  # Type of entity to invalidate (string or ORM model class)
    id_key="id"     # How to extract entity IDs from the return value
)
def update_user(user_id, data):
    # Update in database...
    return {"id": user_id, "name": data.get("name")}

# With ORM model class
from myapp.models import User  # SQLAlchemy or Django model

@cache.invalidates(User)  # Automatically extracts primary key from model instance
def update_user(user_id, data):
    # Update in database...
    user = session.query(User).get(user_id)  # or User.objects.get(id=user_id)
    user.name = data.get("name")
    session.commit()  # or user.save()
    return user # it invalidates this user cache
```
### Invalidation Methods

```python
# Invalidate all caches containing a specific entity
cache.invalidate_entity("user", 42)

# Invalidate all caches for a specific function
cache.invalidate_function(function_name)

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

The `key_prefix` parameter allows for more efficient namespacing directly at the backend level

#### 2. In-Memory Backend (great for testing or small applications)

```python
from cacheref import EntityCache, MemoryBackend

# With namespace
memory_backend = MemoryBackend(key_prefix="app:")
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

The library includes built-in logging for debugging:

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

## Development and Testing

```bash

poetry install

./run_tests.sh

```

## TODO
- [ ] Automatic ORM model detection, @cache.orm()
- [ ] Better api naming. @cache.invalidate_on(entity="user"), or @cache().tracks("user") or @cache.with_tracking etc
- [ ] MyPy Refactory & Cleanup
- [ ] Introduce proper reverse index interface to not lock into Redis OSS comp
- [ ] * By default RedisCompReverser should be used with multi-exec capability
- [ ] Stale refs sweep scheduler / CLI comand
- [ ] Tests

## License

MIT
