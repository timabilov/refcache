

import inspect
from typing import Sequence


def validate_non_collection_class(cls, param_name="parameter"):
    """
    Validates that the provided class is not a collection type (except strings).
    Raises TypeError if validation fails.
    """
    if not inspect.isclass(cls):
        raise TypeError(f"{param_name} must be a class, got {type(cls).__name__}")

    # Allow string classes but reject other sequence types
    if issubclass(cls, Sequence) and not issubclass(cls, (str, bytes)):
        raise TypeError(f"{param_name} cannot be a collection class like list or tuple, given: {cls.__name__}")

    return True
