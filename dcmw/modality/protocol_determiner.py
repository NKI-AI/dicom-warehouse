from typing import Dict, Tuple, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

from dcmw.modality.modalities import *
from dcmw.models.modality_models import StudyProtocol



# TODO: Make db model StudyProtocol
class StudyProtocolClass:
    """Class to hold study protocol"""

    def __init__(self, protocol: str, study_id: Optional[int] = None) -> None:
        self.study_id = study_id
        self.protocol = protocol

    def create_db_entry(self) -> StudyProtocol:
        """Create a database entry for StudyProtocol."""
        return StudyProtocol(protocol=self.protocol, study_id=self.study_id)

    def set_study_id(self, study_id: int) -> None:
        """set study id"""
        self.study_id = study_id

    def identify_existing(self, session: Session) -> StudyProtocol:
        """Return a query to identify the unique record in the database."""
        if self.study_id:
            return session.query(StudyProtocol).filter_by(**{"study_id": getattr(self, "study_id")}).one()
        else:
            raise ValueError("Study_ID not set for this study-protocol.")

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

    def update_existing(self, existing: StudyProtocol) -> None:
        """Overwrite the properties of the existing record."""
        new_entry = self.create_db_entry()
        for attr, value in new_entry.__dict__.items():
            if not attr.startswith("_sa_"):  # Filter out internal SQLAlchemy attributes
                setattr(existing, attr, value)


def count_modalities(modalities: List[Modality]) -> Dict[str, int]:
    """Count the amount a certain modality is present in one study."""
    t1_count = 0
    t2_count = 0
    dwi_count = 0
    subtraction_t1_count = 0
    ultrafast_t1_count = 0

    # Count each modality type
    for modality in modalities:
        if isinstance(modality, T1W):
            if modality.subtraction:
                subtraction_t1_count += 1
            elif modality.timeseries == "fast":
                ultrafast_t1_count += 1
            else:
                t1_count += 1
        elif isinstance(modality, T2W):
            t2_count += 1
        elif isinstance(modality, DWI):
            dwi_count += 1
    return {
        "t1_count": t1_count,
        "t2_count": t2_count,
        "dwi_count": dwi_count,
        "subtraction_t1_count": subtraction_t1_count,
        "ultrafast_t1_count": ultrafast_t1_count,
    }


def determine_protocol(counts: Dict[str, int]) -> StudyProtocolClass:
    """ Check if there is a full protocol:
    DWI, T2, Ultrafast T1, and multiple T1s (contrast-series)."""
    # Check protocol completion
    missing_modalities = []
    if counts["t1_count"] < 2:
        missing_modalities.append("T1")
    if counts["t2_count"] < 1:
        missing_modalities.append("T2")
    if counts["dwi_count"] < 1:
        missing_modalities.append("DWI")
    if counts["ultrafast_t1_count"] < 1:
        missing_modalities.append("Ultrafast T1")

    if not missing_modalities:
        protocol = "Full protocol"
    else:
        protocol = f"Not full protocol. Missing: {', '.join(missing_modalities)}"

    return StudyProtocolClass(protocol)


def t1_contrast(modalities: List[Modality]) -> List[Modality]:
    """Finds T1 scans which belong to the contrast series, and names them accordingly."""
    t1_post_contrast_count = 0
    for modality in modalities:
        if isinstance(modality, T1W) and not modality.subtraction and modality.timeseries != "ultrafast":
            if t1_post_contrast_count == 0:
                if modality.timeseries == "slow":
                    modality.contrast_series = "pre-contrast_post-contrast"
                else:
                    modality.contrast_series = "pre-contrast"
            else:
                modality.contrast_series = f"post-contrast_{t1_post_contrast_count}"
            t1_post_contrast_count += 1
    return modalities


def process_modalities(modalities: List[Modality]) -> Tuple[List[Modality], StudyProtocolClass]:
    """Determine the study protocol, and t1 contrast series.
    However, work in progress, not perfect yet (and never will be;p)"""
    # TODO: needs to work on this, also needs to take into account the acquisition time?

    sorted_modalities = sorted(modalities, key=lambda x: (x.acquisition_time is None, x.acquisition_time))

    counts = count_modalities(sorted_modalities)
    modalities = t1_contrast(sorted_modalities)
    protocol = determine_protocol(counts)

    return modalities, protocol
