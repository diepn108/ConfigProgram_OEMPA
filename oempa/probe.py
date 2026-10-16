"""Manual transducer description; independent of device capability and geometry."""

from dataclasses import dataclass


PROBE_DEFAULTS = {
    "brand": "AOS", "model": "F5-N32-P0.6mm", "frequency": "5.0", "elements": "32",
    "pitch": "0.6", "numbering": "1-32", "marking": "8062 C105 S2",
    "full_marking": "AOS F5-N32-P0.6mm 8062 C105 S2", "velocity": "", "wedge": "",
}

DOCUMENTED_MAPPING = tuple(range(1, 17))
MAPPING_SOURCE = "AOS SDK documentation"
MAPPING_TEXT = "AOS-defined logical 0-15 -> probe elements 1-16"
WIRING_STATUS = "Not independently tested"


def mapping_summary(probe):
    if probe is not None and getattr(probe, "mapping_source", None) == MAPPING_SOURCE:
        return f"Element mapping: {MAPPING_TEXT}; physical wiring: {probe.physical_wiring_validation}"
    return "Physical mapping: Unverified"


@dataclass(frozen=True)
class ProbeDescription:
    # Text records user descriptions; it is not a validated physical geometry.
    values: tuple[tuple[str, str], ...]
    sources: tuple[tuple[str, str], ...]
    frequency_verified: bool = False

    @classmethod
    def from_values(cls, values):
        sources = tuple((key, "inferred_unverified" if key == "frequency" and str(value) == PROBE_DEFAULTS[key]
                         else "user_supplied_label" if str(value) == PROBE_DEFAULTS[key] and value
                         else "user_entered") for key, value in values.items())
        return cls(tuple((key, str(value)) for key, value in values.items()), sources)
