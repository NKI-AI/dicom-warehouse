"""
Script to read in user-specific information to database.
"""
import argparse
import os

from dcmw.db import get_database_manager
from dcmw.paths import DATA_DIR
from dcmw.utils.utils_io import get_logger
from dcmw.utils.utils_user_uploads import read_file, validate_model_against_df, write_to_db

logger = get_logger()


def main(db_name: str, file_name: str, table_name: str) -> None:
    """Write data of file {file_name} to table {table_name} in database {db_name}"""

    # Initialize database manager
    database_manager = get_database_manager(db_name)

    # Read data into a dataframe
    file_path = os.path.join(DATA_DIR, file_name)
    df = read_file(file_path)

    # Check if dataframe structure and database model are comparable
    validate_model_against_df(df, table_name, database_manager)

    # Read data into database
    write_to_db(df, database_manager, table_name)

    logger.info(f"Done with exporting data of {file_name} to table {table_name} in database {db_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a user-specific excel or csv file to PostgreSQL")
    parser.add_argument("--db_name", type=str, required=True, help="Name of the database to use.")
    parser.add_argument(
        "--file_name",
        metavar="file_name",
        type=str,
        required=True,
        help="Name of filename, make sure it is stored in {project_root}/data/.",
    )
    parser.add_argument("--table_name", type=str, required=True, help="Name of the new table.")

    args = parser.parse_args()

    if not args.db_name:
        logger.error("No database name was set.")
    if not args.file_name:
        logger.error("No filename was given.")
    if not args.table_name:
        logger.error("No table name was given.")
    else:
        main(args.db_name, args.file_name, args.table_name)
