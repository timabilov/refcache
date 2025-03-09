"""Tests for Django ORM integration with cacheref."""

import uuid
from typing import Optional

import pytest

from cacheref import EntityCache
from cacheref.backends.memory import MemoryBackend
from cacheref.orm import get_entity_name_and_id_extractor
from tests.models import CompositePKModel, CustomPKModel, StringPKModel, TestModel, UUIDModel


# Basic Django model verification
@pytest.mark.django_db
def test_model_creation(enable_django):
    """Verify that the Django test model works correctly."""
    # Create a test object
    test_obj = TestModel.objects.create(
        name="Test Instance",
        description="This is a test description"
    )

    # Retrieve and verify
    retrieved_obj = TestModel.objects.get(id=test_obj.id)
    assert retrieved_obj.name == "Test Instance"
    assert retrieved_obj.description == "This is a test description"

# Test entity name extraction from various model types
@pytest.mark.django_db
def test_entity_name_extraction_standard_model():
    """Test entity name extraction from a standard Django model."""
    entity_name, _ = get_entity_name_and_id_extractor(TestModel)
    assert entity_name == "test_app_testmodel"  # Django auto-generates table names

@pytest.mark.django_db
def test_entity_name_extraction_uuid_model():
    """Test entity name extraction from a model with UUID primary key."""
    entity_name, _ = get_entity_name_and_id_extractor(UUIDModel)
    assert entity_name == "test_app_uuidmodel"

@pytest.mark.django_db
def test_entity_name_extraction_custom_pk_model():
    """Test entity name extraction from a model with custom PK field name."""
    entity_name, _ = get_entity_name_and_id_extractor(CustomPKModel)
    assert entity_name == "test_app_custompkmodel"

@pytest.mark.django_db
def test_entity_name_extraction_string_pk_model():
    """Test entity name extraction from a model with string primary key."""
    entity_name, _ = get_entity_name_and_id_extractor(StringPKModel)
    assert entity_name == "test_app_stringpkmodel"

@pytest.mark.django_db
def test_entity_name_extraction_composite_pk_model():
    """Test entity name extraction from a model with composite primary key."""
    entity_name, _ = get_entity_name_and_id_extractor(CompositePKModel)
    assert entity_name == "test_app_compositepkmodel"

# Test ID extraction from various model instances
@pytest.mark.django_db
def test_id_extraction_standard_model(enable_django):
    """Test ID extraction from a standard Django model instance."""
    obj = TestModel.objects.create(name="Standard Model", description="Standard model test")
    _, id_extractor = get_entity_name_and_id_extractor(TestModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.id
    assert isinstance(extracted_id, int)

@pytest.mark.django_db
def test_id_extraction_uuid_model(enable_django):
    """Test ID extraction from a model instance with UUID primary key."""
    obj = UUIDModel.objects.create(name="UUID Model")
    _, id_extractor = get_entity_name_and_id_extractor(UUIDModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.id
    assert isinstance(extracted_id, uuid.UUID)

@pytest.mark.django_db
def test_id_extraction_custom_pk_model(enable_django):
    """Test ID extraction from a model instance with custom PK field name."""
    obj = CustomPKModel.objects.create(name="Custom PK Model")
    _, id_extractor = get_entity_name_and_id_extractor(CustomPKModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.custom_id
    assert isinstance(extracted_id, int)

@pytest.mark.django_db
def test_id_extraction_string_pk_model(enable_django):
    """Test ID extraction from a model instance with string primary key."""
    obj = StringPKModel.objects.create(code="ABC123", name="String PK Model")
    _, id_extractor = get_entity_name_and_id_extractor(StringPKModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.code
    assert extracted_id == "ABC123"
    assert isinstance(extracted_id, str)

@pytest.mark.django_db
def test_id_extraction_composite_pk_model(enable_django):
    """Test ID extraction from a model instance with composite primary key.
    
    Note: Django doesn't truly support composite primary keys, so this actually
    tests that the standard ID is extracted even for models with unique_together.
    """
    obj = CompositePKModel.objects.create(first_id=1, second_id=2, name="Composite PK Model")
    _, id_extractor = get_entity_name_and_id_extractor(CompositePKModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.id  # Django still creates an auto-incrementing id
    assert isinstance(extracted_id, int)


# Test extraction works via pk attribute
@pytest.mark.django_db
def test_id_extraction_via_pk_attribute(enable_django):
    """Verify that the ID extraction works through Django's pk attribute."""
    obj = TestModel.objects.create(name="PK Test", description="Testing pk attribute")

    # Manually verify pk is functioning correctly
    assert obj.pk == obj.id

    # Test that our extractor uses pk
    _, id_extractor = get_entity_name_and_id_extractor(TestModel)
    extracted_id = id_extractor(obj)
    assert extracted_id == obj.pk

# Test caching with Django model
@pytest.mark.django_db
def test_simple_django_caching(enable_django):
    """Test that caching with Django model works correctly."""
    # Create cache
    memory_cache = EntityCache(backend=MemoryBackend(key_prefix="django_test:"), debug=True)

    # Create test object
    test_obj = TestModel.objects.create(
        name="Cache Test Object",
        description="This object will be retrieved via a cached function"
    )

    # Counter to track function calls
    call_count = 0

    # Create cached function using Django model as entity
    @memory_cache(TestModel)
    def get_test_model_by_id(model_id: int) -> Optional[TestModel]:
        nonlocal call_count
        call_count += 1
        try:
            return TestModel.objects.get(id=model_id)
        except TestModel.DoesNotExist:
            return None

    # First call should execute the function
    result = get_test_model_by_id(test_obj.id)
    assert result is not None
    assert result.name == "Cache Test Object"
    assert call_count == 1

    # Second call should use the cache
    result = get_test_model_by_id(test_obj.id)
    assert result is not None
    assert result.name == "Cache Test Object"
    assert call_count == 1  # Still 1, function not called again

    # Different ID should execute the function again
    result = get_test_model_by_id(999)  # Non-existent ID
    assert result is None
    assert call_count == 2  # Incremented because it's a different ID
