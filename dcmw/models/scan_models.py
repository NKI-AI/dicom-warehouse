from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from dcmw.models.base_models import WarehouseBase


class ScanPath(WarehouseBase):
    __tablename__ = "scan_path"
    series_id = Column(Integer, ForeignKey("series.id"), index=True)
    series = relationship("Series", back_populates="scan_paths")

    scan_path = Column(String(400), unique=True)
    acquisition_time = Column(Time)
