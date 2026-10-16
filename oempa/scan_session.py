from pathlib import Path

import numpy as np

from oempa.scan_grid import ScanGrid


class ScanSession:
    def __init__(
        self,
        scan_dir,
        x_positions,
        y_positions,
        time_us,
        gate_start_us,
        gate_end_us,
        tx_element=0,
        rx_element=0,
        overwrite=False,
    ):
        self.scan_dir = Path(scan_dir)

        self.time_us = np.asarray(
            time_us,
            dtype=float,
        )

        if self.time_us.ndim != 1:
            raise ValueError(
                "time_us must be one-dimensional."
            )

        if self.time_us.size == 0:
            raise ValueError(
                "time_us cannot be empty."
            )

        self.gate_start_us = float(
            gate_start_us
        )

        self.gate_end_us = float(
            gate_end_us
        )

        if (
            self.gate_end_us
            <= self.gate_start_us
        ):
            raise ValueError(
                "Gate end must be greater "
                "than gate start."
            )

        self.tx_element = int(
            tx_element
        )

        self.rx_element = int(
            rx_element
        )

        self.grid = ScanGrid(
            scan_dir=self.scan_dir,
            x_positions=x_positions,
            y_positions=y_positions,
            overwrite=overwrite,
        )

        self.cscan_path = (
            self.scan_dir
            / "cscan.npy"
        )

        self.cscan = np.full(
            (
                self.grid.y_count,
                self.grid.x_count,
            ),
            np.nan,
            dtype=np.float32,
        )

        self._restore_completed_pixels()

    @property
    def x_positions(self):
        return self.grid.x_positions

    @property
    def y_positions(self):
        return self.grid.y_positions

    @property
    def position_count(self):
        return self.grid.position_count

    @property
    def completed_count(self):
        return self.grid.completed_count()

    @property
    def progress_percent(self):
        if self.position_count == 0:
            return 0.0

        return (
            self.completed_count
            / self.position_count
            * 100.0
        )

    def _get_gate_mask(self):
        gate_mask = (
            (
                self.time_us
                >= self.gate_start_us
            )
            & (
                self.time_us
                <= self.gate_end_us
            )
        )

        if not np.any(
            gate_mask
        ):
            raise ValueError(
                "Selected C-scan gate "
                "contains no samples."
            )

        return gate_mask

    def _extract_cscan_value(
        self,
        fmc,
    ):
        array = np.asarray(
            fmc
        )

        if array.ndim != 3:
            raise ValueError(
                "FMC data must have shape "
                "(TX, RX, samples)."
            )

        if (
            self.tx_element < 0
            or self.tx_element
            >= array.shape[0]
        ):
            raise ValueError(
                "TX element is outside "
                "the FMC data."
            )

        if (
            self.rx_element < 0
            or self.rx_element
            >= array.shape[1]
        ):
            raise ValueError(
                "RX element is outside "
                "the FMC data."
            )

        if (
            array.shape[2]
            != self.time_us.size
        ):
            raise ValueError(
                "FMC sample count does not "
                "match the time axis."
            )

        gate_mask = (
            self._get_gate_mask()
        )

        ascan = array[
            self.tx_element,
            self.rx_element,
            :,
        ].astype(
            np.float32
        )

        gated = ascan[
            gate_mask
        ]

        value = float(
            np.max(
                np.abs(
                    gated
                )
            )
        )

        return value

    def add_fmc(
        self,
        x_index,
        y_index,
        fmc_data,
    ):
        if hasattr(
            fmc_data,
            "data",
        ):
            array = np.asarray(
                fmc_data.data
            )
        else:
            array = np.asarray(
                fmc_data
            )

        value = (
            self._extract_cscan_value(
                array
            )
        )

        saved_path = (
            self.grid.save_fmc(
                x_index=x_index,
                y_index=y_index,
                fmc_data=array,
            )
        )

        self.cscan[
            y_index,
            x_index,
        ] = value

        self._save_cscan()

        return (
            saved_path,
            value,
        )

    def _save_cscan(self):
        np.save(
            self.cscan_path,
            self.cscan,
        )

    def _restore_completed_pixels(self):
        for y_index in range(
            self.grid.y_count
        ):
            for x_index in range(
                self.grid.x_count
            ):
                if not self.grid.is_complete(
                    x_index,
                    y_index,
                ):
                    continue

                fmc = self.grid.load_fmc(
                    x_index,
                    y_index,
                )

                value = (
                    self._extract_cscan_value(
                        fmc
                    )
                )

                self.cscan[
                    y_index,
                    x_index,
                ] = value

        if np.any(
            np.isfinite(
                self.cscan
            )
        ):
            self._save_cscan()

    def next_position(self):
        return (
            self.grid.next_incomplete()
        )

    def get_cscan(self):
        return self.cscan.copy()