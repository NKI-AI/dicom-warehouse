import os
import time
import traceback
from datetime import datetime, timedelta, time as datetime_time
from multiprocessing import Pool
from typing import Iterator, List, Tuple, Optional, Dict, Any

import SimpleITK as sitk
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from dcmw.db import DatabaseManager
from dcmw.models.dicom_models import Image, Series, Study
from dcmw.models.scan_models import ScanPath
from dcmw.utils.utils import time_difference
from dcmw.utils.utils_extraction import count_tag_values
from dcmw.utils.utils_io import get_logger

logger = get_logger()

class DICOMFilesExporter:
    """something here"""

    def __init__(
        self,
        db_manager: DatabaseManager,
        save_dir: str,
        extension: str = "nrrd",
        threads: int = 15,
        batch_size: int = 15,
    ) -> None:
        self.db_manager = db_manager
        self.save_dir = save_dir
        self.threads = threads
        self.extension = set_extension(extension)
        self.batch_size = batch_size
        self.current_batch = 0
        self.t = 0.0

    def process_database(self) -> None:
        """
        Process the DICOM files using either single threaded or multi-threaded approach based on the number of threads.

        If threads is set to 1, uses a single-threaded approach. Otherwise, uses a multi-threaded approach.
        """
        self.t = time.time()
        if self.threads == 1:
            logger.info("Using a single thread.")
            self._process_single_threaded()
        else:
            logger.info(f"Using {self.threads} threads.")
            self._process_multi_threaded()

    def _log_progress(self) -> None:
        """
        Logs the progress of processing.
        """
        elapsed_time = time.time() - self.t
        logger.info(
            f"Batch {self.current_batch} with a size of {self.batch_size} series done in {elapsed_time:.2f} seconds."
        )
        self.t = time.time()

    def _process_single_threaded(self) -> None:
        """
        Process DICOM series in a single-threaded manner.
        """
        for args in self._find_series_batch():
            for arg in args:
                self._process_series(arg)
            self._log_progress()

    def _process_multi_threaded(self) -> None:
        """
        Process DICOM series using multiple threads.
        """
        pool = Pool(processes=self.threads)
        for args in self._find_series_batch():
            pool.map(func=self._process_series, iterable=args)
            self._log_progress()

        pool.close()
        pool.join()

    def _process_series(self, series: Series, debug: bool = True) -> None:
        session = self.db_manager.create_session()
        try:
            self._setup_series_for_exporting(series, session)
        except Exception as e:
            session.rollback()
            logger.error(f"Error processing series: {series.series_instance_uid}" f"Error: {e}")
            if debug:
                raise
        finally:
            session.close()

    def _setup_series_for_exporting(self, series: Series, session: Session) -> None:
        """Prepare everything for exporting"""
        study = session.query(Study).filter_by(id=series.study_id).first()
        assert study is not None
        images = session.query(Image).filter_by(series_id=series.id).all()

        # find list of different acquisition times within a series
        acq_times = sorted(
            list(set([image.acquisition_time for image in images if image.acquisition_time is not None]))
        )
        acq_times = correct_time_mistakes(acq_times, images)

        for acq_time in acq_times:
            if len(acq_times) != 1:
                grouped_images = [image for image in images if image.acquisition_time == acq_time]
            else:
                grouped_images = images

            fns = [image.dicom_file for image in grouped_images if image.dicom_file is not None]
            output_filename = self._construct_output_filename(study, series, acq_time)
            metadata = self._set_metadata(study, series, acq_time)

            try:
                self._construct_and_save_scan(fns, output_filename, metadata, session, series)
            except Exception as e:
                logger.error(f"Error occured in series: {series.series_instance_uid}")
                logger.error(e)
                logger.error(str(traceback.format_exc()))

    def _construct_and_save_scan(self, fns: List[str], output_filename: str, metadata: Dict[str, Any], session: Session, series: Series) -> None:
        """Construct scan and send through to be saved."""
        if os.path.exists(output_filename):
            logger.info("Conversion stopped, file {} already exists.".format(output_filename))
            return

        # make output directory
        _construct_output_dir(output_filename)

        # find directory where the dicoms are stored
        dicom_dir = os.path.dirname(fns[0])

        # set file_reader (needed to set file names information for SimpleITK.)
        fns_path_for_itk = os.path.join(
            fns[0]
        )  # needed as there are spaces in the path names, and sitk.ImageFileReader can't handle that
        file_reader = sitk.ImageFileReader()  # type: ignore
        file_reader.SetFileName(fns_path_for_itk) # type: ignore
        file_reader.ReadImageInformation() # type: ignore

        # Sort dicom filenames
        sorted_filenames = sitk.ImageSeriesReader_GetGDCMSeriesFileNames(dicom_dir, metadata["series_instance_uid"]) # type: ignore
        time_sorted_filenames = [fn for fn in sorted_filenames if fn in fns]

        # create scan, with metadata
        img = sitk.ReadImage(time_sorted_filenames)
        for key, val in metadata.items():
            img.SetMetaData(key, val) # type: ignore
        sitk.WriteImage(img, output_filename)

        # save to database
        # TODO: what if something went wrong in this function, then image is already saved, but is put into database.
        # Need to shuffle some stuff / put writing to database and saving file in same try/except block?
        # What is best?
        # Also, what if image already exists, but not in database? Also, vice versa? What if directory changed, idk, what if?
        insert_path_to_db(output_filename, int(series.id), metadata["timestamp_of_acquisition"], session)

        logger.info("Series {} has been added under name {}".format(metadata["series_instance_uid"], output_filename))

    def _construct_output_filename(self, study: Study, series: Series, acq_time: datetime_time) -> str:
        """Construct name to save exported scan under."""
        out_dir_standard = "{}/{}/{}/{}/".format(
            self.db_manager.db_name, study.patient_name, study.study_instance_uid, series.series_instance_uid
        )
        acq_time_transformed = acq_time.strftime("%H_%M_%S")
        file_name = "{}".format(acq_time_transformed)
        out_filename = os.path.join(self.save_dir, out_dir_standard, file_name + self.extension)
        return out_filename

    def _set_metadata(self, study: Study, series: Series, acq_time: datetime_time) -> Dict[str, str]:
        metadata = {
            "patient_name": str(study.patient_name),
            "study_instance_uid": str(study.study_instance_uid),
            "series_instance_uid": str(series.series_instance_uid),
            "manufacturer": str(series.manufacturer),
            "mri_model_name": str(series.manufacturer_model_name),
            "date_of_creation": str(datetime.now()),
            "slice_thickness": str(series.slice_thickness),
            "patient_position": str(series.patient_position),
            "date_of_acquisition": str(series.series_date),
            "timestamp_of_acquisition": str(acq_time),
            "database_of_origin": str(self.db_manager.db_name),
        }
        return metadata

    def _find_series_batch(self) -> Iterator[List[Series]]:
        """
        Yields batches of series from the database, each of size {self.batch_size}.

        Yields:
        - List[Series]: A batch of series retrieved from the database.
        """
        session = self.db_manager.create_session()

        while True:
            series = session.query(Series).offset(self.current_batch * self.batch_size).limit(self.batch_size).all()
            if not series:
                # No more series to fetch
                break

            self.current_batch += 1
            yield series

        session.close()


def correct_time_mistakes(acq_times: List[datetime_time], images: List[Image]) -> List[datetime_time]:
    """Sometimes a 3D scan with no time-component can have different times, exactly 1 second apart.
    If this is the case, this function only returns the first of those timestamps."""
    if len(acq_times) > 1:
        all_one_second_apart = all(
            time_difference(acq_times[i], acq_times[i + 1]) == timedelta(seconds=1) for i in range(len(acq_times) - 1)
        )
        if all_one_second_apart:
            if len(set(count_tag_values(images, "acquisition_time").values())) != 1:
                return [acq_times[0]]
    return acq_times


def set_extension(extension: str) -> str:
    """Find the right file extension"""
    if extension == "nrrd":
        return ".nrrd"
    if extension == "nifti":
        return ".nii.gz"
    raise ValueError(f"Can't convert to format {extension}")


def insert_path_to_db(output_filename: str, series_id: int, acq_time: datetime_time, session: Session) -> None:
    """create db entry for scan_path"""
    db_entry = ScanPath(series_id=series_id, scan_path=output_filename, acquisition_time=acq_time)
    try:
        session.add(db_entry)
        session.commit()
    except (IntegrityError, DataError) as e:
        session.rollback()
        logger.error(e)

# TODO: maybe something like this to update database, instead of above insert_path_to_db function
# def add_or_update_image(session: Session, image_data) -> None:
#     # First, check if the entry already exists
#     existing_entry = (
#         session.query(ScanPath)
#         .filter(ScanPath.series_id == image_data.series_id, ScanPath.acquisition_time == image_data.acquisition_time)
#         .first()
#     )
#
#     if existing_entry:
#         # If exists, update
#         existing_entry.some_attribute = (
#             image_data.some_attribute
#         )  # replace 'some_attribute' with actual attribute names
#         # Update other fields as needed...
#     else:
#         # If not, add to session
#         session.add(image_data)
#
#     session.commit()


def _construct_output_dir(output_filename: str) -> None:
    """Make output directory."""
    output_dir = os.path.dirname(output_filename)
    os.makedirs(output_dir, exist_ok=True)
