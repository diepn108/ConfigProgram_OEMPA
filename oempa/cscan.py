import numpy as np


class CScanData:
    def __init__(
        self,
        data,
        x_positions,
        y_positions,
        gate_start_us,
        gate_end_us,
    ):
        self.data = np.asarray(data)
        self.x_positions = np.asarray(x_positions)
        self.y_positions = np.asarray(y_positions)
        self.gate_start_us = float(gate_start_us)
        self.gate_end_us = float(gate_end_us)

    @property
    def shape(self):
        return self.data.shape

    @property
    def minimum(self):
        return float(self.data.min())

    @property
    def maximum(self):
        return float(self.data.max())


class CScanProcessor:
    def __init__(
        self,
        gate_start_us,
        gate_end_us,
        tx_element=0,
        rx_element=0,
    ):
        self.gate_start_us = float(
            gate_start_us
        )

        self.gate_end_us = float(
            gate_end_us
        )

        self.tx_element = int(
            tx_element
        )

        self.rx_element = int(
            rx_element
        )

        if (
            self.gate_end_us
            <= self.gate_start_us
        ):
            raise ValueError(
                "Gate end must be greater "
                "than gate start."
            )

    def process(
        self,
        fmc_grid,
        time_us,
        x_positions,
        y_positions,
    ):
        fmc_grid = np.asarray(
            fmc_grid
        )

        time_us = np.asarray(
            time_us
        )

        x_positions = np.asarray(
            x_positions
        )

        y_positions = np.asarray(
            y_positions
        )

        if fmc_grid.ndim != 5:
            raise ValueError(
                "FMC grid must have shape "
                "(Y, X, TX, RX, samples)."
            )

        y_count = len(
            y_positions
        )

        x_count = len(
            x_positions
        )

        if fmc_grid.shape[0] != y_count:
            raise ValueError(
                "Y dimension does not match "
                "y_positions."
            )

        if fmc_grid.shape[1] != x_count:
            raise ValueError(
                "X dimension does not match "
                "x_positions."
            )

        if (
            self.tx_element < 0
            or self.tx_element
            >= fmc_grid.shape[2]
        ):
            raise ValueError(
                "TX element is outside "
                "the FMC data."
            )

        if (
            self.rx_element < 0
            or self.rx_element
            >= fmc_grid.shape[3]
        ):
            raise ValueError(
                "RX element is outside "
                "the FMC data."
            )

        if (
            fmc_grid.shape[4]
            != len(time_us)
        ):
            raise ValueError(
                "Sample dimension does not "
                "match the time axis."
            )

        gate_mask = (
            (time_us >= self.gate_start_us)
            & (time_us <= self.gate_end_us)
        )

        if not np.any(
            gate_mask
        ):
            raise ValueError(
                "Selected C-scan gate "
                "contains no samples."
            )

        ascans = fmc_grid[
            :,
            :,
            self.tx_element,
            self.rx_element,
            :,
        ]

        gated = ascans[
            :,
            :,
            gate_mask,
        ].astype(
            np.float32
        )

        cscan = np.max(
            np.abs(gated),
            axis=2,
        )

        return CScanData(
            data=cscan,
            x_positions=x_positions,
            y_positions=y_positions,
            gate_start_us=(
                self.gate_start_us
            ),
            gate_end_us=(
                self.gate_end_us
            ),
        )