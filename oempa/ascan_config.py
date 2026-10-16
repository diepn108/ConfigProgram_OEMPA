"""Single logical TX/RX configuration; no probe geometry or hardware imports."""

from dataclasses import dataclass
import math
from pathlib import Path


@dataclass(frozen=True)
class SingleElementAscanConfig:
    tx_element: int = 0
    rx_element: int = 0
    pulser_width_us: float = 0.5
    tx_delay_us: float = 0.0
    rx_delay_us: float = 0.0
    analog_gain_db: float = 20.0
    digital_gain_db: float = 0.0
    start_us: float = 0.0
    range_us: float = 30.0
    time_slot_us: float = 2000.0
    beam_correction_db: float = 0.0
    filter_index: int = 1
    bit_size: int = 0
    rectification: int = 0
    compression_type: int = 0

    cycle_count = 1

    @property
    def tx_aperture(self):
        return (self.tx_element,)

    @property
    def rx_aperture(self):
        return (self.rx_element,)

    def validate(self):
        for value in (self.tx_element, self.rx_element):
            if type(value) is not int or not 0 <= value <= 15:
                raise ValueError("Logical TX/RX elements must be integers 0?15.")
        values = (self.pulser_width_us, self.tx_delay_us, self.rx_delay_us, self.analog_gain_db,
                  self.digital_gain_db, self.start_us, self.range_us, self.time_slot_us, self.beam_correction_db)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Acquisition settings must be finite.")
        if self.start_us < 0 or self.range_us <= 0 or self.time_slot_us < 50:
            raise ValueError("Start must be nonnegative, range positive and TimeSlot at least 50 ?s.")
        for name, value, step, maximum in (("TX delay", self.tx_delay_us, .004, 32.764),
                                          ("RX delay", self.rx_delay_us, .005, 40.955)):
            if not 0 <= value <= maximum or not math.isclose(value / step, round(value / step), abs_tol=1e-6):
                raise ValueError(f"{name} must be within 0?{maximum} ?s in {step} ?s steps.")
        if self.pulser_width_us <= 0 or not math.isclose(self.pulser_width_us / .004, round(self.pulser_width_us / .004), abs_tol=1e-6):
            raise ValueError("Pulse width must be positive in 0.004 ?s steps.")
        if type(self.filter_index) is not int or self.filter_index < 0:
            raise ValueError("Filter index must be a nonnegative integer.")
        if (self.bit_size, self.rectification, self.compression_type) != (0, 0, 0):
            raise ValueError("Single-element mode requires Signed 8-bit Compression.")


class SingleElementAscanConfigBuilder:
    def __init__(self, config):
        config.validate()
        self.config = config

    def build_text(self):
        c = self.config
        return "\n".join([
            "[Root]", "VersionDriverOEMPA=1.1.5.4", "CycleCount=1", "EnableMultiChannel=0", "AscanBitSize=8Bits", "",
            "[Cycle:0]", f"GainDigital={c.digital_gain_db:.6f} dB", f"BeamCorrection={c.beam_correction_db:.6f} dB",
            f"Start={c.start_us:.6f} us", f"Range={c.range_us:.6f} us", f"TimeSlot={c.time_slot_us:.6f} us",
            "PointCount=0", "CompressionType=Compression", "Rectification=Signed",
            f"FilterIndex={c.filter_index}", f"GainAnalog={c.analog_gain_db:.6f} dB", "GateCount=0", "",
            "[Cycle:0\\Pulser]", "WedgeDelay=0 us", "CenterDelay=0 us", "Element.count=1", f"Element={c.tx_element}",
            "Delay.count=1;1", f"Delay={c.tx_delay_us:.6f} us", "Width.count=1", f"Width={c.pulser_width_us:.6f} us", "",
            "[Cycle:0\\Receiver]", "WedgeDelay=0 us", "CenterDelay=0 us", "Element.count=1", f"Element={c.rx_element}",
            "Focusing=Standard", "Delay.count=1;1", f"Delay={c.rx_delay_us:.6f} us", "Gain.count=1", "Gain=0 dB",
            "FocalTimeOfFlight.count=1", "FocalTimeOfFlight=0 us", "",
        ])

    def save(self, path):
        path = Path(path)
        path.write_text(self.build_text(), encoding="utf-8")
        return path
