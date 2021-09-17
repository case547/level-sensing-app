import warnings
from copy import copy
from enum import Enum

import numpy as np

import acconeer.exptool as et

PEAK_MERGE_LIMIT_M = 0.005

class Processor:
    """Detector class, which does all the processing."""
    def __init__(self, sensor_config, processing_config, session_info):
        self.session_info = session_info

        self.f = sensor_config.update_rate

        num_depths = self.session_info["data_length"]

        self.current_mean_sweep = np.zeros(num_depths)
        self.last_mean_sweep = np.full(num_depths, np.nan)
        self.sweeps_since_mean = 0

        # Create an ndarray via np.linspace(range_start, range_end, num_depths)
        self.r = et.utils.get_range_depths(sensor_config, session_info)
        self.dr = self.r[1] - self.r[0]
        self.sweep_index = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        """Called to set values for the detector."""
        self.nbr_average = processing_config.nbr_average
        self.threshold_type = processing_config.threshold_type
        self.peak_sorting_method = processing_config.peak_sorting_type

        self.fixed_threshold_level = processing_config.fixed_threshold

        self.idx_cfar_pts = np.round(
            (
                processing_config.cfar_guard_cm / 100.0 / 2.0 / self.dr
                + np.arange(processing_config.cfar_window_cm / 100.0 / self.dr)
            )
        )

        self.cfar_one_sided = processing_config.cfar_one_sided
        self.cfar_sensitivity = processing_config.cfar_sensitivity

    def calculate_cfar_threshold(self, sweep, idx_cfar_pts, alpha, one_side):

        threshold = np.full(sweep.shape, np.nan)

        start_idx = np.max(idx_cfar_pts)
        if one_side:
            rel_indexes = -idx_cfar_pts
            end_idx = sweep.size
        else:
            rel_indexes = np.concatenate((-idx_cfar_pts, +idx_cfar_pts), axis=0)
            end_idx = sweep.size - start_idx

        for idx in np.arange(start_idx, end_idx):
            threshold[int(idx)] = (
                1.0 / (alpha + 1e-10) * np.mean(sweep[(idx + rel_indexes).astype(int)])
            )

        return threshold

    def find_peaks(self, sweep, threshold):

        if threshold is None or np.all(np.isnan(threshold)):
            return []

        found_peaks = []

        # Note: at least 3 samples above threshold are required to form a peak

        d = 1
        N = len(sweep)
        while d < (N - 1):
            # Skip to when threshold starts, applicable only for CFAR
            if np.isnan(threshold[d - 1]):
                d += 1
                continue

            # Break when threshold ends, applicable only for CFAR
            if np.isnan(threshold[d + 1]):
                break

            # At this point, threshold is defined (not NaN)

            # If the current point is not over threshold, the next will not be
            # a peak because 3 adjacent samples above the threshold is needed
            if sweep[d] <= threshold[d]:
                d += 2
                continue

            # Continue if previous point is not over threshold, for the same reason
            if sweep[d - 1] <= threshold[d - 1]:
                d += 1
                continue

            # Continue if this point isn't larger than the previous
            if sweep[d - 1] >= sweep[d]:
                d += 1
                continue

            # A peak is either a single point, or a plateau consisting of several equal
            # points, all over their threshold. The closest neighbouring points on each
            # side of the point/plateau must have a lower value and also be over their
            # threshold. The next step is to decide if the following point(s) are a peak:

            d_upper = d + 1
            while True:
                # If out of range or on last point
                if (d_upper) >= (N - 1):
                    break

                # If no threshold value for index d_upper
                if np.isnan(threshold[d_upper]):
                    break

                # If d_upper below threshold
                if sweep[d_upper] <= threshold[d_upper]:
                    break
                
                # Comparing d_upper with d
                if sweep[d_upper] > sweep[d]:
                    break
                elif sweep[d_upper] < sweep[d]:
                    delta = d_upper - d
                    found_peaks.append(d + int(np.ceil((delta - 1) / 2.0)))
                    break
                else:  # equal
                    d_upper += 1

            d = d_upper

        return found_peaks

    def merge_peaks(self, peak_indexes, merge_max_range):
        merged_peaks = copy(peak_indexes)

        while True:
            num_neighbours = np.zeros(len(merged_peaks))  # number of neighbours
            for i, p in enumerate(merged_peaks):
                num_neighbours[i] = np.sum(np.abs(np.array(merged_peaks) - p) < merge_max_range)

            # Find arg of first peak with max number of neighbours
            peak_i = np.argmax(num_neighbours)

            if num_neighbours[peak_i] <= 1:
                break

            peak = merged_peaks[peak_i]

            remove_mask = np.abs(np.array(merged_peaks) - peak) < merge_max_range   # the mask/condition
            peaks_to_remove = np.array(merged_peaks)[remove_mask]

            for p in peaks_to_remove:
                merged_peaks.remove(p)

            # Add back mean peak
            merged_peaks.append(int(round(np.mean(peaks_to_remove))))

            merged_peaks.sort()

        return merged_peaks

    def sort_peaks(self, peak_indexes, sweep):
        amp = np.array([sweep[int(i)] for i in peak_indexes])
        r = np.array([self.r[int(i)] for i in peak_indexes])

        PeakSorting = ProcessingConfiguration.PeakSorting
        if self.peak_sorting_method == PeakSorting.CLOSEST:
            quantity_to_sort = r
        elif self.peak_sorting_method == PeakSorting.STRONGEST:
            quantity_to_sort = -amp
        elif self.peak_sorting_method == PeakSorting.STRONGEST_REFLECTOR:
            quantity_to_sort = -amp * r ** 2
        elif self.peak_sorting_method == PeakSorting.STRONGEST_FLAT_REFLECTOR:
            quantity_to_sort = -amp * r
        else:
            raise Exception("Unknown peak sorting method")

        return [peak_indexes[i] for i in quantity_to_sort.argsort()]

    def process(self, data, data_info=None):
        """Function is called every frame and should return 
        the struct out_data, which contains all processed data.
        """
        if data_info is None:
            warnings.warn(
                "To leave out data_info or set to None is deprecated",
                DeprecationWarning,
                stacklevel=2,
            )

        sweep = data

        # Average envelope sweeps, written to handle varying nbr_average
        weight = 1.0 / (1.0 + self.sweeps_since_mean)
        self.current_mean_sweep = weight * sweep + (1.0 - weight) * self.current_mean_sweep
        self.sweeps_since_mean += 1

        # Determining threshold
        if self.threshold_type is ProcessingConfiguration.ThresholdType.FIXED:
            threshold = self.fixed_threshold_level * np.ones(sweep.size)
        elif self.threshold_type is ProcessingConfiguration.ThresholdType.CFAR:
            threshold = self.calculate_cfar_threshold(
                self.current_mean_sweep,
                self.idx_cfar_pts,
                self.cfar_sensitivity,
                self.cfar_one_sided,
            )
        else:
            print("Unknown thresholding method")

        found_peaks = None

        # If a new averaged sweep is ready for processing
        if self.sweeps_since_mean >= self.nbr_average:
            self.sweeps_since_mean = 0
            self.last_mean_sweep = self.current_mean_sweep.copy()
            self.current_mean_sweep *= 0

            # First peak-finding, then peak-merging, finally peak sorting.
            found_peaks = self.find_peaks(self.last_mean_sweep, threshold)
            if len(found_peaks) > 1:
                found_peaks = self.merge_peaks(found_peaks, np.round(PEAK_MERGE_LIMIT_M / self.dr))
                found_peaks = self.sort_peaks(found_peaks, self.last_mean_sweep)

        out_data = {
            "sweep": sweep,
            "last_mean_sweep": self.last_mean_sweep,
            "threshold": threshold,
            "sweep_index": self.sweep_index,
            "found_peaks": found_peaks,
        }

        self.sweep_index += 1

        return out_data

class ProcessingConfiguration(et.configbase.ProcessingConfig):
    """Define configuration options for detector."""
    class ThresholdType(Enum):
        FIXED = "Fixed"
        RECORDED = "Recorded"
        CFAR = "CFAR"

    class PeakSorting(Enum):
        STRONGEST = "Strongest signal"
        CLOSEST = "Closest signal"
        STRONGEST_REFLECTOR = "Strongest reflector"
        STRONGEST_FLAT_REFLECTOR = "Strongest flat reflector"

    VERSION = 1

    nbr_average = et.configbase.FloatParameter(
        label="Sweep averaging",
        default_value=5,
        limits=(1, 100),
        logscale=True,
        decimals=0,
        updateable=True,
        order=0,
        visible=True,
        help=(
            "The number of envelope sweeps to be average into one then used for"
            " distance detection."
        ),
    )

    threshold_type = et.configbase.EnumParameter(
        label="Threshold type",
        default_value=ThresholdType.FIXED,
        enum=ThresholdType,
        updateable=True,
        order=5,
        help="Setting the type of threshold",
    )

    fixed_threshold = et.configbase.FloatParameter(
        label="Fixed threshold level",
        default_value=800,
        limits=(1, 20000),
        decimals=0,
        updateable=True,
        order=10,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.FIXED,
        help=(
            "Sets the value of fixed threshold. The threshold has this constant value over"
            " the full sweep."
        ),
    )

    cfar_sensitivity = et.configbase.FloatParameter(
        label="CFAR sensitivity",
        default_value=0.5,
        limits=(0.01, 1),
        logscale=True,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        decimals=4,
        updateable=True,
        order=40,
        help=(
            "Value between 0 and 1 that sets the threshold. A low sensitivity will set a "
            "high threshold, resulting in only few false alarms but might result in "
            "missed detections."
        ),
    )

    cfar_guard_cm = et.configbase.FloatParameter(
        label="CFAR guard",
        default_value=12,
        limits=(1, 20),
        unit="cm",
        decimals=1,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=41,
        help=(
            "Range around the distance of interest that is omitted when calculating "
            "CFAR threshold. Can be low, ~4 cm, for Profile 1, and should be "
            "increased for higher Profiles."
        ),
    )

    cfar_window_cm = et.configbase.FloatParameter(
        label="CFAR window",
        default_value=3,
        limits=(0.1, 20),
        unit="cm",
        decimals=1,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=42,
        help="Range next to the CFAR guard from which the threshold level will be calculated.",
    )

    cfar_one_sided = et.configbase.BoolParameter(
        label="Use only lower distance to set threshold",
        default_value=False,
        visible=lambda conf: conf.threshold_type == conf.ThresholdType.CFAR,
        updateable=True,
        order=43,
        help=(
            "Instead of determining the CFAR threshold from sweep amplitudes from "
            "distances both closer and a farther, use only closer. Helpful e.g. for "
            "fluid level in small tanks, where many multipath signal can apprear "
            "just after the main peak."
        ),
    )

    peak_sorting_type = et.configbase.EnumParameter(
        label="Peak sorting",
        default_value=PeakSorting.STRONGEST,
        enum=PeakSorting,
        updateable=True,
        order=100,
        help="Setting the type of peak sorting method.",
    )

    history_length_s = et.configbase.FloatParameter(
        default_value=10,
        limits=(3, 1000),
        updateable=True,
        logscale=True,
        unit="s",
        label="History length",
        order=198,
        help="Length of time history for plotting.",
    )
