from dataclasses import dataclass
from pathlib import Path

import numpy as np

from oempa.focal_law import FocalLawCalculator


@dataclass
class PAConfig:
    angle_deg: float = 0.0

    element_count: int = 16
    start_element: int = 0
    pitch_mm: float = 0.6

    velocity_m_s: float = 5900.0

    range_us: float = 30.0
    time_slot_us: float = 2000.0

    analog_gain_db: float = 20.0
    digital_gain_db: float = 0.0
    beam_correction_db: float = 0.0

    filter_index: int = 1
    pulser_width_us: float = 0.5

    driver_version: str = "1.1.5.4"

    def validate(self):
        if self.element_count <= 0:
            raise ValueError(
                "element_count must be positive."
            )

        if self.start_element < 0:
            raise ValueError(
                "start_element cannot be negative."
            )

        if self.start_element + self.element_count > 16:
            raise ValueError(
                "PA aperture exceeds the 16 available OEM-PA channels."
            )

        if self.pitch_mm <= 0:
            raise ValueError(
                "pitch_mm must be positive."
            )

        if self.velocity_m_s <= 0:
            raise ValueError(
                "velocity_m_s must be positive."
            )

        if self.range_us <= 0:
            raise ValueError(
                "range_us must be positive."
            )

        if self.time_slot_us <= 0:
            raise ValueError(
                "time_slot_us must be positive."
            )

        if self.pulser_width_us <= 0:
            raise ValueError(
                "pulser_width_us must be positive."
            )


class PAConfigBuilder:
    def __init__(
        self,
        config,
    ):
        self.config = config
        self.config.validate()

    @staticmethod
    def _format_array(
        values,
        decimals=6,
    ):
        return ";".join(
            f"{float(value):.{decimals}f}"
            for value in values
        )

    @staticmethod
    def _format_int_array(
        values,
    ):
        return ";".join(
            str(int(value))
            for value in values
        )

    def calculate_law(self):
        calculator = FocalLawCalculator(
            element_count=16,
            pitch_mm=self.config.pitch_mm,
            velocity_m_s=self.config.velocity_m_s,
            tx_resolution_ns=4.0,
            rx_resolution_ns=5.0,
            tx_max_delay_us=32.764,
            rx_max_delay_us=40.955,
        )

        return calculator.steering_delays(
            angle_deg=self.config.angle_deg,
            start_element=self.config.start_element,
            aperture_size=self.config.element_count,
        )

    def build_text(self):
        cfg = self.config
        law = self.calculate_law()

        elements = law.element_indices

        tx_delays = law.tx_delays_us
        rx_delays = law.rx_delays_us

        rx_gains = np.zeros(
            cfg.element_count,
            dtype=float,
        )

        widths = np.full(
            cfg.element_count,
            cfg.pulser_width_us,
            dtype=float,
        )

        lines = [
            "[Root]",
            f"VersionDriverOEMPA={cfg.driver_version}",
            "CycleCount=1",
            "",
            "[Cycle:0]",
            f"GainDigital={cfg.digital_gain_db:.6f} dB",
            f"BeamCorrection={cfg.beam_correction_db:.6f} dB",
            "Start=0.000000 us",
            f"Range={cfg.range_us:.6f} us",
            f"TimeSlot={cfg.time_slot_us:.6f} us",
            "PointCount=0",
            "CompressionType=Compression",
            "Rectification=Signed",
            f"FilterIndex={cfg.filter_index}",
            f"GainAnalog={cfg.analog_gain_db:.6f} dB",
            "GateCount=0",
            "",
            "[Cycle:0\\Pulser]",
            "WedgeDelay=0.000000 us",
            "CenterDelay=0.000000 us",
            f"Element.count={cfg.element_count}",
            "Element=" + self._format_int_array(elements),
            f"Delay.count={cfg.element_count};1",
            "Delay=" + self._format_array(tx_delays) + " us",
            f"Width.count={cfg.element_count}",
            "Width=" + self._format_array(widths) + " us",
            "",
            "[Cycle:0\\Receiver]",
            "WedgeDelay=0.000000 us",
            "CenterDelay=0.000000 us",
            f"Element.count={cfg.element_count}",
            "Element=" + self._format_int_array(elements),
            "Focusing=Standard",
            f"Delay.count={cfg.element_count};1",
            "Delay=" + self._format_array(rx_delays) + " us",
            f"Gain.count={cfg.element_count}",
            "Gain=" + self._format_array(rx_gains) + " dB",
            "FocalTimeOfFlight.count=1",
            "FocalTimeOfFlight=0.000000 us",
            "",
        ]

        return "\n".join(lines)

    def save(
        self,
        path,
    ):
        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            self.build_text(),
            encoding="utf-8",
        )

        return path