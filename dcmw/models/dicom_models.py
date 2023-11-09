import typing
from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship
from typing import Optional
from datetime import date, time

from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils_models import load_config_and_extend_models


class Patient(WarehouseBase):
    __tablename__ = "patient"
    studies = relationship("Study", back_populates="patient")

class Study(WarehouseBase):
    __tablename__ = "study"
    patient_id = Column(Integer, ForeignKey("patient.id"), index=True)
    patient = relationship("Patient", back_populates="studies")
    series = relationship("Series", back_populates="study")
    # New due to study protocol
    study_protocol = relationship("StudyProtocol", back_populates="study", uselist=False)

    if typing.TYPE_CHECKING:
        patient_name: Optional[str] = None
        study_instance_uid: Optional[str] = None
        study_date: Optional[date] = None


class Series(WarehouseBase):
    __tablename__ = "series"
    study_id = Column(Integer, ForeignKey("study.id"), index=True)
    study = relationship("Study", back_populates="series")
    images = relationship("Image", back_populates="series")
    # New due to automatic series description
    t1w_modality = relationship("T1WModality", back_populates="series", uselist=False)
    t2w_modality = relationship("T2WModality", back_populates="series", uselist=False)
    mdixon_modality = relationship("MDixonModality", back_populates="series", uselist=False)
    dwi_modality = relationship("DWIModality", back_populates="series", uselist=False)
    mip_modality = relationship("MIPModality", back_populates="series", uselist=False)
    undetermined_modality = relationship("UndeterminedModality", back_populates="series", uselist=False)
    # New due to scan_path
    scan_paths = relationship("ScanPath", back_populates="series")

    if typing.TYPE_CHECKING:
        manufacturer: Optional[str] = None
        series_instance_uid: Optional[str] = None
        series_date: Optional[date] = None
        patient_position: Optional[str] = None
        slice_thickness: Optional[str] = None
        manufacturer_model_name: Optional[str] = None
        series_description: Optional[str] = None


class Image(WarehouseBase):
    __tablename__ = "image"
    series_id = Column(Integer, ForeignKey("series.id"), index=True)
    series = relationship("Series", back_populates="images")
    mri_image = relationship("MRIImage", back_populates="image", uselist=False)

    if typing.TYPE_CHECKING:
        dicom_file: Optional[str] = None
        acquisition_time: Optional[time] = None


class MRIImage(WarehouseBase):
    __tablename__ = "mri_image"
    image_id = Column(Integer, ForeignKey("image.id"), index=True)
    image = relationship("Image", back_populates="mri_image", uselist=False)
    image_philips = relationship("MRIImagePhilips", back_populates="mri_image", uselist=False)
    image_siemens = relationship("MRIImageSiemens", back_populates="mri_image", uselist=False)
    image_ge = relationship("MRIImageGE", back_populates="mri_image", uselist=False)


class MRIImagePhilips(WarehouseBase):
    __tablename__ = "mri_image_philips"
    image_id = Column(Integer, ForeignKey("mri_image.id"), unique=True, index=True)
    mri_image = relationship("MRIImage", back_populates="image_philips")


class MRIImageSiemens(WarehouseBase):
    __tablename__ = "mri_image_siemens"
    image_id = Column(Integer, ForeignKey("mri_image.id"), unique=True, index=True)
    mri_image = relationship("MRIImage", back_populates="image_siemens")


class MRIImageGE(WarehouseBase):
    __tablename__ = "mri_image_ge"
    image_id = Column(Integer, ForeignKey("mri_image.id"), unique=True, index=True)
    mri_image = relationship("MRIImage", back_populates="image_ge")


models_dict = {
    "Patient": Patient,
    "Study": Study,
    "Series": Series,
    "Image": Image,
    "MRIImage": MRIImage,
    "MRIImagePhilips": MRIImagePhilips,
    "MRIImageSiemens": MRIImageSiemens,
    "MRIImageGE": MRIImageGE,
}

# extent models based on config
load_config_and_extend_models(models_dict)
