import logging
from typing import Any, Callable, Tuple, Type, TypeVar, Union

T = TypeVar('T')
KeyType = Union[str, int]
IdExtractorType = Union[str, Callable[[Any], KeyType], Tuple[str, Callable[[Any], KeyType]]]


logger = logging.getLogger("cacheref")


def extractor_trace(extractor: IdExtractorType, extractor_index: int) -> str:
    """Format an extractor for logging."""
    return f"extractor[{extractor_index+1}] = '{extractor}' ({type(extractor)})"


class IdExtractorError(Exception):
    """Exception raised when ID extraction fails."""

    def __init__(self, item, extractor, message=None):
        self.item = item
        self.extractor = extractor
        self.message = message or f"Failed to extract ID using {extractor}"
        super().__init__(self.message)

def item_error(source_func: Callable, item: Any, extractor: IdExtractorType):
    return IdExtractorError(
        item=item,
        extractor=extractor,
        message=f"Error extracting ID for item {item}, id field: {extractor} in {source_func.__name__}"
    )


def extract_entity_ids(source_func: Callable, result: Any,  id_key: IdExtractorType,
                       supported_id_types: Tuple = (str, int),
                       fail_on_missing_id: bool = True):
    """
    Extract entity IDs from the result in various formats.

    Args:
        source_func: The function that produced the result for logging context
        result: The data to extract IDs from
        id_key: The field name containing the ID (default: 'id'),
                    can be a string key, a callable, or a tuple of both
        supported_id_types: The supported primitve ID types to extract from
        fail_on_missing_id: Raise an error if an ID is missing or None
        root_key: The root key for the result data (used for logging)
    """
    extractor_list: Tuple[Union[str, Callable[[Any], KeyType]]] = tuple()
    if isinstance(id_key, (list, tuple)):
        extractor_list = tuple(id_key)
    else:
        extractor_list = (id_key,)


    ids = set()

    try:
        if callable(result):
            raise ValueError(f"Failed to extract IDs, {source_func.__name__}  {result=} \
                                is a callable, please provide a valid result")
        if isinstance(result, (list, tuple)):
            # Handle list of objects
            for item in result:
                extracted_id = _first_result_from_extractors(item, source_func, supported_id_types, extractor_list,
                                                             fail_on_missing_id)
                if extracted_id is not None:
                    ids.add(extracted_id)
        else:
            # Handle single object
            extracted_id = _first_result_from_extractors(result, source_func, supported_id_types, extractor_list,
                                                         fail_on_missing_id)
            if extracted_id is not None:
                ids.add(extracted_id)

    except IdExtractorError:
        # Re-raise specific extractor errors without modification
        raise
    except Exception as e:
        # Handle general errors with appropriate context
        raise IdExtractorError(
            item=result,  # Using result instead of undefined 'item'
            extractor=id_key,
            message=f"Error extracting IDs from {source_func.__name__}: \n{e}"
        ) from e
    ref_types = set(type(id_) for id_ in ids)
    if len(ref_types) > 1:
        logger.warning(f"❗ Extracted IDs have multiple types: {ref_types} in {source_func.__name__}")
    return ids

def _parse_item_id(source_func: Callable, item: Any, supported_id_types: Tuple[Type], extractor: IdExtractorType):
    """This function will try to extract id from entity"""
    if callable(extractor):
        try:
            return extractor(item)
        except Exception as e:
            raise item_error(source_func, item, extractor=extractor) from e
    elif isinstance(extractor, str):
        logger.debug(f"Extracting ID from {item} using {extractor=} {supported_id_types=}")
        # handle dict
        if isinstance(item, dict):
            return item.get(extractor)
        # or object with attribute
        if hasattr(item, extractor):
            return getattr(item, extractor)
        # or flat primitive value
        # if isinstance(item, supported_id_types):
        return item

    else:
        raise ValueError(f"Unsupported id_key extractor type {type(extractor)} in {source_func.__name__}, \
                            provide either callable or str as field for key")

def _first_result_from_extractors(item: Any, source_func: Callable, supported_id_types: Tuple[Type],
                                  extractor_list: Tuple[Union[str, Callable[[Any], KeyType]]],
                                  fail_on_missing_id: bool = True):
    """This function will try to extract any first id from entity/item in order of extractors"""
    for i, extractor in enumerate(extractor_list):
        logger.debug(f'Using key_id {extractor} type={type(extractor)} for {item=}')
        try:
            extracted_id = _parse_item_id(source_func, item, supported_id_types, extractor)
            if extracted_id is None:
                if fail_on_missing_id:
                    raise ValueError(f"Extract ID is \"None\" from {item}"\
                                     f" using {extractor_trace(extractor, i)} in {source_func.__name__}")
                else:
                    logger.debug("Skipping missing or None extracted_id "\
                                 f"as fail_on_missing_id=True from {item} using"\
                                  " {extractor_trace(extractor, i)} in {source_func.__name__}")
                    continue
            if isinstance(extracted_id, supported_id_types):
                return extracted_id
            else:
                # non supported ID type
                raise ValueError(
                    f"{extracted_id=} got unsupported ID value {type(extracted_id)} "\
                    f"for item {item} in {source_func.__name__}. \nTried {extractor_trace(extractor, i)} "\
                    f"\nGiven supported_id_types: {supported_id_types}."
                )
        except IdExtractorError:
            logging.debug(f'Skipping failed extractor {extractor} for item {item}', exc_info=True)
    # could not extract id from *any* extractor
    if fail_on_missing_id:

        raise item_error(source_func, item, extractor_list)

    return None
