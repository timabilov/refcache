"""Tests for SQLAlchemy integration with cacheref."""

from math import pi
import uuid
from typing import Optional

import pytest

from cacheref import EntityCache
from cacheref.backends.memory import MemoryBackend
from cacheref.orm import get_entity_name_and_id_extractor

try:
    import sqlalchemy as sa
    from sqlalchemy.orm import Session, declarative_base, sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

# Skip all tests if SQLAlchemy is not installed
pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy is not installed")

# SQLAlchemy setup
Base = declarative_base()

# Model with standard integer primary key
class User(Base):
    __tablename__ = 'users'

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String)
    email = sa.Column(sa.String, unique=True)

    def __repr__(self):
        return f"User(id={self.id}, name={self.name})"

# Model with different name for primary key
class Product(Base):
    __tablename__ = 'products'

    product_id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String)
    price = sa.Column(sa.Float)

    def __repr__(self):
        return f"Product(product_id={self.product_id}, name={self.name})"

# Model with UUID primary key
class Order(Base):
    __tablename__ = 'orders'

    id = sa.Column(sa.String, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('users.id'))
    total = sa.Column(sa.Float)

    def __repr__(self):
        return f"Order(id={self.id}, user_id={self.user_id})"

# Model with composite primary key
class OrderItem(Base):
    __tablename__ = 'order_items'

    order_id = sa.Column(sa.String, sa.ForeignKey('orders.id'), primary_key=True)
    product_id = sa.Column(sa.Integer, sa.ForeignKey('products.product_id'), primary_key=True)
    quantity = sa.Column(sa.Integer)

    def __repr__(self):
        return f"OrderItem(order_id={self.order_id}, product_id={self.product_id})"

from sqlalchemy.orm import as_declarative, declared_attr

# custom base

@as_declarative()
class CustomBase:
    __name__: str

    @declared_attr
    def __tablename__(cls) -> str:
        """Returns table name  by lowercasing a Class name"""
        return cls.__name__.lower()

    pk = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

# Model without explicit tablename
class Tag(CustomBase):
    # SQLAlchemy will auto-generate from CustomBase
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String)

    def __repr__(self):
        return f"Tag(id={self.id}, name={self.name})"


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with test tables."""
    if not HAS_SQLALCHEMY:
        pytest.skip("SQLAlchemy is not installed")

    # Create in-memory database
    engine = sa.create_engine('sqlite:///:memory:')

    # Create tables
    Base.metadata.create_all(engine)
    CustomBase.metadata.create_all(engine)

    # Create a session
    Session = sessionmaker(bind=engine)
    session = Session()

    # Insert some test data
    user = User(id=1, name="Test User", email="test@example.com")
    product = Product(product_id=101, name="Test Product", price=9.99)
    order = Order(id="order-123", user_id=1, total=19.98)
    order_item = OrderItem(order_id="order-123", product_id=101, quantity=2)
    tag = Tag(id=1, name="Test Tag")

    session.add_all([user, product, order, order_item, tag])
    session.commit()

    yield session

    # Clean up
    session.close()


# Test entity name extraction
def test_sqlalchemy_entity_name_extraction_standard():
    """Test entity name extraction from a standard SQLAlchemy model."""
    entity_name, _ = get_entity_name_and_id_extractor(User)
    assert entity_name == "users"

def test_sqlalchemy_entity_name_extraction_custom_pk():
    """Test entity name extraction from a model with custom PK name."""
    entity_name, _ = get_entity_name_and_id_extractor(Product)
    assert entity_name == "products"

def test_sqlalchemy_entity_name_extraction_uuid_pk():
    """Test entity name extraction from a model with UUID primary key."""
    entity_name, _ = get_entity_name_and_id_extractor(Order)
    assert entity_name == "orders"

def test_sqlalchemy_entity_name_extraction_composite_pk():
    """Test entity name extraction from a model with composite primary key."""
    entity_name, _ = get_entity_name_and_id_extractor(OrderItem)
    assert entity_name == "order_items"

def test_sqlalchemy_entity_name_extraction_auto_tablename():
    """Test entity name extraction from a model with auto-generated tablename."""
    entity_name, _ = get_entity_name_and_id_extractor(Tag)
    # SQLAlchemy sets the table name automatically for the model without __tablename__
    assert entity_name == "tag"


# Test ID extraction
def test_sqlalchemy_id_extraction_standard(db_session):
    """Test ID extraction from a standard model with integer PK."""
    user = db_session.query(User).first()
    _, id_extractor = get_entity_name_and_id_extractor(User)

    extracted_id = id_extractor(user)
    assert extracted_id == 1
    assert isinstance(extracted_id, int)

def test_sqlalchemy_id_extraction_custom_pk(db_session):
    """Test ID extraction from a model with custom PK field name."""
    product = db_session.query(Product).first()
    _, id_extractor = get_entity_name_and_id_extractor(Product)

    extracted_id = id_extractor(product)
    assert extracted_id == 101
    assert isinstance(extracted_id, int)

def test_sqlalchemy_id_extraction_uuid_pk(db_session):
    """Test ID extraction from a model with UUID primary key."""
    order = db_session.query(Order).first()
    _, id_extractor = get_entity_name_and_id_extractor(Order)

    extracted_id = id_extractor(order)
    assert extracted_id == "order-123"
    assert isinstance(extracted_id, str)

def test_sqlalchemy_id_extraction_composite_pk(db_session):
    """Test ID extraction from a model with composite primary key."""
    order_item = db_session.query(OrderItem).first()
    _, id_extractor = get_entity_name_and_id_extractor(OrderItem)

    # For composite keys, SQLAlchemy extractors typically use the first PK column
    extracted_id = id_extractor(order_item)
    assert extracted_id == "order-123"  # The first part of the composite key
    assert isinstance(extracted_id, str)

def test_sqlalchemy_id_extraction_auto_tablename(db_session):
    """Test ID extraction from a model with auto-generated tablename."""
    tag = db_session.query(Tag).first()
    _, id_extractor = get_entity_name_and_id_extractor(Tag)

    extracted_id = id_extractor(tag)
    assert extracted_id == 1
    assert isinstance(extracted_id, int)


def test_simple_sqlalchemy_caching(db_session):
    """Test that caching with SQLAlchemy model works correctly."""
    # Create cache
    memory_cache = EntityCache(backend=MemoryBackend(key_prefix="sqlalchemy_test:"), debug=True)

    # Counter to track function calls
    call_count = 0

    # Create cached function using SQLAlchemy model as entity
    @memory_cache(User)
    def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
        nonlocal call_count
        call_count += 1
        return session.query(User).filter(User.id == user_id).first()

    # First call should execute the function
    user: User = get_user_by_id(db_session, 1)
    assert user is not None
    assert user.name == "Test User"
    assert call_count == 1

    # Second call should use the cache
    user: User = get_user_by_id(db_session, 1)
    assert user is not None
    assert user.name == "Test User"
    assert user.id == 1
    assert call_count == 1  # Still 1, function not called again

    # Try with a different model
    call_count = 0

    @memory_cache(Product)
    def get_product_by_id(session: Session, product_id: int) -> Optional[Product]:
        nonlocal call_count
        call_count += 1
        return session.query(Product).filter(Product.product_id == product_id).first()

    # First call should execute the function
    product = get_product_by_id(db_session, 101)
    assert product is not None
    assert product.name == "Test Product"
    assert call_count == 1

    # Second call should use the cache
    product = get_product_by_id(db_session, 101)
    assert product is not None
    assert product.name == "Test Product"
    assert call_count == 1  # Still 1, function not called again


def test_cache_composite_key(db_session):
    """Test that caching with SQLAlchemy model works correctly."""
    # Create cache
    memory_cache = EntityCache(backend=MemoryBackend(key_prefix="sqlalchemy_test:"), debug=True)

    # Counter to track function calls
    call_count = 0

    # Create cached function using SQLAlchemy model as entity
    @memory_cache(OrderItem)
    def get_order_by_product_id(session: Session, product_id: int) -> Optional[OrderItem]:
        nonlocal call_count
        call_count += 1
        return session.query(OrderItem).filter(OrderItem.product_id == product_id).all()

    ois: OrderItem = get_order_by_product_id(db_session, 101)
    oi = ois[0]
    assert oi is not None
    assert oi.quantity == 2
    assert call_count == 1

    # Second call should use the cache
    ois: OrderItem = get_order_by_product_id(db_session, 101)
    oi = ois[0]
    assert oi is not None
    assert oi.quantity == 2
    assert call_count == 1
