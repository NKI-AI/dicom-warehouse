import time
import traceback
from multiprocessing import Process, Queue
from typing import List
from sqlalchemy.orm import Session

from dcmw.db import DatabaseManager
from dcmw.modality.protocol_determiner import process_modalities
from dcmw.modality.vendor_strategies import ModalityStrategyFactory
from dcmw.models.dicom_models import Study, Series
from dcmw.utils.utils_extraction import extract_tag
from dcmw.utils.utils_io import get_logger

logger = get_logger()


class ModalityExtractor:
    """
    An extractor class to determine the modality of each series in the provided studies and save them into a specified
    database.

    Attributes:
    - database_url (str): The URL for the database where modalities will be stored.
    - threads (int): Number of worker threads for parallel processing. Defaults to 15.
    - batch_size (int): Number of studies to be processed in a single batch. Defaults to 5.
    - queue (Queue): A queue for multiprocessing where studies will be put and processed.
    - studies (List[Study]): A list of studies that will be processed.

    Methods:
    - extract_modalities: Initiates the modality extraction process for all provided studies.
    """

    def __init__(self, db_manager: DatabaseManager, threads: int = 15, batch_size: int = 45) -> None:
        self.db_manager = db_manager
        self.threads = threads
        self.queue: Queue[Study] = Queue()
        self.studies = self._get_studies()
        self.batch_size = batch_size if batch_size >= threads else threads
        self.current_batch = 0
        self.t = 0.0

    def extract_modalities(self) -> None:
        """
        Extract the modalities per series using either single threaded or multi-threaded approach based on the number of threads.

        If threads is set to 1, uses a single-threaded approach. Otherwise, uses a multi-threaded approach.
        """
        self.t = time.time()
        if self.threads == 1:
            self._process_single_threaded()
        else:
            self._process_multi_threaded()

    def _log_progress(self) -> None:
        """
        Logs the progress of processing.
        """
        elapsed_time = time.time() - self.t
        logger.info(
            f"Batch {self.current_batch+1} with a size of {self.batch_size} study done in {elapsed_time:.2f} seconds."
        )
        self.t = time.time()
        self.current_batch += 1

    def _process_single_threaded(self) -> None:
        """
        Extract modalities in a single-threaded manner.
        """
        logger.info("Processing with a single thread.")
        session = self.db_manager.create_session()
        for i, study in enumerate(self.studies):
            self._extract_modalities_single_study(study, session)

            # log progress
            if i % self.batch_size == 0 and i != 0:
                self._log_progress()

    def _process_multi_threaded(self, debug: bool = False) -> None:
        """
        Extract modalities using multiple threads.
        """
        for item in self.studies:
            self.queue.put(item)

        logger.info("Starting up multiprocessing with {} threads.".format(self.threads))
        processes = [
            Process(
                target=self._extract_modalities_single_study_multi_thread,
            )
            for _ in range(self.threads)
        ]
        for process in processes:
            process.start()
        for process in processes:
            # TODO: Sometimes it hangs, but I cannot figure out why. Maybe you know how to solve this?
            if debug:
                if process.is_alive():
                    logger.debug(f"Process {process.name} is still running...")
                else:
                    logger.debug(f"Process {process.name} has finished.")
            process.join()
        logger.info("Multiprocessing closed.")

    def _extract_modalities_single_study_multi_thread(self) -> None:
        """
        Processes a single study and determines the modality of each series in that study.

        This method picks a study from the queue, retrieves its series from the database,
        determines the modality of each series using the appropriate strategy based on the manufacturer,
        and then stores the determined modalities back to the database.
        """
        while self.queue.qsize() > 0:
            session = self.db_manager.create_session()
            study = self.queue.get()
            self._extract_modalities_single_study(study, session)

            if self.queue.qsize() % self.batch_size == 0:
                self._log_progress()  # TODO: now self.current_batch is not 'shared' in multiprocessing, thus is also not updated. Needs to be fixed / logged in a different way.

    def _extract_modalities_single_study(self, study: Study, session: Session) -> None:
        """
        This method has a single study as input, and extracts its series from the database,
        determines the modality of each series using the appropriate strategy based on the manufacturer,
        and then stores the determined modalities back to the database.
        """
        try:
            study_series = session.query(Series).filter_by(study_id=study.id).all()

            manufacturer = extract_tag(study_series, "manufacturer")
            assert isinstance(manufacturer, str), "Manufacturer should be a string."
            strategy = ModalityStrategyFactory.get_strategy(manufacturer)

            modalities = []

            for series in study_series:
                filled_strategy = strategy(session, series)
                modality = filled_strategy.determine_sequence(series)
                modality.set_series_description(series.series_description)
                modality.set_series_id(int(series.id))
                modalities.append(modality)

            modalities, protocol = process_modalities(modalities)
            protocol.set_study_id(int(study.id))
            for mod in modalities:
                mod.upsert_db_entry(session)
            protocol.upsert_db_entry(session)

            session.commit()
            session.close()

        except Exception as e:
            print("Exception occurred:", e)
            print(traceback.format_exc())

    def _get_studies(self) -> List[Study]:
        """
        Retrieves all the studies from the database.

        Returns:
        - List[Study]: A list of studies retrieved from the database.
        """
        session = self.db_manager.create_session()
        studies = session.query(Study).all()
        session.close()
        logger.info(f"Extracting modalities for {len(studies)} studies.")
        return studies
