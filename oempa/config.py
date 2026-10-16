from dataclasses import dataclass
from pathlib import Path


@dataclass
class FMCConfig:
    tx_count: int = 16
    rx_count: int = 16

    range_us: float = 30.0
    time_slot_us: float = 2000.0

    analog_gain_db: float = 20.0
    digital_gain_db: float = 0.0
    beam_correction_db: float = 0.0

    filter_index: int = 1
    pulser_width_us: float = 0.5

    driver_version: str = "1.1.5.4"

    @property
    def cycle_count(self):
        return self.tx_count * self.rx_count

    def validate(self):
        if self.tx_count <= 0:
            raise ValueError(
                "TX count must be greater than zero."
            )

        if self.rx_count <= 0:
            raise ValueError(
                "RX count must be greater than zero."
            )

        if self.tx_count > 16:
            raise ValueError(
                "This OEM-PA supports at most 16 TX elements."
            )

        if self.rx_count > 16:
            raise ValueError(
                "This OEM-PA supports at most 16 RX elements."
            )

        if self.cycle_count > 2047:
            raise ValueError(
                "Cycle count exceeds OEM-PA maximum of 2047."
            )

        if self.range_us <= 0:
            raise ValueError(
                "A-scan range must be greater than zero."
            )

        if self.time_slot_us <= 0:
            raise ValueError(
                "Time slot must be greater than zero."
            )

        if self.pulser_width_us <= 0:
            raise ValueError(
                "Pulser width must be greater than zero."
            )

        if self.filter_index not in range(5):
            raise ValueError(
                "Filter index must be between 0 and 4."
            )


class FMCConfigBuilder:
    def __init__(self, config=None):
        if config is None:
            config = FMCConfig()

        config.validate()

        self.config = config

    def generate(self):
        self.config.validate()

        lines = []

        self._add_root(lines)

        for tx in range(
            self.config.tx_count
        ):
            base_cycle = (
                tx
                * self.config.rx_count
            )

            self._add_acquisition_cycle(
                lines,
                base_cycle,
                tx,
            )

            for rx in range(
                1,
                self.config.rx_count,
            ):
                cycle = (
                    base_cycle
                    + rx
                )

                self._add_replay_cycle(
                    lines,
                    cycle,
                    rx,
                )

        return "\n".join(lines)

    def save(self, file_path):
        file_path = Path(file_path)

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        text = self.generate()

        file_path.write_text(
            text,
            encoding="utf-8",
        )

        return file_path

    def _add_root(self, lines):
        lines.append("[Root]")

        lines.append(
            f"VersionDriverOEMPA="
            f"{self.config.driver_version}"
        )

        lines.append(
            f"CycleCount="
            f"{self.config.cycle_count}"
        )

        lines.append(
            "EnableMultiChannel=1"
        )

        lines.append("")

    def _add_common_cycle(self, lines):
        lines.append(
            f"GainDigital="
            f"{self.config.digital_gain_db:.6f} dB"
        )

        lines.append(
            f"Range="
            f"{self.config.range_us:.6f} us"
        )

        lines.append(
            "PointCount=0"
        )

        lines.append(
            "Rectification=Signed"
        )

        lines.append(
            f"FilterIndex="
            f"{self.config.filter_index}"
        )

        lines.append(
            "GateCount=0"
        )

        lines.append(
            f"BeamCorrection="
            f"{self.config.beam_correction_db:.6f} dB"
        )

    def _add_acquisition_cycle(
        self,
        lines,
        cycle,
        tx,
    ):
        lines.append(
            f"[Cycle:{cycle}]"
        )

        self._add_common_cycle(
            lines
        )

        lines.append(
            f"GainAnalog="
            f"{self.config.analog_gain_db:.6f} dB"
        )

        lines.append(
            f"HWAcquisitionTime="
            f"{self.config.time_slot_us:.6f} us"
        )

        lines.append(
            "HWAcquisition=1"
        )

        lines.append("")

        # Pulser

        lines.append(
            f"[Cycle:{cycle}\\Pulser]"
        )

        lines.append(
            "Element.count=1"
        )

        lines.append(
            f"Element={tx}"
        )

        lines.append(
            "Width.count=1"
        )

        lines.append(
            f"Width="
            f"{self.config.pulser_width_us:.6f} us"
        )

        lines.append("")

        # Receiver

        lines.append(
            f"[Cycle:{cycle}\\Receiver]"
        )

        lines.append(
            "Element.count=1"
        )

        lines.append(
            "Element=0"
        )

        lines.append(
            "StartFirst=0"
        )

        lines.append(
            f"Start.count="
            f"{self.config.rx_count}"
        )

        start_values = ";".join(
            ["0.000000 us"]
            * self.config.rx_count
        )

        lines.append(
            f"Start={start_values}"
        )

        decimation_values = ";".join(
            ["0"]
            * self.config.rx_count
        )

        lines.append(
            f"Decimation="
            f"{decimation_values}"
        )

        lines.append("")

    def _add_replay_cycle(
        self,
        lines,
        cycle,
        rx,
    ):
        lines.append(
            f"[Cycle:{cycle}]"
        )

        self._add_common_cycle(
            lines
        )

        lines.append(
            f"HWReplayTime="
            f"{self.config.time_slot_us:.6f} us"
        )

        lines.append(
            "HWAcquisition=0"
        )

        lines.append("")

        lines.append(
            f"[Cycle:{cycle}\\Receiver]"
        )

        lines.append(
            "Element.count=1"
        )

        lines.append(
            f"Element={rx}"
        )

        lines.append("")