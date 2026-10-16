"""Pure display processing for cached FMC diagonal traces; no device access."""

from dataclasses import dataclass
import numpy as np


NORMALIZATIONS = ("None", "Global", "Per trace")
CONTRASTS = ("Linear", "Boost weak (sqrt)")


@dataclass(frozen=True)
class TraceDisplay:
    data: np.ndarray
    limit: float
    description: str


def display_traces(traces, representation="RF", normalization="None", contrast="Linear"):
    """Normalize over the supplied (possibly gated) samples, never the source array.

    Global preserves relative amplitudes between channels; Per trace scales each
    channel by its own peak and therefore removes inter-channel amplitude ratios.
    Square-root contrast preserves RF sign and boosts smaller display magnitudes.
    """
    source = np.asarray(traces)
    if source.ndim != 2 or not source.size or not np.isrealobj(source) or not np.all(np.isfinite(source)):
        raise ValueError("Display requires nonempty finite real traces.")
    if representation not in ("RF", "Absolute") or normalization not in NORMALIZATIONS or contrast not in CONTRASTS:
        raise ValueError("Unknown display processing option.")
    data = source.astype(np.float64, copy=True)
    if representation == "Absolute":
        data = np.abs(data)
    peak = float(np.max(np.abs(data)))
    limit = peak if peak > 0 else 1.0
    if normalization != "None":
        divisor = np.max(np.abs(data), axis=1, keepdims=True) if normalization == "Per trace" else peak
        np.divide(data, divisor, out=data, where=np.asarray(divisor) > 0)
        limit = 1.0
    if contrast == "Boost weak (sqrt)":
        data = np.sign(data) * np.sqrt(np.abs(data) / limit) * limit
    data.setflags(write=False)
    return TraceDisplay(data, limit, f"{normalization} normalization / {contrast} contrast - display processing only")
