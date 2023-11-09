from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship

from dcmw.models.base_models import WarehouseBase
from dcmw.models.dicom_models import Patient

# -----------------------------------------------------------------------
"""
NOTE: DON'T FORGET TO RUN A MIGRATION AFTER ADJUSTING ANY OF THE MODELS.
Otherwise, there will be a mismatch between the database and the code, resulting in errors.
To run migrations, consider using Alembic.
"""
# -----------------------------------------------------------------------
"""
Example model: A model which holds series which contain malignancies.

class SeriesWithMalignancy(WarehouseBase):   # model name, use CamelCase
    __tablename__ = 'series_with_malignancy'   # table name, use snake case.
    series_id = Column(Integer, ForeignKey('series.id'), index=True)  # A foreign key example.
    series = relationship("Series", back_populates="series_with_malignancy")  # Back populate example, if you have a column with back population, see below.
    series_identifier = Column(String(200), unique=True)   # Example of a unique column. Make sure there is always a unique column.
    malignancy_type = Column(String(50))  # Example of column with type string, and a max length of 50 characters.
    location_quadrant = Column(Integer)   # Example of a column with type integer.
    
In case you have used a relationship, make sure the relating model has a corresponding column.
In the example case, the following line needs to be added to model 'Series':

series_with_malignancy = relationship("SeriesWithMalignancy", back_populates="series")

Furthermore, if you have used a relationship: Add mapping information. 
(This states which column in the new table maps to a different column in an already existing table.)

SeriesWithMalignancy.mapping_info = {
    "class": Series,
    "foreign_column": "series_instance_uid",
    "class_column": "series_identifier"
}

Make sure you always have a unique column. This makes sure there will be no duplicates in your table if you re-upload your data.
Without a unique column, your data won't be uploaded to the database.
"""
# ---------------------------------------------------------------------