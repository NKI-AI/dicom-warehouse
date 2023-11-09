from typing import Any, List, Optional, Dict, Union, Tuple, Sequence
from collections import Counter

from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils_io import get_logger

logger = get_logger()

def get_attribute_value(model_instance: WarehouseBase, attribute_name: str) -> Any:
    """
    Retrieves the value of the specified attribute from the given SQLAlchemy model instance.

    :param model_instance: An instance of an SQLAlchemy model.
    :param attribute_name: The name of the attribute to retrieve.
    :return: The value of the attribute if it exists, else None.
    """
    return getattr(model_instance, attribute_name, None)


def extract_tag_counter(model_list: List[WarehouseBase], tag_name: str) -> Optional[Any]:
    """
    Different DICOM files in one model can sometimes have different values for the same tag,
    even if these are supposed to be the same (e.g., some tags are not filled in at all in all files).
    This function gets all values of the same tags, excluding None values, and returns the most common value.

    :param model_list: List of SQLAlchemy model instances.
    :param tag_name: The name of the attribute/tag to retrieve from each model instance.
    :return: The most common value for the specified tag, or None if no common value found.
    """
    tag_list = [get_attribute_value(m, tag_name) for m in model_list]
    tag_value: List[Tuple[Any, int]] = Counter(filter(None, tag_list)).most_common(1)
    return tag_value[0][0] if tag_value else None


def count_tag_values(model_list: Sequence[WarehouseBase], tag_name: str) -> Dict[Any, int]:
    """
    Counts the presence of all unique values in a certain tag.

    :param model_list: List of SQLAlchemy model instances.
    :param tag_name: The name of the attribute/tag to retrieve from each model instance.
    :return: Dictionary with keys being the unique values of the tag and values being their respective counts.
    """
    tag_list = [get_attribute_value(m, tag_name) for m in model_list]
    tag_values: Dict[Any, int] = Counter(filter(None, tag_list))
    return tag_values


def extract_tag_values(model_list: List[WarehouseBase], tag_name: str) -> List[Any]:
    """
    Extract all unique values for a specified tag from a list of models.

    :param model_list: List of SQLAlchemy model instances.
    :param tag_name: The name of the attribute/tag to retrieve from each model instance.
    :return: List of unique tag values.
    """
    tag_list = [get_attribute_value(m, tag_name) for m in model_list]
    tag_values = [v for v in set(tag_list) if v is not None]
    return tag_values


def extract_tag(model_list: Sequence[WarehouseBase], tag_name: str, multiple: bool = False) -> Union[Any, List[Any], str]:
    """
    Extract unique values for a specified tag. If multiple=True, returns all unique values; otherwise,
    ensures only one unique value exists and returns it.

    :param model_list: List of SQLAlchemy model instances.
    :param tag_name: The name of the attribute/tag to retrieve from each model instance.
    :param multiple: Flag indicating if multiple unique tag values should be returned.
    :return: A single unique value if multiple is False, else a list of all unique values.
    """
    tag_list = [get_attribute_value(m, tag_name) for m in model_list]
    tag_values = [v for v in set(tag_list) if v is not None]
    if multiple:
        return tag_values
    if len(tag_values) != 1:
        error_msg = f"No, or more than 1, value for {tag_name}: {tag_values}"
        logger.error(error_msg)
        # TODO: Should return Undetermined (modality) with reason: {critical_parameter} failure: None / multiple values while singularity constraint.
        # TODO: for now, just go with the first value.. Need to investigate whether this still holds or is now fixed in a different way.
        # raise ValueError(error_msg)
    return tag_values[0]