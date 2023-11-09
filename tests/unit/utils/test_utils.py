import configparser
from datetime import date, datetime
from pathlib import Path

import pytest
from pydicom.dataset import Dataset
from sqlalchemy import Column, Date, Integer, String, Time
from sqlalchemy.orm import declarative_base

from dcmw.utils.utils import (
    add_fields_from_toml,
    db_config,
    get_dicom_value,
    is_pascal_case,
    parse_datetime,
    populate_from_dicom,
    to_snake_case,
)

# Mock CONFIG_DIR for testing
CONFIG_DIR = Path("tests")

Base = declarative_base()


class MockModel(Base):
    __tablename__ = "mock_model"
    id = Column(Integer, primary_key=True)
    user_name = Column(String)
    birth_date = Column(Date)


def test_is_pascal_case():
    # Positive cases
    assert is_pascal_case("PascalCase") == True
    assert is_pascal_case("Pascal") == True
    assert is_pascal_case("PascalCaseExample") == True
    assert is_pascal_case("P") == True  # Single uppercase character

    # Negative cases
    assert is_pascal_case("notPascalCase") == False  # starts with lowercase
    assert is_pascal_case("Pascal_case") == False  # has underscore
    assert is_pascal_case("Pascal-Case") == False  # has hyphen
    assert is_pascal_case("pascalCase") == False  # camelCase
    assert is_pascal_case("") == False  # empty string
    assert is_pascal_case("123Pascal") == False  # starts with a number
    assert is_pascal_case("PascalCase123") == False  # ends with a number


def test_to_snake_case():
    # Test with camelCase strings
    assert to_snake_case("camelCase") == "camel_case"
    assert to_snake_case("someCamelCaseString") == "some_camel_case_string"

    # Test with PascalCase strings
    assert to_snake_case("PascalCase") == "pascal_case"
    assert to_snake_case("SomePascalCaseString") == "some_pascal_case_string"

    # Test with strings that are already in snake_case
    assert to_snake_case("already_snake_case") == "already_snake_case"

    # Test with strings that have consecutive uppercase letters
    assert to_snake_case("HTTPServer") == "http_server"
    assert to_snake_case("findUserID") == "find_user_id"

    # Test with strings that are all uppercase
    assert to_snake_case("HTTP") == "http"

    # Test with strings that are all lowercase
    assert to_snake_case("http") == "http"

    # Test with strings that mix cases and non-alphabetic characters
    assert to_snake_case("User123ID") == "user123_id"

    # Test with empty string
    assert to_snake_case("") == ""


def test_get_dicom_value():

    # Create a sample DICOM dataset
    ds = Dataset()
    ds.PatientName = "John Doe"
    ds.PatientID = "123456"

    # Test retrieving an existing DICOM value
    hex_tags = (0x0010, 0x0010)  # PatientName
    assert get_dicom_value(ds, hex_tags) == "John Doe"

    # Test retrieving another existing DICOM value
    hex_tags = (0x0010, 0x0020)  # PatientID
    assert get_dicom_value(ds, hex_tags) == "123456"

    # Test retrieving a non-existent DICOM value
    hex_tags = (0x0010, 0x0030)  # Date of Birth (not set in our sample)
    assert get_dicom_value(ds, hex_tags) is None

    # Test with invalid hex tags (not part of the standard DICOM tags)
    hex_tags = (0x9999, 0x9999)
    assert get_dicom_value(ds, hex_tags) is None

    # Test with a completely empty dataset
    empty_ds = Dataset()
    hex_tags = (0x0010, 0x0010)
    assert get_dicom_value(empty_ds, hex_tags) is None


def test_add_fields_from_toml():
    # Valid Fields
    fields = [
        {"name": "SomeField", "type": "String", "length": 100},
        {"name": "Age", "type": "Integer", "not_null": True},
    ]
    add_fields_from_toml(MockModel, fields)
    assert hasattr(MockModel, "user_name")
    assert hasattr(MockModel, "age")

    # Field Name not in PascalCase
    with pytest.raises(ValueError):
        fields = [{"name": "some_field", "type": "String"}]
        add_fields_from_toml(MockModel, fields)

    # Unsupported Field Type
    with pytest.raises(ValueError):
        fields = [{"name": "UnsupportedTypeField", "type": "CustomType"}]
        add_fields_from_toml(MockModel, fields)

    # Field already in model
    with pytest.raises(AttributeError):
        fields = [{"name": "UserName", "type": "String", "length": 100}]
        add_fields_from_toml(MockModel, fields)

    # Defaults
    fields = [{"name": "DefaultString", "type": "String"}]
    add_fields_from_toml(MockModel, fields)
    assert isinstance(MockModel.default_string.property.columns[0].type, String)
    assert MockModel.default_string.property.columns[0].nullable


def test_populate_from_dicom():

    # Create a mock DICOM dataset
    ds = Dataset()
    ds.add_new((0x0010, 0x0010), "PN", "John Doe")
    ds.add_new((0x0010, 0x0030), "DA", "19900101")

    # Configuration for mapping
    config = {
        "fields": [
            {"name": "UserName", "hex_tag": (0x0010, 0x0010)},
            {"name": "BirthDate", "hex_tag": (0x0010, 0x0030), "type": "Date"},
        ]
    }

    populated_model = populate_from_dicom(MockModel, ds, config)
    assert populated_model.user_name == "John Doe"
    assert populated_model.birth_date == datetime(1990, 1, 1)

    # Unsupported Field Type
    with pytest.raises(ValueError):
        bad_config = {"fields": [{"name": "UnsupportedTypeField", "hex_tag": (0x0010, 0x0010), "type": "CustomType"}]}
        populate_from_dicom(MockModel, ds, bad_config)

    # Missing Field in DICOM
    missing_field_config = {"fields": [{"name": "MissingField", "hex_tag": (0x0010, 0x0040)}]}
    populated_model_missing_field = populate_from_dicom(MockModel, ds, missing_field_config)
    assert getattr(populated_model_missing_field, to_snake_case("MissingField")) is None


def test_parse_datetime():
    # Testing with valid datetime string and parsers
    assert parse_datetime("2023-09-20", ["%Y-%m-%d"]) == datetime(2023, 9, 20)
    assert parse_datetime("20-09-2023", ["%d-%m-%Y"]) == datetime(2023, 9, 20)
    assert parse_datetime("09/20/23 14:55", ["%m/%d/%y %H:%M"]) == datetime(2023, 9, 20, 14, 55)

    # Testing with multiple parsers
    parsers = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%y %H:%M"]
    assert parse_datetime("2023-09-20", parsers) == datetime(2023, 9, 20)
    assert parse_datetime("20-09-2023", parsers) == datetime(2023, 9, 20)
    assert parse_datetime("09/20/23 14:55", parsers) == datetime(2023, 9, 20, 14, 55)

    # Testing whitespace or empty string
    assert parse_datetime(" ", ["%Y-%m-%d"]) is None
    assert parse_datetime("", ["%Y-%m-%d"]) is None

    # Testing with no matching parser
    assert parse_datetime("2023-09-20", ["%H:%M:%S"]) is None

    # Testing invalid date string
    assert parse_datetime("2023-13-40", ["%Y-%m-%d"]) is None  # Invalid month and day
    # TODO: Maybe this test is better as that is what it the function should output, but I like the function to go on
    #  and return None instead of raising errors, as dicom tags can be quite annoying in having
    #  strange stuff in every tag.
    # with pytest.raises(ValueError):
    #     assert parse_datetime("2023-13-40", ["%Y-%m-%d"])  # Invalid month and day
