"""Main file to get modality from MR scans (basically the series description, but better."""

import argparse

from dcmw.db import get_database_manager
from dcmw.modality.modality_extractor import ModalityExtractor
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def main(db_name: str, threads: int = 15, batch_size: int = 45) -> None:
    """
    Extract modalities for studies in the specified database.

    Args:
        db_name (str): Name of the database from which studies are to be processed.
        threads (int, optional): Number of threads to be used for processing. Defaults to 15.
        batch_size (int, optional): Size of batch. Defaults to 45.

    Returns:
        None
    """

    # Initialize database manager
    database_manager = get_database_manager(db_name)

    logger.info(f"Starting extracting modalities for studies in database: {db_name}")

    extractor = ModalityExtractor(database_manager, threads=threads, batch_size=batch_size)
    extractor.extract_modalities()

    logger.info(f"Done with extracting modalities for all studies in database {db_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process DICOM data to PostgreSQL")
    parser.add_argument("--db_name", type=str, required=True, help="Name of the database to use.")
    parser.add_argument("--threads", type=int, default=1, help="Number of threads to use for processing.")
    parser.add_argument("--batch_size", type=int, default=45, help="Size of batch.")

    args = parser.parse_args()

    if not args.db_name:
        logger.error("No database name was set.")
    else:
        main(args.db_name, args.threads, args.batch_size)
