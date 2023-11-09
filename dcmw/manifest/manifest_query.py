"""
Create here your own query

As manifest_maker.py expects a list of Series as output, make sure your output does do.
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import List
from datetime import datetime

from dcmw.models import *
from dcmw.db import DatabaseManager
from dcmw.utils.utils_io import get_logger

logger = get_logger()

class QueryBase(ABC):
    """Query base class. Please write your own Query Class by looking at one of the examples below."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    @abstractmethod
    def execute_query(self) -> List[Series]:
        """Abstract function which holds the actual query"""
        pass


class QueryExample1(QueryBase):
    """Query Example 1: Retrieving all scans obtain with a 3T field strength."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)

    def execute_query(self) -> List[Series]:
        session = self.db_manager.create_session()
        series = (
            session.query(Series)
            .filter(
                Series.images.any(Image.mri_image.has(MRIImage.magnetic_field_strength == str(3))) # type: ignore
            )  # Filter field strength
            .all()
        )
        return series


class QueryExample2(QueryBase):
    """Query Example 2: Retrieving all scans obtain with a 3T field strength and being an
    ADC map (which is a dwi_type in the DWI modality class)."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)

    def execute_query(self) -> List[Series]:
        session = self.db_manager.create_session()
        series = (
            session.query(Series)
            .filter(
                Series.images.any(Image.mri_image.has(MRIImage.magnetic_field_strength == str(3))) # type: ignore
            )  # Filter field strength
            .filter(Series.dwi_modality.has(DWIModality.dwi_type == "adc"))  # Filter for dwi type ADC
            .all()
        )
        return series


class QueryExample3(QueryBase):
    """Query Example 3: Retrieving all scans obtain in a study before 2013 and being an
    T1 subtraction image."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)

    def execute_query(self) -> List[Series]:
        session = self.db_manager.create_session()
        series = (
            session.query(Series)
            .filter(Series.study.has(Study.study_date < date(2020, 1, 1))) # type: ignore # Filter for studies before 2020
            .filter(Series.t1w_modality.has(T1WModality.subtraction == True))  # Filter Series with T1 subtraction
            .all()
        )
        return series


def check_and_return_query_class(query_name: str) -> type:
    """Check for existence of query class, if it exists, return this class."""
    query_class = globals().get(query_name, None)

    if query_class and isinstance(query_class, type):
        return query_class
    else:
        error_message = "Query does not exist or is not a class. Please add it to manifest_query.py."
        logger.error(error_message)
        raise ValueError(error_message)
