import pytest

from cacheref.idextractor import IdExtractorError, extract_entity_ids


def test_extract_entity_ids_simple_dict():
    """Test extraction from a simple dictionary with default id_key."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result={"id": 1},
        id_key="id",
        supported_id_types=(str, int)
    )
    assert ids == {1}


def test_extract_entity_ids_custom_id_key():
    """Test extraction with a custom id_key."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result={"user_id": 123},
        id_key="user_id",
        supported_id_types=(str, int)
    )
    assert ids == {123}


def test_extract_entity_ids_list_of_dicts():
    """Test extraction from a list of dictionaries."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=[
            {"id": 1},
            {"id": 2},
            {"id": 3}
        ],
        id_key="id",
        supported_id_types=(str, int)
    )
    assert ids == {1, 2, 3}


def test_extract_entity_ids_list_of_flat_values():
    """Test extraction from a list of flat values (integers/strings)."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=[1, 2, 3, 4],
        id_key='id',  # by defeault it is hidden on cache decorator
        supported_id_types=(str, int)
    )
    assert ids == {1, 2, 3, 4}


def test_extract_entity_ids_single_flat_value():
    """Test extraction from a single flat value."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=42,
        id_key='id',  # by default it is hidden on cache decorator
        supported_id_types=(str, int)
    )
    assert ids == {42}


def test_extract_entity_ids_iterable_id_key(caplog):
    """Test extraction using multiple id_keys (iterable id_key)."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result={"user_id": 1, "account_id": 2, "group_id": 3},
        # Only extracts first (Note: compose key not supported for now)
        id_key=["user_id", "account_id"],
        supported_id_types=(str, int)
    )
    assert ids == {1}


def test_extract_entity_ids_object_with_attributes():
    """Test extraction from objects with attributes instead of dict keys."""
    class User:
        def __init__(self, id_):
            self.id = id_

    user = User(id_=99)
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=user,
        id_key="id",
        supported_id_types=(str, int)
    )
    assert ids == {99}


def test_extract_entity_ids_list_of_objects():
    """Test extraction from a list of objects with attributes."""
    class User:
        def __init__(self, id_):
            self.id = id_

    users = [User(id_=1), User(id_=2), User(id_=3)]
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=users,
        id_key="id",
        supported_id_types=(str, int)
    )
    assert ids == {1, 2, 3}


def test_extract_entity_ids_unsupported_id_type(caplog):
    """Test handling of unsupported ID types with log verification."""
    with pytest.raises(IdExtractorError) as e:
        ids = extract_entity_ids(
            source_func=lambda x: x,
            result={"id": [1, 2, 3]},  # List is not in supported_id_types
            id_key="id",
            supported_id_types=(str, int)
        )
        assert ids == set()
    assert "got unsupported ID value" in str(e.value)
    assert "<class 'list'>" in str(e.value)



def test_extract_entity_ids_mixed_types(caplog):
    """Test extraction from mixed supported types."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=[
            {"id": 1},
            {"id": "string-id"},
            {"id": 3}
        ],
        id_key="id",
        supported_id_types=(str, int)
    )
    assert ids == {1, "string-id", 3}
    assert 'IDs have multiple types' in caplog.text


def test_extract_entity_ids_allow_missing_id_key():
    """Test behavior when id_key is missing from some results."""
    ids = extract_entity_ids(
        source_func=lambda x: x,
        result=[
            {"id": 1},
            {"name": "No ID here"},
            {"id": 3}
        ],
        id_key="id",
        supported_id_types=(str, int),
        fail_on_missing_id=False
    )
    assert ids == {1, 3}  # Should only extract existing IDs


def test_extract_entity_ids_forbid_missing_id_key():
    """Test behavior when id_key is missing from some results."""
    with pytest.raises(IdExtractorError) as e:
        extract_entity_ids(
            source_func=lambda x: x,
            result=[
                {"id": 1},
                {"name": "No ID here"},
                {"id": 3}
            ],
            id_key="id",
            supported_id_types=(str, int),
            fail_on_missing_id=True
        )
    assert "Extract ID is \"None\"" in str(e.value)


def test_fail_no_ids_nested_lists():
    """Test extraction from nested lists of dictionaries."""
    with pytest.raises(IdExtractorError) as e:
        extract_entity_ids(
            source_func=lambda x: x,
            result=[
                {"groups": [{"id": 1}, {"id": 2}]},
                {"groups": [{"id": 3}, {"id": 4}]}
            ],
            id_key="groups.id",
            supported_id_types=(str, int)
        )
    assert "Extract ID is \"None\"" in str(e.value)
