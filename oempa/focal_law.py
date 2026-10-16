import numpy as np


class FocalLaw:
    def __init__(
        self,
        element_indices,
        element_positions_mm,
        ideal_delays_us,
        tx_delays_us,
        rx_delays_us,
        angle_deg,
        velocity_m_s,
        pitch_mm,
    ):
        self.element_indices = np.asarray(element_indices, dtype=int)
        self.element_positions_mm = np.asarray(element_positions_mm, dtype=float)

        self.ideal_delays_us = np.asarray(ideal_delays_us, dtype=float)
        self.tx_delays_us = np.asarray(tx_delays_us, dtype=float)
        self.rx_delays_us = np.asarray(rx_delays_us, dtype=float)

        self.angle_deg = float(angle_deg)
        self.velocity_m_s = float(velocity_m_s)
        self.pitch_mm = float(pitch_mm)


class FocalLawCalculator:
    def __init__(
        self,
        element_count,
        pitch_mm,
        velocity_m_s,
        tx_resolution_ns=4.0,
        rx_resolution_ns=5.0,
        tx_max_delay_us=32.764,
        rx_max_delay_us=40.955,
    ):
        self.element_count = int(element_count)
        self.pitch_mm = float(pitch_mm)
        self.velocity_m_s = float(velocity_m_s)

        self.tx_resolution_ns = float(tx_resolution_ns)
        self.rx_resolution_ns = float(rx_resolution_ns)

        self.tx_max_delay_us = float(tx_max_delay_us)
        self.rx_max_delay_us = float(rx_max_delay_us)

        if self.element_count <= 0:
            raise ValueError("element_count must be positive.")

        if self.pitch_mm <= 0:
            raise ValueError("pitch_mm must be positive.")

        if self.velocity_m_s <= 0:
            raise ValueError("velocity_m_s must be positive.")

        if self.tx_resolution_ns <= 0:
            raise ValueError("tx_resolution_ns must be positive.")

        if self.rx_resolution_ns <= 0:
            raise ValueError("rx_resolution_ns must be positive.")

    def element_positions_mm(
        self,
        start_element=0,
        aperture_size=None,
    ):
        start_element = int(start_element)

        if aperture_size is None:
            aperture_size = self.element_count

        aperture_size = int(aperture_size)

        if start_element < 0:
            raise ValueError("start_element cannot be negative.")

        if aperture_size <= 0:
            raise ValueError("aperture_size must be positive.")

        end_element = start_element + aperture_size

        if end_element > self.element_count:
            raise ValueError("Aperture exceeds available elements.")

        indices = np.arange(
            start_element,
            end_element,
            dtype=int,
        )

        center = start_element + (aperture_size - 1) / 2.0
        positions_mm = (indices - center) * self.pitch_mm

        return indices, positions_mm

    @staticmethod
    def _quantize(
        delays_us,
        resolution_ns,
    ):
        resolution_us = resolution_ns * 1e-3

        quantized = np.round(
            delays_us / resolution_us
        ) * resolution_us

        quantized[np.isclose(quantized, 0.0)] = 0.0

        return quantized

    def steering_delays(
        self,
        angle_deg,
        start_element=0,
        aperture_size=None,
    ):
        indices, positions_mm = self.element_positions_mm(
            start_element=start_element,
            aperture_size=aperture_size,
        )

        angle_rad = np.deg2rad(float(angle_deg))
        positions_m = positions_mm * 1e-3

        relative_time_s = (
            positions_m
            * np.sin(angle_rad)
            / self.velocity_m_s
        )

        relative_time_s -= np.min(relative_time_s)

        ideal_delays_us = relative_time_s * 1e6

        tx_delays_us = self._quantize(
            ideal_delays_us,
            self.tx_resolution_ns,
        )

        rx_delays_us = self._quantize(
            ideal_delays_us,
            self.rx_resolution_ns,
        )

        if np.max(tx_delays_us) > self.tx_max_delay_us:
            raise ValueError(
                "Calculated TX delay exceeds OEM-PA emission delay range."
            )

        if np.max(rx_delays_us) > self.rx_max_delay_us:
            raise ValueError(
                "Calculated RX delay exceeds OEM-PA reception delay range."
            )

        return FocalLaw(
            element_indices=indices,
            element_positions_mm=positions_mm,
            ideal_delays_us=ideal_delays_us,
            tx_delays_us=tx_delays_us,
            rx_delays_us=rx_delays_us,
            angle_deg=angle_deg,
            velocity_m_s=self.velocity_m_s,
            pitch_mm=self.pitch_mm,
        )