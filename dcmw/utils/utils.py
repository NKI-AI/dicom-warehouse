import configparser
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Type

from pydicom.dataset import Dataset, DataElement
from sqlalchemy import Column, Date, Float, Integer, String, Time, create_engine
from sqlalchemy.types import DECIMAL

from dcmw.models.base_models import WarehouseBase
from dcmw.paths import CONFIG_DIR
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def db_config(db_name: str) -> str:
    """Get database configuration."""
    parser = configparser.ConfigParser()
    config_path = CONFIG_DIR / "database.ini"
    parser.read(config_path)
    return parser[db_name]["database_url"]


def is_pascal_case(s: str) -> bool:
    """Check if a string is in PascalCase."""
    return bool(re.match(r"^[A-Z][a-zA-Z]*([A-Z][a-zA-Z]*)*$", s))


def to_snake_case(s: str) -> str:
    """Convert a string from PascalCase, camelCase, or any mix to snake_case."""
    return re.sub("((?<=[a-z0-9])[A-Z]|(?<!^)[A-Z](?=[a-z]))", r"_\1", s).lower()


def get_dicom_value(dicom_data: Dataset, hex_tag: Tuple[int, int], parent_hex_tag: Optional[Tuple[int, int]]) -> Optional[Any]:
    """Retrieve DICOM value from given tags."""
    if parent_hex_tag:
        parent_tag = (parent_hex_tag[0], parent_hex_tag[1])
        data_element = dicom_data.get(parent_tag)
        # If the parent tag isn't found or isn't a DataElement, return None.
        if data_element and isinstance(data_element, DataElement):
            # Get the nested Dataset.
            try:
                nested_dataset = data_element[0]
            except (TypeError, IndexError, KeyError):
                return None

            # Now, retrieve the desired tag from this nested dataset.
            tag = (hex_tag[0], hex_tag[1])
            nested_data_element = nested_dataset.get(tag)
            if nested_data_element:
                return nested_data_element.value

    tag = (hex_tag[0], hex_tag[1])
    data_element = dicom_data.get(tag)
    return data_element.value if data_element else None


# Define parsers for Date and Time
DATETIME_PARSERS = {"Date": ["%Y%m%d"], "Time": ["%H%M%S", "%H%M%S.%f"]}


def parse_datetime(value: str, parsers: List[str]) -> Optional[datetime]:
    """Parse a string into a datetime object using provided formats."""
    if not value.strip():
        return None

    for parser in parsers:
        try:
            return datetime.strptime(value.strip(), parser)
        except ValueError:
            continue

    return None

def time_converter(v: Any) -> Optional[time]:
    parsed = parse_datetime(v, DATETIME_PARSERS["Time"])
    return parsed.time() if parsed else None

def date_converter(v: Any) -> Optional[date]:
    parsed = parse_datetime(v, DATETIME_PARSERS["Date"])
    return parsed.date() if parsed else None

# Mapping types to their respective conversion functions
TYPE_CONVERSION_MAPPING: Dict[str, Callable[[Any], Any]] = {
    "String": str,
    "Integer": int,
    "Time": time_converter,
    "Date": date_converter,
    "Float": float,
    "Decimal": float,  # You've used float(value) for the 'Decimal' type in the original code
}


def populate_from_dicom(model_cls: Type[WarehouseBase], dicom_data: Dataset, config: Dict[str, Any]) -> WarehouseBase:
    """
    Populate an ORM model instance using data extracted from a DICOM dataset.

    This function reads the DICOM data, retrieves values based on tags specified in the config,
    applies type conversions if necessary, and sets the values to the corresponding attributes of the model instance.

    :param model_cls: The SQLAlchemy model class that needs to be populated.
    :param dicom_data: The DICOM dataset containing the relevant data.
    :param config: A dictionary specifying fields and their corresponding DICOM hex tags and data types.
                   Example:
                   {
                       "fields": [
                           {"name": "PatientName", "hex_tag": "0x00100010", "type": "String"},
                           ...
                       ]
                   }
    :return: An instance of the model populated with data from the DICOM dataset.
    :raises ValueError: If an unsupported field type is encountered.
    """
    instance = model_cls()
    fields = config.get("fields", [])

    for field in fields:
        field_name = field["name"]
        hex_tag = field["hex_tag"]
        field_type = field.get("type", "String")
        snake_field_name = to_snake_case(field_name)

        # Check if there's a parent tag and convert it similarly to hex_tag.
        parent_hex_tag = None
        if "parent_tag" in field:
            parent_hex_tag = field["parent_tag"]

        value = get_dicom_value(dicom_data, hex_tag, parent_hex_tag)

        if value == "":  # DICOM might have empty strings for certain fields.
            value = None

        if value:
            if field_type in TYPE_CONVERSION_MAPPING:
                try:
                    value = TYPE_CONVERSION_MAPPING[field_type](value)
                except TypeError:
                    # TODO: IDK what to do about cases which SHOULD be a certain type, but dicom just stored it as a different type of value.
                    #  Now just say, those values are None.
                    value = None
            else:
                error_msg = f"Unsupported field type '{field_type}' for field '{field_name}'."
                logger.error(error_msg)
                raise ValueError(error_msg)

        setattr(instance, snake_field_name, value)

    return instance


def extract_value_from_mapping(known_key: str, mapping: Dict[Any, Any]) -> Any:
    """
    Extract a value from a given dictionary based on a provided key.

    :param known_key: The key whose associated value needs to be fetched.
    :param mapping: Dictionary containing key-value pairs.
    :return: Value associated with the provided key.
    :raises ValueError: If the provided key is not found in the dictionary.
    """
    for key, value in mapping.items():
        if key == known_key:
            return value
    error_msg = f"Given key '{known_key}' not found in mapping."
    logger.error(error_msg)
    raise ValueError(error_msg)


def time_difference(t1: time, t2: time) -> timedelta:
    """Computes time difference between two datetime.time objects. Apparently datetime can only
    subtract datetime.datetime values"""
    today = date.today()
    dt1 = datetime.combine(today, t1)
    dt2 = datetime.combine(today, t2)
    return dt2 - dt1


# TODO:
# Some remarks:
# PatientAge is of course an integer, but can be string like: '040Y', so chosen to do string
