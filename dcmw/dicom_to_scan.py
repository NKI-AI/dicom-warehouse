import argparse

from dcmw.db import get_database_manager
from dcmw.dcm_to_format.dicom_exporter import DICOMFilesExporter
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def main(db_name: str, save_dir: str, form: str = "nrrd", threads: int = 15, batch_size: int = 30) -> None:
    """Main function to process DICOM data into a 3D file format."""

    # Initialize database manager
    database_manager = get_database_manager(db_name)

    logger.info(f"Starting conversion of DICOM files in {db_name} to {form} format.")

    exporter = DICOMFilesExporter(database_manager, save_dir, form, threads=threads, batch_size=batch_size)
    exporter.process_database()

    logger.info(
        f"Done with exporting DICOM files from {db_name} to {form} format. "
        f"Exported files can be found in {save_dir}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export DICOM data to 3D scan format.")
    parser.add_argument("--db_name", type=str, required=True, help="Name of the database to use.")
    parser.add_argument(
        "--save_dir",
        type=str,
        required=True,
        help="Parent directory to save exported scans in. Files will be saved in according to:"
        "save_dir/db_name/patient_name/study_instance_uid/series_instance_uid/acq_time.extension",
    )
    parser.add_argument(
        "--format", type=str, default="nrrd", help="3D format to save DICOMs to.", choices=["nrrd", "nifti"]
    )
    parser.add_argument("--threads", type=int, default=1, help="Number of threads to use for processing.")
    parser.add_argument("--batch_size", type=int, default=50, help="Size of batches.")

    args = parser.parse_args()

    if not args.db_name:
        logger.error("No database name was set.")
    elif not args.save_dir:
        logger.error("No save directory was set.")
    else:
        main(args.db_name, args.save_dir, args.format, args.threads, args.batch_size)
