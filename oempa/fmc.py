from pathlib import Path

import numpy as np


class FMCData:
    def __init__(
        self,
        data,
        tx_count,
        rx_count,
        point_count,
        data_size,
        signed,
        bit_size,
        start_us=0.0,
        sampling_hz=100e6,
        metadata=None,
    ):
        self.data = data

        self.tx_count = int(tx_count)
        self.rx_count = int(rx_count)

        self.point_count = int(point_count)
        self.data_size = int(data_size)

        self.signed = bool(signed)
        self.bit_size = None if bit_size is None else int(bit_size)

        self.start_us = None if start_us is None else float(start_us)
        self.sampling_hz = None if sampling_hz is None else float(sampling_hz)
        self.metadata = metadata

    # Shape

    @property
    def shape(self):
        return self.data.shape

    # Time axis

    @property
    def sample_interval_s(self):
        if self.metadata is not None:
            timing = self.metadata.timing
            return None if timing is None or self.metadata.time_us is None else 1.0 / timing.sampling_hz
        if self.sampling_hz is None:
            return None
        return 1.0 / self.sampling_hz

    @property
    def sample_interval_us(self):
        if self.sample_interval_s is None:
            return None
        return (
            self.sample_interval_s
            * 1e6
        )

    @property
    def time_us(self):
        if self.metadata is not None:
            axis = self.metadata.time_us
            return np.arange(self.point_count) if axis is None else axis
        if self.start_us is None or self.sampling_hz is None:
            return np.arange(self.point_count)
        return (
            self.start_us
            + np.arange(
                self.point_count
            )
            / self.sampling_hz
            * 1e6
        )

    # A-scan access

    def get_ascan(
        self,
        tx,
        rx,
    ):
        self._validate_element(
            tx,
            self.tx_count,
            "TX",
        )

        self._validate_element(
            rx,
            self.rx_count,
            "RX",
        )

        return self.data[
            tx,
            rx,
            :
        ]

    # Cycle mapping

    def cycle_from_tx_rx(
        self,
        tx,
        rx,
    ):
        self._validate_element(
            tx,
            self.tx_count,
            "TX",
        )

        self._validate_element(
            rx,
            self.rx_count,
            "RX",
        )

        return (
            tx * self.rx_count
            + rx
        )

    def tx_rx_from_cycle(
        self,
        cycle,
    ):
        cycle = int(cycle)

        cycle_count = (
            self.tx_count
            * self.rx_count
        )

        if not 0 <= cycle < cycle_count:
            raise IndexError(
                f"Cycle {cycle} is outside "
                f"0-{cycle_count - 1}."
            )

        tx = (
            cycle
            // self.rx_count
        )

        rx = (
            cycle
            % self.rx_count
        )

        return tx, rx

    # Saving

    def save(self, file_path):
        if self.metadata is not None:
            from oempa.dataset import save_dataset
            return save_dataset(file_path, self.data, self.metadata)
        file_path = Path(
            file_path
        )
        actual_path = file_path if file_path.suffix == ".npy" else Path(str(file_path) + ".npy")
        if Path(str(actual_path) + ".json").exists():
            # Explicitly clear provenance on a metadata-free overwrite, even if bytes match.
            from oempa.dataset import AcquisitionMetadata, save_dataset
            incomplete = AcquisitionMetadata("unknown", self.data.shape, self.data.dtype.str,
                                             warnings=("Metadata-free overwrite; acquisition provenance unavailable.",),
                                             axis_names=("TX", "RX", "sample"))
            return save_dataset(file_path, self.data, incomplete)

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        np.save(
            file_path,
            self.data,
        )

        return file_path

    @classmethod
    def load(cls, file_path):
        from oempa.dataset import load_dataset
        dataset = load_dataset(file_path)
        raw = dataset.data
        if raw.ndim != 3 or raw.dtype.kind not in "iu":
            raise ValueError("FMC file must contain an integer (TX, RX, N) cube.")
        timing = dataset.metadata.timing if dataset.metadata.time_us is not None else None
        return cls(raw, raw.shape[0], raw.shape[1], raw.shape[2], raw.dtype.itemsize,
                   raw.dtype.kind == "i", dataset.metadata.bit_size,
                   None if timing is None else timing.start_s * 1e6,
                   None if timing is None else timing.sampling_hz, dataset.metadata)

    # Validation

    @staticmethod
    def _validate_element(
        element,
        count,
        name,
    ):
        element = int(element)

        if not 0 <= element < count:
            raise IndexError(
                f"{name} element "
                f"{element} is outside "
                f"0-{count - 1}."
            )


class FMCProcessor:
    def __init__(
        self,
        tx_count=16,
        rx_count=16,
        start_us=0.0,
        sampling_hz=100e6,
    ):
        self.tx_count = int(
            tx_count
        )

        self.rx_count = int(
            rx_count
        )

        self.start_us = float(
            start_us
        )

        self.sampling_hz = float(
            sampling_hz
        )

        self._validate()

    @property
    def cycle_count(self):
        return (
            self.tx_count
            * self.rx_count
        )

    def process(
        self,
        acquisition_result,
    ):
        raw = acquisition_result.scans

        expected_shape = (
            self.cycle_count,
            acquisition_result.point_count,
        )

        if raw.shape != expected_shape:
            raise ValueError(
                f"Raw acquisition shape "
                f"{raw.shape} does not match "
                f"expected shape "
                f"{expected_shape}."
            )

        fmc = raw.reshape(
            self.tx_count,
            self.rx_count,
            acquisition_result.point_count,
        )

        return FMCData(
            data=fmc,
            tx_count=self.tx_count,
            rx_count=self.rx_count,
            point_count=(
                acquisition_result.point_count
            ),
            data_size=(
                acquisition_result.data_size
            ),
            signed=(
                acquisition_result.signed
            ),
            bit_size=(
                acquisition_result.bit_size
            ),
            start_us=self.start_us,
            sampling_hz=self.sampling_hz,
        )

    def _validate(self):
        if self.tx_count <= 0:
            raise ValueError(
                "TX count must be greater "
                "than zero."
            )

        if self.rx_count <= 0:
            raise ValueError(
                "RX count must be greater "
                "than zero."
            )

        if self.tx_count > 16:
            raise ValueError(
                "TX count cannot exceed 16."
            )

        if self.rx_count > 16:
            raise ValueError(
                "RX count cannot exceed 16."
            )

        if self.sampling_hz <= 0:
            raise ValueError(
                "Sampling frequency must be "
                "greater than zero."
            )
