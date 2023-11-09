import os
import time
from multiprocessing import Pool
from typing import Any, Iterator, List, Tuple

import pydicom

from dcmw.db import DatabaseManager
from dcmw.dcm_to_db.insert_dicom import process_one_dicom_file
from dcmw.utils.utils_io import get_logger

# Set pydicom configuration
pydicom.config.IGNORE = 1

logger = get_logger()

class DICOMFilesImporter:
    """
    A reader class for processing and storing DICOM files from a given directory into a specified database.

    Attributes:
    - dicom_dir (str): The directory containing DICOM files to be read.
    - database_url (str): The URL for the database where DICOM data will be stored.
    - threads (int): Number of worker threads for parallel processing. Defaults to 15.
    - batch_size (int): Number of series to be processed in a single batch. Defaults to 30.

    Methods:
    - read_folder: Initiates the reading process for DICOM files and stores them in the database.
    """

    def __init__(self, dicom_dir: str, db_manager: DatabaseManager, threads: int = 15, batch_size: int = 15) -> None:
        self.dicom_dir = dicom_dir
        self.db_manager = db_manager
        self.threads = threads
        self.batch_size = batch_size if batch_size >= threads else threads
        self.t = 0.0
        self.current_batch = 0

    def process_folder(self) -> None:
        """
        Process the DICOM files using either single threaded or multi-threaded approach based on the number of threads.

        If threads is set to 1, uses a single-threaded approach. Otherwise, uses a multi-threaded approach.
        """
        self.t = time.time()
        if self.threads == 1:
            logger.info("Using a single thread.")
            self._process_dirs_single_threaded()
        else:
            logger.info(f"Using {self.threads} threads.")
            self._process_dirs_multi_threaded()
        logger.info(f"Done scanning directory {self.dicom_dir}.")

    def _log_progress(self) -> None:
        """
        Logs the progress of processing.
        """
        # TODO: this is not actually true: batch can be smaller if there is not more data in folders.
        #  So we need to account for that in some way, maybe by returning something if a series/folder is completely done?
        elapsed_time = time.time() - self.t
        logger.info(
            f"Batch {self.current_batch} with a size of {self.batch_size} series (folders) done in {elapsed_time:.2f} seconds."
        )
        self.t = time.time()

    def _process_dirs_single_threaded(self) -> None:
        """
        Process directories containing DICOM files in a single-threaded manner.
        """
        for args in self._find_files_batch():
            for arg in args:
                self._process_dir(arg)
            self._log_progress()

    def _process_dirs_multi_threaded(self) -> None:
        """
        Process directories containing DICOM files using multiple threads.
        """
        pool = Pool(processes=self.threads)
        for args in self._find_files_batch():
            pool.map(func=self._process_dir, iterable=args)
            self._log_progress()

        pool.close()
        pool.join()

    def _process_dir(self, args: Tuple[str, List[str]], debug: bool = True) -> None:
        """
        Processes and stores a series of DICOM files located in the specified directory into the database.

        Args:
        - args (Tuple[str, List[str]]): A tuple containing the directory path and a list of file names within that directory.

        Returns:
        - bool: True if the DICOM data is successfully read, otherwise None.

        Raises:
        - Exception: Propagates any exception that occurs during the processing and reading of DICOM files.

        Note:
        This method initiates a new database session for each series to ensure data integrity
        and to handle any potential errors during the processing of individual DICOM files.
        """
        session = self.db_manager.create_session()

        dir_path, file_names = args
        try:
            for file_name in file_names:
                file_path = os.path.join(dir_path, file_name)
                process_one_dicom_file(file_path, session, debug=False)
        except Exception as e:
            session.rollback()
            logger.error(f"Error processing directory: {dir_path}. \n" f"Error in file: {file_name}. \n" f"Error: {e}")
            # TODO: To raise or not to raise? For debug purposes, it is now set to raise.
            if debug:
                raise
        finally:
            session.close()

    def _find_files_batch(self) -> Iterator[List[Tuple[str, List[str]]]]:
        """
        Yields batches of series directories containing DICOM files.

        This iterator function walks through the DICOM directory and identifies last-child directories
        that contain only DICOM files. It then groups these directories into batches of a specified size
        (based on the batch_size attribute) and yields each batch for processing.

        Returns:
        - Iterator[List[Tuple[str, List[str]]]]: An iterator that yields batches of directories and their associated DICOM files.

        Note:
        The method utilizes an internal count mechanism for testing purposes which limits the number of batches yielded.
        This behavior is temporary and should be removed in production.
        """
        batch = []

        for root, _, files in os.walk(self.dicom_dir):
            # dcm_files = [f for f in files if not f.startswith(".") and f.lower().endswith(".dcm")]
            # TODO: above line cannot work for some sets, as sometimes dicom files don't end with .dcm.
            #  In these cases, we actually need to write a function which does:
            #  Detecting DICOM files without relying on their file extension can be a bit tricky.
            #  Typically, DICOM files start with a specific 128-byte preamble followed by "DICM".
            #  This can be used to determine if a file is a DICOM file.
            #  However, this takes significantly longer right? So for now stick with line below, however,
            #  we need to think about this in the future.
            dcm_files = [f for f in files if not f.startswith(".")]
            if files:
                batch.append((root, dcm_files))

                if len(batch) >= self.batch_size:
                    self.current_batch += 1
                    yield batch
                    batch = []

        if batch:
            yield batch
