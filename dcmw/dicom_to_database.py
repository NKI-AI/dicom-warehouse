"""Main file to read DICOM tags into a database."""

import argparse
from typing import List

from dcmw.db import get_database_manager
from dcmw.dcm_to_db.dicom_importer import DICOMFilesImporter
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def main(dirs: List[str], db_name: str, threads: int = 15, batch_size: int = 45) -> None:
    """Main function to process DICOM data into the database."""

    # Initialize database manager
    database_manager = get_database_manager(db_name)

    # Create db if it does not exist
    database_manager.create_database_if_not_exists()

    logger.info(f"Starting reading DICOM files from directories: {dirs}")

    for d in dirs:
        importer = DICOMFilesImporter(d, database_manager, threads=threads, batch_size=batch_size)
        importer.process_folder()

    logger.info(f"Done with reading all DICOM files from {dirs} into database {db_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process DICOM data to PostgreSQL",
                                     fromfile_prefix_chars='@')
    parser.add_argument(
        "--dirs",
        metavar="list_of_dirs",
        type=str,
        nargs="+",
        required=True,
        help="List of directories containing DICOM files.",
    )
    parser.add_argument("--db_name", type=str, required=True, help="Name of the database to use.")
    parser.add_argument("--threads", type=int, default=1, help="Number of threads to use for processing.")
    parser.add_argument("--batch_size", type=int, default=100, help="Batch size.")

    args = parser.parse_args()

    if not args.db_name:
        logger.error("No database name was set.")
    else:
        main(args.dirs, args.db_name, args.threads, args.batch_size)
