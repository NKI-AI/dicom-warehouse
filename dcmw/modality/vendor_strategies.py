import ast
from abc import ABC, abstractmethod
from datetime import datetime, time, timedelta
from typing import Type, List, Union, Dict, Optional, Any

import numpy as np
from sqlalchemy.orm import joinedload, Session

from dcmw.modality.modalities import DWI, MIP, T1W, T2W, MDixon, Undetermined, Modality
from dcmw.models.dicom_models import Image, Series, MRIImage
from dcmw.models.base_models import WarehouseBase
from dcmw.utils.utils_extraction import extract_tag_values
from dcmw.utils.utils_io import get_logger

logger = get_logger()


class ModalityStrategy(ABC):
    """Base strategy class for determining modality types based on different criteria."""

    def __init__(self, session: Session, series: Series, debug: bool = False) -> None:
        """
        Initialize the modality strategy with session, series, and debug mode.

        :param session: The database session.
        :param series: The series of images to be processed.
        :param debug: Flag to indicate whether debug information should be printed.
        """
        self.vendor_images: List[WarehouseBase]
        self.session = session
        self.series = series
        self.images = self._query_images_by_series()
        self.mri_images = self._filter_mri_images()
        self.critical_tags: Dict[str, Union[str, int, float, List[str], List[List[str]], List[time], None]]
        self.multiple_tags = ["image_type"]
        self.acquisition_times = self._set_acquisition_times()

        if debug:
            self._print_debug_info()

    @abstractmethod
    def determine_sequence(self, series: Series) -> Modality:
        """
        Abstract method to determine the sequence type.
        Should be implemented by each vendor-specific strategy.
        """
        pass

    def _print_debug_info(self) -> None:
        """Print debug information about the series description and image file.
        Now you can easily do: dcmpdump {file_location} and check its tags"""
        print(self.series.series_description)
        print(self.images[0].dicom_file)

    def _query_images_by_series(self) -> List[Image]:
        """Query and return all images associated with the current series, joined by all corresponding MRIImages."""
        return self.session.query(Image).options(joinedload(Image.mri_image)).filter_by(series_id=self.series.id).all()

    def _filter_mri_images(self) -> List[MRIImage]:
        """Filter and return only the MRI images from the current series."""
        return [image.mri_image for image in self.images if image.mri_image]

    def _filter_vendor_images(self, vendor_image_attribute: str) -> None:
        """Get all associated vendor images"""
        self.vendor_images = [
            getattr(image, vendor_image_attribute)
            for image in self.mri_images
            if getattr(image, vendor_image_attribute)
        ]

    def _set_acquisition_times(self) -> List[time]:
        """Set and return acquisition times, ensuring no duplicates."""
        times = sorted({image.acquisition_time for image in self.images if image.acquisition_time})
        try:  # TODO: this needs to change, looks dumb and off.
            if not times[0]:
                times = [time.min]
        except IndexError:
            times = [time.min]
        return times

    def _get_mean_time_in_between(self) -> int:
        """Calculate the mean time between acquisitions, in seconds (int)."""
        timedeltas = [datetime.combine(datetime.min, t) - datetime.min for t in self.acquisition_times]
        differences = [(t - s).total_seconds() for s, t in zip(timedeltas, timedeltas[1:])]
        mean_time_in_between = timedelta(seconds=float(np.mean(differences)))
        return mean_time_in_between.seconds

    def _get_critical_tags(self, *tags: str) -> None:
        self.critical_tags = {tag: self._extract_critical_tag(tag, multiple=tag in self.multiple_tags) for tag in tags}

    def _test_critical_tags(self) -> None | Undetermined:
        """If a critical tag is None, then series description cannot be determined."""
        assert self.critical_tags is not None
        for value in self.critical_tags.values():
            if value is None or value == "":
                return Undetermined("critical_parameter", self.acquisition_times)
        return None

    def _extract_critical_tag(self, tag: str, multiple: bool = False) -> Any:
        """Extract critical tag from a set of (vendor specific) images."""
        assert self.vendor_images is not None
        tag_values = extract_tag_values(self.vendor_images, tag)
        if len(tag_values) == 0:
            # error_msg = f"No value for {tag}: {tag_values}"
            # logger.debug(error_msg)
            return None
        if multiple:
            if tag == "image_type":  # TODO: this is ugly, needs cleaning up
                try:
                    tag_values = [ast.literal_eval(x) for x in tag_values if x is not None]  # TODO: literal_eval <3
                    tag_values = tag_values[0]
                except (SyntaxError, ValueError) as e:
                    # In some cases, dicom tags suck.
                    print(e)
                    return None
            return tag_values
        if len(tag_values) > 1:
            error_msg = f"Multiple values for {tag}: {tag_values}"
            logger.debug(error_msg)
            return None
        return tag_values[0]


class PhilipsStrategy(ModalityStrategy):
    def __init__(self, session: Session, series: Series) -> None:
        super().__init__(session, series)
        self._filter_vendor_images("image_philips")
        self._get_critical_tags("acquisition_contrast", "pulse_sequence_name", "image_type")

    def determine_sequence(self, series: Series) -> Modality:
        """Abstract method to determine the sequence type."""
        critical_test_result = self._test_critical_tags()
        if critical_test_result:
            return critical_test_result

        image_type = self.critical_tags["image_type"]

        # DWI #
        if self.critical_tags["acquisition_contrast"] == "DIFFUSION":
            if isinstance(image_type, list) and len(image_type) > 0:
                if image_type[2] == "ADC" or image_type[3] == "ADC":
                    return DWI(self.acquisition_times, "adc")  # TODO: used b-values to calculate adc
                if image_type[2] == "EADC" or image_type[3] == "EADC":
                    # TODO: what are extra-params for these kind of series?
                    return DWI(self.acquisition_times, "eadc")  # TODO: used b-values to calculate eadc, what is eadc?:)
            return DWI(self.acquisition_times, "dwi")  # TODO: find b-values

        # T2 # TODO: what are extra-params for T2?
        if self.critical_tags["acquisition_contrast"] == "T2":
            return T2W(self.acquisition_times)

        # T1 / mDIXON
        if self.critical_tags["acquisition_contrast"] == "T1":
            if isinstance(image_type, list) and len(image_type) > 0:
                # mDIXON logic  #TODO: Does this work? Seems like it has a lot more options? #old comment
                if len(image_type) == 4:
                    return MDixon(self.acquisition_times, "4")
                if image_type[2] == "IP":
                    return MDixon(self.acquisition_times, "IP")
                if image_type[2] == "OP":
                    return MDixon(self.acquisition_times, "OP")
                if image_type[2] == "F":
                    return MDixon(self.acquisition_times, "F")

                if image_type[2] == "W":
                    # Some MDixon water can be ultrafast, apparently.
                    if len(self.acquisition_times) > 1:
                        mean_time_in_between = self._get_mean_time_in_between()
                        if mean_time_in_between == 1:
                            "Sometimes mistake in DICOM and a single scan got two timestamps (precisely 1s apart)."
                            return MDixon(self.acquisition_times, "W")
                        return T1W(self.acquisition_times, timeseries="fast")
                    return MDixon(self.acquisition_times, "W")

                if image_type == ["ORIGINAL", "PRIMARY", "M_FFE", "M", "FFE"] or image_type == ["ORIGINAL", "PRIMARY", "M_SE", "M", "SE"]:
                    if len(self.acquisition_times) > 1:
                        mean_time_in_between = self._get_mean_time_in_between()
                        if mean_time_in_between > 30:
                            # if time difference more than 1 min, probably a T1 pre- post contrast time series
                            return T1W(self.acquisition_times, timeseries="slow")
                        elif mean_time_in_between == 1:
                            return T1W(self.acquisition_times, timeseries="single")
                        else:
                            return T1W(self.acquisition_times, timeseries="fast")
                        # in few cases, some T1 sequences where exactly 1s apart. According to their names,
                        # it should be subtraction images. This need to be manually verified however.

                    # TODO: it needs to be checked whether this holds:
                    unknown_key_substraction = extract_tag_values(self.vendor_images, "unknown_key_for_sinwas_distinction")[0]
                    if unknown_key_substraction > 1:
                        return T1W(self.acquisition_times, subtraction=True)

                    # Else, a single T1 or still a subtraction
                    return T1W(self.acquisition_times, timeseries="single")

                ## More T1 stuff
                # unknown_key = dcm_obj[
                #     0x2005, 0x100d]  ## For differentiating between sinwas and others (works if there is only 1 sinwas at least)
                # if unknown_key.value == 0.0:  # only true t1 assumed to have 0.0 (sinwas/suitwas has high unzero value)
                #     --> probably sinwas/suitwas
                #     waterfatshift = dcm_obj[0x2001, 0x1022].value
                #     if 0.9 < waterfatshift < 1.1:  # silicone has waterfatshift of approx 1
                #         --> probably silicone series

                # MIPs logic
                if image_type[2] in ["PROJECTION IMAGE", "PROJECTION IMAG"]:
                    return MIP(self.acquisition_times, "t1w")

        return Undetermined("no_logic", self.acquisition_times)


class SiemensStrategy(ModalityStrategy):
    def __init__(self, session: Session, series: Series) -> None:
        super().__init__(session, series)
        self._filter_vendor_images("image_siemens")
        self._get_critical_tags("sequence_name", "image_type")

    def determine_sequence(self, series: Series) -> Modality:
        """Abstract method to determine the sequence type."""
        critical_test_result = self._test_critical_tags()
        if critical_test_result:
            return critical_test_result

        image_type = self.critical_tags["image_type"]

        # imagetype dyn: ['ORIGINAL', 'PRIMARY', 'M', 'ND'] not always
        # '*tir2d1_11', '*tir2d1_16', '*tir2d1_13', '*tir2d1_15' for STIR

        # DWI logic
        if isinstance(image_type, list) and len(image_type) > 0:
            if image_type[2] == "DIFFUSSION":
                if image_type[3] == "ADC":
                    return DWI(self.acquisition_times, "adc")
                return DWI(self.acquisition_times, "dwi")

        # T2 logic
        if self.critical_tags["sequence_name"] in [
            "*tse2d1_21",
            "*tir2d1_17",
            "*tse2d1_19",
            "*tse2d1_17",
            "*tse2d1_15",
            "*tse2d1_11",
            "*tse2d1_23",
            "*tir2d1_11",
            "*tseR2d1rs19",
        ]:
            return T2W(self.acquisition_times)

        # T1 logic / mdixon?
        if self.critical_tags["sequence_name"] in ["*fl3d1", "*tse2d1_4", "*fl3d1_ns"]:
            if isinstance(image_type, list) and len(image_type) > 0:
                if isinstance(image_type[3], str) and "MIP" in image_type[3]:
                    return MIP(self.acquisition_times, "t1w")
                if image_type[-1] == "SUB":
                    if len(self.acquisition_times) > 1:
                        return T1W(self.acquisition_times, subtraction=True, timeseries="slow")
                    return T1W(self.acquisition_times, subtraction=True, timeseries="single")
                if image_type[-1] == "NORM":
                    return T1W(self.acquisition_times, timeseries="single")  # TODO: check this, no idea what/why I did?
            if len(self.acquisition_times) > 1:
                mean_time_in_between = self._get_mean_time_in_between()
                if mean_time_in_between > 30:
                    # if time difference more than 1 min, probably a T1 pre- post contrast time series
                    return T1W(self.acquisition_times, timeseries="slow")
                elif mean_time_in_between == 1:
                    return T1W(self.acquisition_times, timeseries="single")
                else:
                    return T1W(self.acquisition_times, timeseries="fast")
            return T1W(self.acquisition_times, timeseries="single")

        return Undetermined("no_logic", self.acquisition_times)


class GEStrategy(ModalityStrategy):
    def __init__(self, session: Session, series: Series) -> None:
        super().__init__(session, series)
        self._filter_vendor_images("image_ge")
        self._get_critical_tags("pulse_sequence", "image_type")

    def determine_sequence(self, series: Series) -> Modality:
        """Abstract method to determine the sequence type."""
        critical_test_result = self._test_critical_tags()
        if critical_test_result:
            return critical_test_result

        image_type = self.critical_tags["image_type"]

        # First DWI logic
        if self.critical_tags["pulse_sequence"] == 0:
            if isinstance(image_type, list) and len(image_type) > 0:
                if image_type[-1] == "ADC":
                    return DWI(self.acquisition_times, "adc")  # TODO: add b_values
            return DWI(self.acquisition_times, "dwi")  # TODO: with b-value info

        # T2 logic
        if self.critical_tags["pulse_sequence"] in [19, 56]:
            # TODO: requires more checks or needs to be rewritten:
            #  56 can be dixon water
            #  19 can also be dixon water or loc sequence
            return T2W(self.acquisition_times)  # TODO: with T2 info

        # For T1?: fat: (FS/NFS), timeseries (single/UF(inflow)/slow(outflow), subtraction (True/False)

        # T1 logic (and mdixon)
        if self.critical_tags["pulse_sequence"] in [1, 3, 20, 22, 66, 85, 104]:
            if isinstance(image_type, list) and len(image_type) > 0:
                if image_type[0] == "DERIVED":
                    if image_type[1] == "PRIMARY":
                        if image_type[2] == "DIXON":
                            if image_type[3] == "WATER":
                                return MDixon(self.acquisition_times, "W")
                            return MDixon(self.acquisition_times, "unknown")
                        if image_type[-1] == "SUBTRACT":
                            return T1W(self.acquisition_times, timeseries="single", subtraction=True)
                    if image_type[-1] == "MIP":
                        return MIP(self.acquisition_times, mip_type="t1w")
                    if image_type[-1] == "PROCESSED":
                        return T1W(self.acquisition_times)  # TODO: What is this for T1?

            if len(self.acquisition_times) > 1:
                mean_time_in_between = self._get_mean_time_in_between()
                if mean_time_in_between > 30:
                    return T1W(self.acquisition_times, timeseries="slow")
                if mean_time_in_between == 1 and len(self.acquisition_times) == 2:
                    "Sometimes mistake in DICOM and a single scan got to timestamps (precisely 1s apart)."
                    return T1W(self.acquisition_times, timeseries="single")
                return T1W(self.acquisition_times, timeseries="fast")
            return T1W(self.acquisition_times, timeseries="single")

        return Undetermined("no_logic", self.acquisition_times)


class UndeterminedStrategy(ModalityStrategy):
    def __init__(self, session: Session, series: Series) -> None:
        super().__init__(session, series)

    def determine_sequence(self, series: Series) -> Undetermined:
        """Abstract method to determine the sequence type."""
        return Undetermined("vendor", self.acquisition_times)


### Factory ###
MANUFACTURER_MAPPING = {"philips": PhilipsStrategy, "siemens": SiemensStrategy, "ge": GEStrategy}


class ModalityStrategyFactory:
    """Factory class to retrieve the appropriate modality strategy based on the manufacturer."""

    @staticmethod
    def get_strategy(manufacturer: str) -> Type[ModalityStrategy]:
        """
        Returns the modality strategy class based on the manufacturer.

        :param manufacturer: The name of the manufacturer.
        :return: Modality strategy class corresponding to the manufacturer, or 'Undetermined' if not found.
        """
        manufacturer = manufacturer.lower()
        for key, value in MANUFACTURER_MAPPING.items():
            if key in manufacturer:
                return value
        return UndeterminedStrategy
