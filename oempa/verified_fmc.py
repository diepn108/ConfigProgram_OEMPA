"""Read-only inspection of the existing verified 16-by-16 FMC file."""

from configparser import ConfigParser
import hashlib
from pathlib import Path

from oempa.config import FMCConfig


APPROVED_FMC_SHA256 = "0256c4aa19fadbef561c16353af6e9508ecbee2f52a8fe810c0fb33fba0935d7"


def approved_fmc_application(path, diagnostic):
    """Construct provenance only after successful OFF load, never hardware truth."""
    from dataclasses import asdict
    from oempa.hardware_state import AppliedFMCConfiguration
    requested = inspect_approved_fmc(path)
    stages = tuple(diagnostic.get(name) for name in ("entered", "before_hw", "after_hw", "left"))
    if stages != (True, True, True, True) or diagnostic.get("parsed_cycle_count") != 256:
        raise RuntimeError("FMC load/parse completion was not established.")
    parser = ConfigParser(interpolation=None)
    parser.read_string(Path(path).read_bytes().decode("utf-8-sig"))
    flags = tuple(parser.getboolean(f"Cycle:{index}", "HWAcquisition") for index in range(256))
    return AppliedFMCConfiguration(str(Path(path).resolve()), APPROVED_FMC_SHA256, flags, tuple(asdict(requested).items()), 256, stages, True)


def inspect_approved_fmc(path):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != APPROVED_FMC_SHA256:
        raise ValueError("FMC file differs from the inspected verified 16-by-16 configuration.")
    parser = ConfigParser(interpolation=None)
    parser.read_string(data.decode("utf-8-sig"))
    root = parser["Root"]
    if int(root["CycleCount"]) != 256 or root["EnableMultiChannel"] != "1":
        raise ValueError("Expected 256-cycle MultiHWChannel FMC configuration.")
    for index in range(256):
        cycle = parser[f"Cycle:{index}"]
        receiver = parser[f"Cycle:{index}\\Receiver"]
        tx, rx = divmod(index, 16)
        if int(cycle["HWAcquisition"]) != int(rx == 0) or receiver["Element"] != str(rx) or receiver["Element.count"] != "1":
            raise ValueError(f"Invalid FMC mapping at cycle {index}.")
        if rx == 0:
            pulser = parser[f"Cycle:{index}\\Pulser"]
            if pulser["Element"] != str(tx) or pulser["Element.count"] != "1" or pulser["Width.count"] != "1" or float(pulser["Width"].split()[0]) != 0.5:
                raise ValueError(f"Invalid TX at cycle {index}.")
            # Vendor ReadFileTextMultiHWChannel defaults omitted TX delays to zero.
            if "Delay.count" in pulser or "Delay" in pulser or receiver["Start.count"] != "16" or receiver["StartFirst"] != "0":
                raise ValueError(f"Unexpected FMC TX delay/start structure at cycle {index}.")
        elif parser.has_section(f"Cycle:{index}\\Pulser"):
            raise ValueError(f"Replay cycle {index} must have no TX pulser section.")
    first = parser["Cycle:0"]
    def number(section, key):
        return float(section[key].split()[0])
    return FMCConfig(
        tx_count=16, rx_count=16, range_us=number(first, "Range"),
        time_slot_us=number(first, "HWAcquisitionTime"), analog_gain_db=number(first, "GainAnalog"),
        digital_gain_db=number(first, "GainDigital"), beam_correction_db=number(first, "BeamCorrection"),
        filter_index=int(first["FilterIndex"]), pulser_width_us=number(parser["Cycle:0\\Pulser"], "Width"),
        driver_version=root["VersionDriverOEMPA"],
    )
