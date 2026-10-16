import numpy as np


class BScanData:
    def __init__(
        self,
        data,
        time_us,
        element_indices,
    ):
        self.data = np.asarray(data)
        self.time_us = np.asarray(time_us)
        self.element_indices = np.asarray(element_indices)

    @property
    def shape(self):
        return self.data.shape

    @property
    def element_count(self):
        return self.data.shape[0]

    @property
    def point_count(self):
        return self.data.shape[1]

    @property
    def minimum(self):
        return self.data.min()

    @property
    def maximum(self):
        return self.data.max()

    @property
    def absolute(self):
        return np.abs(
            self.data.astype(np.float32)
    )

class BScanProcessor:
    def __init__(self, mode="pulse_echo"):
        self.mode = mode

        if self.mode != "pulse_echo":
            raise ValueError(
                "Currently supported B-scan mode: pulse_echo"
            )

    def process(self, fmc_data):
        if fmc_data.tx_count != fmc_data.rx_count:
            raise ValueError(
                "Pulse-echo B-scan requires matching "
                "TX and RX element counts."
            )

        element_count = min(
            fmc_data.tx_count,
            fmc_data.rx_count,
        )

        bscan = np.empty(
            (
                element_count,
                fmc_data.point_count,
            ),
            dtype=fmc_data.data.dtype,
        )

        for element in range(element_count):
            bscan[element, :] = fmc_data.get_ascan(
                element,
                element,
            )

        return BScanData(
            data=bscan,
            time_us=fmc_data.time_us.copy(),
            element_indices=np.arange(element_count),
        )