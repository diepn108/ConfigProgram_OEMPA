"""Read-only inspection of the approved static 0-degree PA acceptance file."""

from configparser import ConfigParser
import hashlib
from pathlib import Path

from oempa.pa_config import PAConfig


APPROVED_SHA256 = "70a13245d7231d12b5f824965e6066918e8e61137f7575446c2699364239caa9"


def inspect_approved_pa(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != APPROVED_SHA256:
        raise ValueError("PA acceptance file differs from the inspected approved 2600-us candidate.")
    parser = ConfigParser(interpolation=None)
    parser.read_string(data.decode("utf-8-sig"))
    cycle = parser["Cycle:0"]
    pulser = parser["Cycle:0\\Pulser"]

    def number(section, key):
        return float(section[key].split()[0])

    # Geometry only supports the existing zero-law comparator; not physical truth.
    return PAConfig(
        angle_deg=0, element_count=int(pulser["Element.count"]), start_element=0,
        pitch_mm=0.6, velocity_m_s=5900, range_us=number(cycle, "Range"),
        time_slot_us=number(cycle, "TimeSlot"), analog_gain_db=number(cycle, "GainAnalog"),
        digital_gain_db=number(cycle, "GainDigital"), beam_correction_db=number(cycle, "BeamCorrection"),
        filter_index=int(cycle["FilterIndex"]), pulser_width_us=number(pulser, "Width"),
        driver_version=parser["Root"]["VersionDriverOEMPA"],
    )
