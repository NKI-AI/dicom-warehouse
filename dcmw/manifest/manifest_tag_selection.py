import os
from datetime import date, datetime, time
from typing import Dict, List, Optional, Any, Union, Callable

import toml

from dcmw.models import *
from dcmw.paths import CONFIG_DIR
from dcmw.utils.utils_io import get_logger

logger = get_logger()

# Define a relationship map to guide the data extraction (starting from series)
# TODO: this does not return multiple values if there exists more than one relation, for example series -> image (a series can have multiple images)
def get_mri_image(series: Series) -> Optional[MRIImage]:
    if not series.images:
        return None
    first_image = next(iter(series.images), None)
    return first_image.mri_image if first_image else None

def safe_get_image_attribute(series: Series, attribute: str) -> Optional[Any]:
    mri_image = get_mri_image(series)
    if not mri_image:
        return None
    return getattr(mri_image, attribute, None)

# Define the lambda function type
RelationshipLambdaType = Callable[[Series], Optional[WarehouseBase]]

RELATIONSHIP_MAPPING: Dict[str, RelationshipLambdaType] = {
    "series": lambda s: s,
    "study": lambda s: s.study,
    "patient": lambda s: s.study.patient if s.study else None,
    "image": lambda s: next(iter(s.images or []), None),  # Getting the first image if it exists
    "mri_image": lambda s: get_mri_image(s),
    "mri_image_philips": lambda s: safe_get_image_attribute(s, "image_philips"),
    "mri_image_siemens": lambda s: safe_get_image_attribute(s, "image_siemens"),
    "mri_image_ge": lambda s: safe_get_image_attribute(s, "image_ge"),
    "scan_path": lambda s: list(s.scan_paths) if s.scan_paths else None, # Get all related scans
    "t1w_modality": lambda s: s.t1w_modality,
    "t2w_modality": lambda s: s.t2w_modality,
    "mdixon_modality": lambda s: s.mdixon_modality,
    "dwi_modality": lambda s: s.dwi_modality,
    "mip_modality": lambda s: s.mip_modality,
    "undetermined_modality": lambda s: s.undetermined_modality,
    "study_protocol": lambda s: s.study.study_protocol if s.study else None,
}
# TODO: here ends previous todo on how to return multiple values (line 14)

def get_column_values_from_series(series_list: List[Series]) -> List[Dict[str, Any]]:
    """
    Fetches column values for a list of series based on the configuration specified in the "query.toml" file.

    :param series_list: List of Series objects to retrieve column values from.
    :return: List of dictionaries, where each dictionary corresponds to a series with key-value pairs representing
        model_column names and their values.
    """
    # Load the TOML configuration
    config = toml.load(os.path.join(CONFIG_DIR, "query.toml"))

    results = []

    for series in series_list:
        data = {}

        # Loop over all sections in the TOML (e.g., Standard, Modality, User)
        for section_name, section in config.items():
            for column_info in section["columns"]:
                model_name = column_info["model_name"]
                column_name = column_info["column_name"]

                # If you want a different naming format for "Modality" section
                if section_name == "Modality":
                    key_name = f"{model_name}_{column_name}"
                else:
                    key_name = f"{column_name}"

                try:
                    related_instance = RELATIONSHIP_MAPPING[model_name](series)

                    # Special handling for one-to-many relationships
                    if model_name == "scan_path" and isinstance(related_instance, list):
                        # Extract the desired attribute from each related record
                        data[key_name] = [getattr(item, column_name, None) for item in related_instance]
                    else:
                        data[key_name] = getattr(related_instance, column_name, None) if related_instance else None
                except AttributeError:
                    # Handle cases where the relationship/column does not exist
                    data[key_name] = None

        results.append(data)

    return results


def fill_manifest(series_list: List[Series], db_name: str) -> List[Dict[str, Any]]:
    """
    Populates the manifest with the series' column values and the specified database name.

    :param series_list: List of Series objects to be included in the manifest.
    :param db_name: Name of the database to be added to the manifest.
    :return: Populated manifest as a list of dictionaries.
    """
    manifest = get_column_values_from_series(series_list)

    series_without_scan = []
    for entry in manifest:
        entry["db_name"] = db_name
        if not entry["scan_path"]:
            series_without_scan.append(entry["series_instance_uid"])

    message = f"Your query resulted in {len(manifest)} found series from database {db_name}."
    if series_without_scan:
        message += (
            f"\nHowever, {len(series_without_scan)} series do not have a scan yet. \n"
            f"These series are still put in your manifest. \n"
            f"If this is unwanted, remove them manually, "
            f"adjust your query, or use dicom_to_scan.py to actually create these scans. \n"
            f"This is a list of all series which do not have a scan (no entry in table scan_path):\n"
            f"{series_without_scan}"
        )
    logger.info(message)

    return manifest


def json_serial(obj: Any) -> Union[str, None]:
    """JSON serializer for objects not serializable by default json code
    Obtained from https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable"""

    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


def write_json_manifest(manifest: str, save_dir: str, manifest_name: str) -> None:
    """Write json dump to file."""
    output_file_name = os.path.join(save_dir, manifest_name)
    with open(output_file_name, "w") as out_file:
        out_file.write(manifest)
        logger.info(f"Saved manifest in {output_file_name}")
