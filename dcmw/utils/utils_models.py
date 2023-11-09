from typing import Any, Callable, Dict, List, MutableMapping, Optional, Tuple, Union, Type, Mapping

import toml
from sqlalchemy import Column, Date, Float, Integer, String, Time
from sqlalchemy.types import DECIMAL

from dcmw.models.base_models import WarehouseBase
from dcmw.paths import CONFIG_DIR
from dcmw.utils.utils import is_pascal_case, to_snake_case
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def load_config(config_filename: str = "table_config.toml") -> Dict[str, Any]:
    """
    Load configurations from a TOML file.

    :param config_filename: The name of the configuration file. Default is 'config.toml'.
    :return: A dictionary representing the configuration.
    """
    config_path = CONFIG_DIR / config_filename
    return toml.load(config_path)


def load_config_and_extend_models(models: Mapping[str, Type[WarehouseBase]]) -> None:
    """
    Load configurations from TOML and extend the provided models dynamically.

    :param models: A dictionary mapping class names to their respective SQLAlchemy model classes.
    :raises ValueError: If a class from the configuration is not found in the provided models.
    """
    """Load configurations and extend models dynamically."""
    config = load_config()
    for class_name, config_item in config.items():
        fields = config_item.get("fields", [])
        cls = models.get(class_name)
        if cls:
            # Check if the class has already been extended
            if not hasattr(cls, "_extended"):
                add_fields_from_toml(cls, fields)
                cls._extended = True  # Mark the class as extended
        else:
            error_msg = f"Class {class_name} not found in the current global namespace."
            logger.error(error_msg)
            raise ValueError(error_msg)


# For mapping field types to SQLAlchemy column types
COLUMN_TYPE_MAPPING: Dict[str, Any] = {
    "String": String,
    "Integer": Integer,
    "Time": Time,
    "Date": Date,
    "Float": Float,
    "Decimal": DECIMAL(asdecimal=True),
}


def add_fields_from_toml(cls: Type[WarehouseBase], fields: List[Dict[str, Any]]) -> None:
    """
    Dynamically add fields to an ORM model class based on a provided TOML configuration.

    :param cls: The ORM model class to be extended.
    :param fields: A list of dictionaries containing field configurations.
    :raises ValueError: If the field name is not in PascalCase or if an unsupported field type is encountered.
    :raises AttributeError: If a field with the same name already exists in the class.
    """
    for field in fields:
        field_name = field["name"]
        if not is_pascal_case(field_name):
            error_msg = f"Field name {field_name} is not in PascalCase"
            logger.error(error_msg)
            raise ValueError(error_msg)

        snake_name = to_snake_case(field_name)

        # Check if snake_name is already in cls
        if hasattr(cls, snake_name):
            error_msg = f"Attribute named {snake_name} already exists in the class {cls.__name__}"
            logger.error(error_msg)
            raise AttributeError(error_msg)

        field_type = field.get("type", "String")

        # Check if the field_type is in the mapping
        if field_type not in COLUMN_TYPE_MAPPING:
            error_msg = f"Unsupported field type {field_type} for {field_name}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        column_type = COLUMN_TYPE_MAPPING[field_type]
        if column_type == String:
            column_type = column_type(field.get("length", None))

        setattr(
            cls,
            snake_name,
            Column(column_type, unique=field.get("unique", False), nullable=not field.get("not_null", False)),
        )
