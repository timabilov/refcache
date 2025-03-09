"""
ORM integration for cacheref.

This module provides optional integrations with SQLAlchemy and Django ORM models,
allowing EntityCache to use them directly.
"""

import logging
from typing import Any, Callable, Tuple, Type

logger = logging.getLogger("cacheref")


def get_entity_name_and_id_extractor(model_class: Type) -> Tuple[str, Callable]:
    """
    Extract entity name and ID extractor function from an ORM model class.
    
    This function detects whether the provided class is a SQLAlchemy or Django model,
    and returns appropriate entity name and ID extractor.
    
    Args:
        model_class: A SQLAlchemy or Django model class
        
    Returns:
        A tuple of (entity_name, id_extractor_function)
        
    Raises:
        ValueError: If the class is not recognized as an ORM model
    """
    # First, check if it has SQLAlchemy-specific attributes
    has_sqlalchemy_attrs = (hasattr(model_class, '__table__') or
                           hasattr(model_class, '__tablename__'))

    # Then check if it has Django-specific attributes
    has_django_attrs = (hasattr(model_class, '_meta') and
                       hasattr(getattr(model_class, '_meta', None), 'app_label'))

    # Now try to process based on detected attributes
    if has_sqlalchemy_attrs:
        try:
            # If it looks like SQLAlchemy, try to use SQLAlchemy
            import sqlalchemy
            return _get_sqlalchemy_info(model_class)
        except ImportError:
            # It looks like SQLAlchemy but SQLAlchemy isn't installed
            raise ValueError(
                f"Class {model_class.__name__} appears to be a SQLAlchemy model, "
                "but SQLAlchemy is not installed. Please install it with: pip install sqlalchemy"
            )

    if has_django_attrs:
        try:
            # If it looks like Django, try to use Django
            import django
            return _get_django_info(model_class)
        except ImportError:
            # It looks like Django but Django isn't installed
            raise ValueError(
                f"Class {model_class.__name__} appears to be a Django model, "
                "but Django is not installed. Please install it with: pip install django"
            )

    # If we get here, it doesn't look like either ORM
    raise ValueError(
        f"Class {model_class.__name__} is not recognized as a SQLAlchemy or Django model. "
        "Please ensure you're passing a valid model class."
    )


# --- SQLAlchemy Integration ---

def _get_sqlalchemy_info(model_class: Type) -> Tuple[str, Callable]:
    """Get entity name and ID extractor for a SQLAlchemy model."""
    # Extract table name for entity name
    if hasattr(model_class, '__table__'):
        entity_name = model_class.__table__.name
    elif hasattr(model_class, '__tablename__'):
        entity_name = model_class.__tablename__
    else:
        # Fallback to class name in lowercase
        entity_name = model_class.__name__.lower()

    return entity_name, _extract_sqlalchemy_pk


def _extract_sqlalchemy_pk(obj: Any) -> Any:
    """Extract primary key from a SQLAlchemy model instance."""
    # Get primary key columns
    if hasattr(obj, '__table__'):
        pk_columns = [c.name for c in obj.__table__.primary_key.columns]

        if not pk_columns:
            raise ValueError(f"Model {obj.__class__.__name__} has no primary key")

        # Get the first primary key column
        pk_name = pk_columns[0]

        # Get the value of this column from the object
        if hasattr(obj, pk_name):
            return getattr(obj, pk_name)

    # Fallback to 'id' attribute which is common
    if hasattr(obj, 'id'):
        return obj.id

    # If we get here, we couldn't extract the ID
    raise ValueError(f"Could not extract primary key from {obj.__class__.__name__} instance")


# --- Django Integration ---

def _get_django_info(model_class: Type) -> Tuple[str, Callable]:
    """Get entity name and ID extractor for a Django model."""
    # Get table name from model's _meta
    entity_name = model_class._meta.db_table

    return entity_name, _extract_django_pk


def _extract_django_pk(obj: Any) -> Any:
    """Extract primary key from a Django model instance."""
    # Django models always have 'pk' attribute for primary key
    if hasattr(obj, 'pk'):
        return obj.pk

    # If we get here, we couldn't extract the ID
    raise ValueError(f"Could not extract primary key from {obj.__class__.__name__} instance")
