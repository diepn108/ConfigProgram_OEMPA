"""Pure presentation of state and immutable dataset provenance."""

from oempa.probe import mapping_summary


def dataset_summary(data):
    if data is None:
        return "No dataset"
    metadata = getattr(data, "metadata", None)
    shape = " x ".join(str(n) for n in data.shape)
    if metadata is None or metadata.time_us is None:
        return f"FMC | {shape} | timing metadata incomplete"
    cycle = metadata.hardware.cycles[0]
    return (f"FMC: {shape} | Rev {metadata.configuration_revision}\n"
            f"Sampling: {cycle.sampling_hz / 1e6:g} MHz | Start: {cycle.start_s * 1e6:g} us | Range: {cycle.range_s * 1e6:g} us\n"
            f"{mapping_summary(metadata.probe)}")


def status_summary(state):
    return f"Device: {state.connection.value.capitalize()} | Mode: {state.mode} | Operation: {state.operation.value.capitalize()} | Config: {state.configuration_label} | Data: {state.dataset_label}"


def display_text(value):
    """Normalize display units only; original status/metadata remain untouched."""
    return str(value).replace("\u00b5s", "us").replace("\u03bcs", "us").replace("?s", "us")
