import logging
import os

import pandas as pd

# Suppress logs from NumExpr
logging.getLogger("numexpr").setLevel(logging.ERROR)
# TODO: this suppression doesn't work, probaly because I made my own logger. Needs fixing.

# Ignore future warnings of iteritems
import warnings

# Ignore FutureWarning
warnings.simplefilter(action="ignore", category=FutureWarning)


from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.relationships import RelationshipProperty
from typing import Type, List, Type, Dict, Any, cast

import dcmw.models.user_specific_models as user_models
from dcmw.db import DatabaseManager
from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils import to_snake_case
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def get_model_class_by_tablename(table_name: str) -> Type[WarehouseBase]:
    """Retrieve a SQLAlchemy model class based on its table name."""
    # Loop over all attributes in the user_models module
    for attr_name in dir(user_models):
        attr = getattr(user_models, attr_name)

        # Check if this attribute is a SQLAlchemy model class
        if hasattr(attr, "__tablename__") and attr.__tablename__ == table_name:
            return cast(Type[WarehouseBase], attr)

    message = f"No model found with table name {table_name}"
    logger.error(message)
    raise ValueError(message)


def read_file(file_path: str) -> pd.DataFrame:
    """
    Reads a file into a pandas DataFrame. Detects whether to use read_csv or read_excel based on file extension.

    Args:
    - file_path (str): Path to the file.

    Returns:
    - pd.DataFrame: Data from the file as a DataFrame.
    """

    _, file_extension = os.path.splitext(file_path)

    if file_extension in [".csv"]:
        return pd.read_csv(file_path)
    elif file_extension in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)
    else:
        message = f"Unsupported file extension: {file_extension}"
        logger.error(message)
        raise ValueError(message)


def validate_model_against_df(df: pd.DataFrame, table_name: str, db_manager: DatabaseManager) -> None:
    """
    Validates if the given DataFrame df matches with the SQLAlchemy model with table name table_name.

    Args:
    - df (pd.DataFrame): Input data.
    - table_name (str): Name of the table in the database.
    - db_manager: The database manager to interact with the database.

    Raises:
    - ValueError: If the table doesn't exist or if there's a mismatch between df and the table.
    """
    session = db_manager.create_session()

    # Check if table exists in the database
    assert session.bind is not None
    if not inspect(session.bind).has_table(table_name):
        message = (
            f"The table '{table_name}' does not exist in the database.\n"
            f"Add this model to models.user_specific_models.py and migrate.\n"
            f"Please don't forget to also add foreign keys to other models if added! "
            f"An example of a new model and its foreign keys can be found "
            f"in models.user_specific_models.py."
        )
        logger.error(message)
        raise ValueError(message)

    # Get the model columns
    inspector = inspect(session.bind)
    model_columns = [column["name"] for column in inspector.get_columns(table_name)]

    # Get the df columns
    df_columns = df.columns.tolist()
    df_columns_snake_name = [to_snake_case(column_name) for column_name in df_columns]
    df_columns_final = df_columns_snake_name + ["id", "created", "last_updated"]

    # In case there is an additional id-field:
    model_class = get_model_class_by_tablename(table_name)
    rel_dict = relationship_columns(model_class)
    if "foreign_key_class_column" in rel_dict.keys():
        df_columns_final.append(rel_dict["foreign_key_class_column"])

    # Compare columns
    if set(model_columns) != set(df_columns_final):
        missing_in_df = set(model_columns) - set(df_columns_final)
        missing_in_model = set(df_columns_final) - set(model_columns)

        error_message = "Mismatch between DataFrame and the model:\n"
        if missing_in_df:
            error_message += f"Columns present in the model but missing in DataFrame: {', '.join(missing_in_df)}\n"
        if missing_in_model:
            error_message += f"Columns present in DataFrame but missing in the model: {', '.join(missing_in_model)}"
        error_message += (
            f"Recommended to have another look at your defined models in models.user_specific_models.py,"
            f"and don't forget to run the corresponding migration!\n"
            f"NB: Column names are automatically converted to snake case.\n"
            f"Please don't forget to also add foreign keys to other models if added! "
            f"An example of a new model and its foreign keys can be found "
            f"in models.user_specific_models.py."
        )
        logger.error(error_message)
        raise ValueError(error_message)

    print(f"The DataFrame matches the model for table '{table_name}'.")


def get_unique_columns_for_model(model_class: Type[WarehouseBase]) -> List[str]:
    """
    Get the columns with unique constraints for a given model.

    Parameters:
    - model_class: The SQLAlchemy model class.

    Returns:
    - List of column names with unique constraints.
    """
    unique_columns = []
    for column in model_class.__table__.columns:
        if column.unique:
            unique_columns.append(column.name)
    return unique_columns


def relationship_columns(model_class: Type[WarehouseBase]) -> Dict[str, Any]:
    """Check if there is a relationship column"""
    # Check if the model has relationships
    relationships = [
        rel
        for rel, value in vars(model_class).items()
        if isinstance(value, InstrumentedAttribute) and isinstance(value.property, RelationshipProperty)
    ]
    if len(relationships) > 1:
        error_message = "More than 1 relationship. Currently not supported."
        logger.error(error_message)
        raise ValueError(error_message)
    if len(relationships) == 1 and not all(k in model_class.mapping_info for k in ["foreign_column", "class_column"]): # type: ignore
        error_message = (
            "No mapping information. Please add mapping info to your new table. (Which column in your new"
            " table needs to be mapped to an already existing table in the database?)"
        )
        logger.error(error_message)
        raise ValueError(error_message)

    relationship_dict = {}
    for rel in relationships:
        # Obtain the relationship class, the foreign key, and the backref
        relationship_class = getattr(model_class, rel).property.mapper.class_
        foreign_key_foreign_column = list(list(getattr(model_class, rel).property.local_columns)[0].foreign_keys)[
            0
        ].column.name
        back_populates_field = getattr(model_class, rel).property.back_populates
        foreign_key_class_column = list(getattr(model_class, rel).property.local_columns)[0].name
        relationship_dict = {
            "relationship_class": relationship_class,
            "foreign_key_foreign_column": foreign_key_foreign_column,
            "back_populates_field": back_populates_field,
            "foreign_key_class_column": foreign_key_class_column,
        }
    return relationship_dict


def upsert_data(df: pd.DataFrame, model_class: Type[WarehouseBase], session: Session) -> None:
    """
    Upsert the data from the dataframe into the database based on unique columns.

    Parameters:
    - df: The dataframe containing the data.
    - model_class: The SQLAlchemy model class for the table.
    - session: The SQLAlchemy session object.
    """

    unique_columns = get_unique_columns_for_model(model_class)

    if not unique_columns:
        error_message = f"No unique columns found for {model_class.__name__}. Cannot perform upsert."
        logger.error(error_message)
        raise ValueError(error_message)

    # For simplicity, use the first unique column (except the primary id key, oh apparently has no unique constraint:O).
    # Note: If there are multiple unique constraints (not compound), this could be adjusted.
    unique_column = unique_columns[0]

    try:
        # Find relationships and foreign keys info
        rel_dict = relationship_columns(model_class)

        # Iterate through each row in the dataframe
        for index, row in df.iterrows():
            # Convert the row into a dictionary
            row_dict = row.to_dict()

            if "relationship_class" in rel_dict.keys():
                # Find relational info.
                related_instance = (
                    session.query(rel_dict["relationship_class"])
                    .filter(
                        getattr(rel_dict["relationship_class"], model_class.mapping_info["foreign_column"]) # type: ignore
                        == row_dict[model_class.mapping_info["class_column"]] # type: ignore
                    )
                    .one_or_none()
                )
                if not related_instance:
                    error_message = (
                        f"Could not find {row_dict[model_class.mapping_info['class_column']]} " # type: ignore
                        f"in column {model_class.mapping_info['foreign_column']} " # type: ignore
                        f"of table {rel_dict['relationship_class']}."
                    )
                    logger.error(error_message)
                    raise ValueError(error_message)
                # set relational info in insert row
                row_dict[rel_dict["foreign_key_class_column"]] = getattr(
                    related_instance, rel_dict["foreign_key_foreign_column"]
                )

            # Check if an instance with the same unique column value exists
            instance = (
                session.query(model_class)
                .filter(getattr(model_class, unique_column) == row_dict[unique_column])
                .one_or_none()
            )

            if instance:
                # If instance exists, update it with row's values
                for key, value in row_dict.items():
                    setattr(instance, key, value)
            else:
                # If instance doesn't exist, create a new one and add to the session
                instance = model_class(**row_dict)
                session.add(instance)

        # Commit the changes
        session.commit()

    except IntegrityError:
        # Handle database integrity errors, possibly caused by unique constraint violations other than the column we checked.
        session.rollback()
        error_message = "Database integrity error during upsert. Maybe due to violation of a unique constraint."
        logger.error(error_message)
        raise ValueError(error_message)
    except SQLAlchemyError:
        # Handle general SQLAlchemy errors.
        session.rollback()
        error_message = "General database error during upsert."
        logger.error(error_message)
        raise ValueError(error_message)


def write_to_db(df: pd.DataFrame, db_manager: DatabaseManager, table_name: str) -> None:
    """
    Write data from the dataframe into the database.

    Parameters:
    - df: The dataframe containing the data.
    - db_manager: The database manager class, used to start a session with the database.
    - table_name: The name of the table to which data needs to be added.
    """
    session = db_manager.create_session()
    model_class = get_model_class_by_tablename(table_name)
    try:
        upsert_data(df, model_class, session)
    finally:
        session.close()
