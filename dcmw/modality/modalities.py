import ast
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, time
from typing import Optional, Type, Any, List, Union

import numpy as np
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from dcmw.models.modality_models import *
from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils import extract_value_from_mapping
from dcmw.utils.utils_extraction import extract_tag_values
from dcmw.utils.utils_io import get_logger

# TODO:
# Do we need a modality LOC? Is now often misclassified as T2.
# Still needs code to extract b-values for ADC/DWI

# Constants & Logger Initialization
logger = get_logger()

MDIXON_MAPPING = {
    "IP": "InPhase",
    "OP": "OutPhase",
    "W": "Water",
    "F": "Fat",
    "4": "All 4 variants",
    "unknown": "unknown",
}

T1W_MAPPING = {"single": "single", "slow": "slow", "fast": "ultrafast"}

UNDETERMINED_MAPPING = {
    "vendor": "No logic for vendor",
    "critical_parameter": "Missing information in critical parameters",
    "no_logic": "No logic for this specific set of parameters",
}


class Modality(ABC):
    """Standard Modality class.
    This class determines the modality of a series based on standard DICOM tags
    and provides additional context beyond the standard Modality.
    So basically, it's the series description, but better.
    """

    def __init__(self, acquisition_time: Optional[List[time]] = None, series_id: Optional[int] = None, series_description: Optional[str] = None) -> None:
        self.series_id = series_id
        self.series_description = series_description
        self.acquisition_time = acquisition_time
        self.sqlalchemy_model: Optional[Type[WarehouseBase]] = None

    @abstractmethod
    def create_db_entry(self) -> WarehouseBase:
        """Create a database entry for the modality."""
        pass

    def set_series_description(self, series_description: Union[str, None]) -> None:
        """Set the series description."""
        self.series_description = series_description

    def set_series_id(self, series_id: int) -> None:
        """Set the series ID."""
        self.series_id = series_id

    def identify_existing(self, session: Session) -> WarehouseBase:
        """Return a query to identify the unique record in the database."""
        if self.series_id and self.sqlalchemy_model:
            return session.query(self.sqlalchemy_model).filter_by(**{"series_id": getattr(self, "series_id")}).one()
        else:
            raise ValueError("Series_ID or SQLAlchemy model not set for this modality.")

    def upsert_db_entry(self, session: Session) -> None:
        """Handle the upsert functionality."""
        try:
            # Try to fetch the existing record
            existing = self.identify_existing(session)
            # Update the record as needed
            self.update_existing(existing)
        except NoResultFound:
            # No existing record found, so add a new one
            session.add(self.create_db_entry())

    def update_existing(self, existing: WarehouseBase) -> None:
        """Overwrite the properties of the existing record."""
        new_entry = self.create_db_entry()
        for attr, value in new_entry.__dict__.items():
            if not attr.startswith("_sa_"):  # Filter out internal SQLAlchemy attributes
                setattr(existing, attr, value)


# Individual Modality Classes


class T1W(Modality):
    """T1W Modality with additional attributes related to T1W type."""

    def __init__(self, acquisition_time: List[time], timeseries: str = "single", fat_sup: Optional[bool] = None,
                 subtraction: bool = False, contrast_series: Optional[str] =None) -> None:
        super().__init__(acquisition_time)
        self.timeseries: str = extract_value_from_mapping(timeseries, T1W_MAPPING)
        # self.timeseries = timeseries
        self.fat_sup = fat_sup
        self.subtraction = subtraction
        self.contrast_series = contrast_series
        self.sqlalchemy_model = T1WModality

    def create_db_entry(self) -> T1WModality:
        """Create a database entry for T1W modality."""
        assert self.acquisition_time is not None
        return T1WModality(
            acquisition_time=self.acquisition_time[0],
            time_series=self.timeseries,
            fat_sup=self.fat_sup,
            subtraction=self.subtraction,
            series_description=self.series_description,
            series_id=self.series_id,
            contrast_series=self.contrast_series,
        )


class T2W(Modality):
    """T2W Modality."""

    def __init__(self, acquisition_time: List[time]) -> None:
        super().__init__(acquisition_time)
        self.sqlalchemy_model = T2WModality

    def create_db_entry(self) -> T2WModality:
        """Create a database entry for T2W modality."""
        assert self.acquisition_time is not None
        return T2WModality(
            acquisition_time=self.acquisition_time[0],
            series_description=self.series_description,
            series_id=self.series_id,
        )


class DWI(Modality):
    """DWI Modality with additional attributes related to DWI type and b-values."""

    def __init__(self, acquisition_time: List[time], dwi_type: str, b_values: Optional[List[Union[int, None]]] = None) -> None:
        super().__init__(acquisition_time)
        if b_values is None:
            b_values = [None, None]
        self.dwi_type = dwi_type
        self.b_values = b_values
        self.sqlalchemy_model = DWIModality

    def create_db_entry(self) -> DWIModality:
        """Create a database entry for DWI modality."""
        assert self.acquisition_time is not None
        return DWIModality(
            acquisition_time=self.acquisition_time[0],
            dwi_type=self.dwi_type,
            b_value_1=self.b_values[0],
            b_value_2=self.b_values[1],
            series_description=self.series_description,
            series_id=self.series_id,
        )


class MDixon(Modality):
    def __init__(self, acquisition_time: List[time], dixon_type: str) -> None:
        """MDixon Modality with a specific dixon type."""
        super().__init__(acquisition_time)
        self.dixon_type: str = extract_value_from_mapping(dixon_type, MDIXON_MAPPING)
        self.sqlalchemy_model = MDixonModality

    def create_db_entry(self) -> MDixonModality:
        """Create a database entry for MDixon modality."""
        assert self.acquisition_time is not None
        return MDixonModality(
            acquisition_time=self.acquisition_time[0],
            dixon_type=self.dixon_type,
            series_description=self.series_description,
            series_id=self.series_id,
        )


class MIP(Modality):
    """MIP Modality with a specific MIP type."""

    def __init__(self, acquisition_time: List[time], mip_type: Optional[str] = None) -> None:
        super().__init__(acquisition_time)
        self.mip_type = mip_type
        self.sqlalchemy_model = MIPModality

    def create_db_entry(self) -> MIPModality:
        """Create a database entry for MIP modality."""
        assert self.acquisition_time is not None
        return MIPModality(
            acquisition_time=self.acquisition_time[0],
            mip_type=self.mip_type,
            series_description=self.series_description,
            series_id=self.series_id,
        )


def transform_reason(reason_code: str) -> str:
    """Transforms a reason code into a meaningful reason message."""
    return UNDETERMINED_MAPPING.get(reason_code, "Unknown reason")


class Undetermined(Modality):
    """Undetermined Modality indicating a series with unknown or incomplete tags."""

    def __init__(self, reason_code: str, acquisition_time: Optional[List[time]] = None) -> None:
        super().__init__(acquisition_time)
        self.reason_msg: str = transform_reason(reason_code)
        self.sqlalchemy_model = UndeterminedModality

    def create_db_entry(self) -> UndeterminedModality:
        """Create a database entry for undetermined modality."""
        assert self.acquisition_time is not None
        return UndeterminedModality(
            acquisition_time=self.acquisition_time[0],
            reason=self.reason_msg,
            series_description=self.series_description,
            series_id=self.series_id,
        )
