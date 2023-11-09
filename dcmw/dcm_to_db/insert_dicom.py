from typing import Any, Dict, Optional, Type, Union

import pydicom
from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError
from sqlalchemy.exc import DataError, IntegrityError, NoResultFound
from sqlalchemy.orm import Session

from dcmw.models.dicom_models import (
    Image,
    MRIImage,
    MRIImageGE,
    MRIImagePhilips,
    MRIImageSiemens,
    Patient,
    Series,
    Study,
)
from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils import populate_from_dicom
from dcmw.utils.utils_io import get_logger
from dcmw.utils.utils_models import load_config

logger = get_logger()
ModelConfig = load_config()


def check_and_add_instance(
    instance: WarehouseBase,
    session: Session,
    ModelClass: Type[WarehouseBase],
    unique_filter: Dict[str, Any],
    foreign_key: Optional[Dict[str, Any]] = None,
    extra_attrs: Optional[Dict[str, Any]] = None,
    retries: int = 0,
) -> Any:
    """Safely add an instance to the session, accounting for potential parallel processes."""
    try:
        instance = session.query(ModelClass).filter_by(**unique_filter).one()
    except NoResultFound:
        if foreign_key:
            setattr(instance, foreign_key["key"], foreign_key["value"])
        if extra_attrs:
            for key, value in extra_attrs.items():
                setattr(instance, key, value)
        try:
            session.add(instance)
            session.commit()
        except IntegrityError as e:
            # Rollback once due to race conditions with other processes
            session.rollback()
            if retries < 1:
                retries += 1
                instance = check_and_add_instance(
                    instance, session, ModelClass, unique_filter, foreign_key, extra_attrs, retries=retries
                )
            else:
                error_msg = f"Integrity error: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg)
        except DataError:
            print(instance)
    return instance


MODEL_TO_FILTER_ATTR = {
    Patient: "patient_name",
    Study: "study_instance_uid",
    Series: "series_instance_uid",
    Image: "sop_instance_uid",
    MRIImage: "sop_instance_uid",
    MRIImagePhilips: "image_id",
    MRIImageSiemens: "image_id",
    MRIImageGE: "image_id",
}


def process_model(
    ModelClass: Type[WarehouseBase],
    dicom_metadata: Dataset,
    session: Session,
    foreign_key: Optional[Dict[str, Any]] = None,
    extra_attrs: Optional[Dict[str, Any]] = None,
) -> Any:
    """Process a model based on its metadata and config."""
    instance = populate_from_dicom(ModelClass, dicom_metadata, ModelConfig[ModelClass.__name__])

    filter_attr = MODEL_TO_FILTER_ATTR.get(ModelClass)
    if not filter_attr:
        error_msg = f"Unsupported model class: {ModelClass}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    unique_filter = {filter_attr: getattr(instance, filter_attr)}

    return check_and_add_instance(instance, session, ModelClass, unique_filter, foreign_key, extra_attrs)


MANUFACTURER_MAPPING = {"philips": MRIImagePhilips, "siemens": MRIImageSiemens, "ge": MRIImageGE}


def process_manufacturer_specific(
    dicom_metadata: Dataset, series_instance: Series, mri_image_instance: MRIImage, session: Session
) -> None:
    """Process manufacturer specific models."""
    if series_instance.manufacturer:
        manufacturer = series_instance.manufacturer.lower()
    else:
        manufacturer = "unknown"

    for key, ModelClass in MANUFACTURER_MAPPING.items():
        if key in manufacturer:
            # Populate the instance using the DICOM metadata
            instance = populate_from_dicom(ModelClass, dicom_metadata, ModelConfig[ModelClass.__name__])

            # Unique filter based on image_id for vendor-specific table
            unique_filter = {"image_id": mri_image_instance.id}
            foreign_key = {"key": "image_id", "value": mri_image_instance.id}

            # Check and add (or get existing) instance for vendor-specific table
            check_and_add_instance(instance, session, ModelClass, unique_filter, foreign_key)
            break


def process_one_dicom_file(dcm_path: str, session: Session, debug: bool = False) -> None:
    """Read a DICOM file and process its data."""
    try:
        dicom_metadata = pydicom.dcmread(dcm_path, stop_before_pixels=True)
    except InvalidDicomError as e:
        logger.error(f"Error reading DICOM file {dcm_path}: {e}")
        if debug:
            raise
        return

    patient_instance = process_model(Patient, dicom_metadata, session)
    study_instance = process_model(Study, dicom_metadata, session, {"key": "patient_id", "value": patient_instance.id})
    series_instance = process_model(Series, dicom_metadata, session, {"key": "study_id", "value": study_instance.id})
    image_instance = process_model(
        Image, dicom_metadata, session, {"key": "series_id", "value": series_instance.id}, {"dicom_file": dcm_path}
    )
    mri_image_instance = process_model(
        MRIImage, dicom_metadata, session, {"key": "image_id", "value": image_instance.id}
    )
    process_manufacturer_specific(dicom_metadata, series_instance, mri_image_instance, session)
