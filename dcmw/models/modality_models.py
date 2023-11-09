from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship

from dcmw.models.base_models import WarehouseBase


class T1WModality(WarehouseBase):
    __tablename__ = "t1w_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="t1w_modality")

    acquisition_time = Column(Time)
    time_series = Column(String(50))
    fat_sup = Column(String(50))
    subtraction = Column(Boolean)
    series_description = Column(String(100))
    contrast_series = Column(String(50))


class T2WModality(WarehouseBase):
    __tablename__ = "t2w_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="t2w_modality")

    acquisition_time = Column(Time)
    series_description = Column(String(100))


class MDixonModality(WarehouseBase):
    __tablename__ = "mdixon_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="mdixon_modality")

    acquisition_time = Column(Time)
    dixon_type = Column(String(50))
    series_description = Column(String(100))


class DWIModality(WarehouseBase):
    __tablename__ = "dwi_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="dwi_modality")

    acquisition_time = Column(Time)
    dwi_type = Column(String(50))
    b_value_1 = Column(Integer)
    b_value_2 = Column(Integer)
    series_description = Column(String(100))


class MIPModality(WarehouseBase):
    __tablename__ = "mip_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="mip_modality")

    acquisition_time = Column(Time)
    mip_type = Column(String(50))
    series_description = Column(String(100))


class UndeterminedModality(WarehouseBase):
    __tablename__ = "undetermined_modality"
    series_id = Column(Integer, ForeignKey("series.id"), unique=True, index=True)
    series = relationship("Series", back_populates="undetermined_modality")

    acquisition_time = Column(Time)
    reason = Column(String(100))
    series_description = Column(String(100))


# Study protocol


class StudyProtocol(WarehouseBase):
    __tablename__ = "study_protocol"
    study_id = Column(Integer, ForeignKey("study.id"), unique=True, index=True)
    study = relationship("Study", back_populates="study_protocol")

    protocol = Column(String(200))
