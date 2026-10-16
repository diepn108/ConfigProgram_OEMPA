"""Offline homogeneous-material delay-and-sum TFM, with SI-unit provenance.

The model has point elements on z=0, no wedge/refraction or delay corrections,
equal pair weights and a coherent signed sum. Logical channel order is an
explicitly unverified geometry assumption. Callback MAX data is not raw RF.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from oempa.dataset import AcquisitionDataset, AcquisitionMetadata


def _positive(value, name):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive.")


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")


@dataclass(frozen=True)
class LinearGeometry:
    element_count: int
    pitch_m: float

    def validate(self):
        _integer(self.element_count, "Element count")
        _positive(self.pitch_m, "Pitch")

    @property
    def positions_m(self):
        self.validate()
        with np.errstate(over="ignore"):
            positions = (np.arange(self.element_count) - (self.element_count - 1) / 2) * self.pitch_m
        if not np.all(np.isfinite(positions)):
            raise ValueError("Element coordinates overflow SI-unit geometry.")
        return positions


@dataclass(frozen=True)
class ImageGrid:
    x_min_m: float
    x_max_m: float
    x_count: int
    z_min_m: float
    z_max_m: float
    z_count: int

    def validate(self):
        if not all(math.isfinite(value) for value in (self.x_min_m, self.x_max_m, self.z_min_m, self.z_max_m)):
            raise ValueError("Grid limits must be finite.")
        if self.x_max_m <= self.x_min_m or self.z_max_m <= self.z_min_m or self.z_min_m < 0:
            raise ValueError("Grid requires increasing x/depth limits and depth >= 0.")
        _integer(self.x_count, "Lateral pixel count", 2)
        _integer(self.z_count, "Depth pixel count", 2)
        if self.x_count * self.z_count > 1_000_000:
            raise ValueError("Grid exceeds the CPU workspace limit of 1,000,000 pixels.")

    def coordinates(self):
        self.validate()
        return np.linspace(self.x_min_m, self.x_max_m, self.x_count), np.linspace(self.z_min_m, self.z_max_m, self.z_count)


@dataclass(frozen=True)
class TimingAssumption:
    """Explicit legacy timing; never written back into acquisition metadata."""

    sampling_hz: float
    start_s: float

    def validate(self):
        _positive(self.sampling_hz, "Sampling frequency")
        if not math.isfinite(self.start_s):
            raise ValueError("A-scan start must be finite.")


def validate_fmc(source, *, check_samples=True):
    array = np.asarray(source.data)
    if array.ndim != 3 or min(array.shape) < 1 or array.shape[0] != array.shape[1]:
        raise ValueError("Linear-array TFM requires a nonempty square FMC[TX,RX,sample] cube.")
    if array.dtype.kind not in "iuf" or (check_samples and not np.all(np.isfinite(array))):
        raise ValueError("FMC samples must be finite real numbers.")
    if tuple(array.shape) != source.metadata.shape or array.dtype.str != source.metadata.dtype:
        raise ValueError("FMC dimensions/encoding differ from source metadata.")
    if source.metadata.axis_names and source.metadata.axis_names != ("TX", "RX", "sample"):
        raise ValueError("FMC metadata must identify TX, RX, sample axes in that order.")
    return array


def resolve_timing(source, assumption=None):
    """Complete captured metadata is authoritative; legacy inputs need consent."""
    metadata = source.metadata
    if metadata.complete:
        if assumption is not None:
            raise ValueError("Captured timing cannot be overridden by reconstruction assumptions.")
        snapshot = metadata.hardware
        if metadata.mode != "FMC" or snapshot is None or snapshot.mode != "FMC" or not snapshot.cycles:
            raise ValueError("Complete FMC metadata lacks a hardware snapshot.")
        if snapshot.cycle_count != len(snapshot.cycles) or snapshot.cycle_count != source.data.shape[0] * source.data.shape[1]:
            raise ValueError("Source hardware cycle count differs from FMC dimensions.")
        first = snapshot.cycles[0]
        if first.start_s is None or first.sampling_hz is None:
            raise ValueError("Captured timing is missing.")
        for cycle in snapshot.cycles:
            if cycle.point_count != source.data.shape[-1] or cycle.start_s != first.start_s or cycle.sampling_hz != first.sampling_hz:
                raise ValueError("FMC cycles do not share the captured sample count/start/rate.")
        timing = TimingAssumption(first.sampling_hz, first.start_s)
        origin = "captured acquisition metadata"
    else:
        if assumption is None:
            raise ValueError("Metadata incomplete: explicitly enter assumed sampling frequency and A-scan start.")
        timing = assumption
        origin = "explicit user assumption; acquisition timing unverified"
    timing.validate()
    return timing, origin


def dataset_geometry(source):
    """Return active cube geometry and label provenance, without assuming a pitch.

    Probe label element count is descriptive; only the FMC axes select the active
    aperture. Missing metadata needs an explicit user pitch, never current GUI defaults.
    """
    array = validate_fmc(source, check_samples=False)
    description = source.metadata.probe.description
    value = dict(description.values).get("pitch", "") if description is not None else ""
    if not str(value).strip():
        return None, "Pitch unavailable in dataset; enter an explicit assumption."
    try:
        pitch_m = float(value) * 1e-3
    except (ValueError, TypeError):
        raise ValueError("Dataset probe pitch must be a finite positive value in mm.") from None
    geometry = LinearGeometry(array.shape[0], pitch_m)
    geometry.validate()
    origin = dict(description.sources).get("pitch", "unspecified label source")
    return geometry, f"Dataset probe metadata: {origin}; physical geometry not independently calibrated"


@dataclass(frozen=True)
class TFMRequest:
    geometry: LinearGeometry
    velocity_m_s: float
    grid: ImageGrid
    method: str = "nearest"
    timing_assumption: TimingAssumption | None = None
    geometry_origin: str = "explicit user assumption"

    def validate(self, source, *, check_samples=True):
        array = validate_fmc(source, check_samples=check_samples)
        self.geometry.validate()
        if array.shape[:2] != (self.geometry.element_count, self.geometry.element_count):
            raise ValueError("FMC dimensions are inconsistent with supplied geometry.")
        _positive(self.velocity_m_s, "Longitudinal wave velocity")
        self.grid.validate()
        if self.method not in {"nearest", "linear"}:
            raise ValueError("Reconstruction method must be nearest or linear.")
        return resolve_timing(source, self.timing_assumption)


@dataclass(frozen=True)
class TFMResult:
    image: np.ndarray
    x_m: np.ndarray
    z_m: np.ndarray
    element_x_m: np.ndarray
    request: TFMRequest
    sampling_hz: float
    start_s: float
    timing_origin: str
    source_metadata: AcquisitionMetadata
    source_label: str
    reconstructed_at_utc: str
    mapping_verified: bool = False

    @property
    def configuration_revision(self):
        return self.source_metadata.configuration_revision

    @property
    def method(self):
        return self.request.method

    @property
    def velocity_m_s(self):
        return self.request.velocity_m_s

    @property
    def pitch_m(self):
        return self.request.geometry.pitch_m

    @property
    def propagation_model(self):
        return "Homogeneous medium"

    @property
    def warnings(self):
        return self.source_metadata.warnings + (
            "Experimental reconstruction; features are not identified as defects/reflectors.",
            "Probe/channel mapping: Unverified; centered logical left-to-right ordering assumed.",
            "Homogeneous longitudinal-wave model, no wedge/refraction/delay correction.",
            f"Source buffer: {self.source_metadata.buffer_source}; not assumed pre-compression RF.",
            "Available signed callback data; quantitative/phase fidelity not independently validated.",
        )


def result_metadata(result):
    """Reproducible model/request and original acquisition provenance, not calibration."""
    return {"propagation_model": result.propagation_model, "request": asdict(result.request),
            "source_metadata": asdict(result.source_metadata), "source_label": result.source_label,
            "source_shape": result.source_metadata.shape, "source_configuration_revision": result.configuration_revision,
            "active_elements": result.request.geometry.element_count, "element_x_m": result.element_x_m.tolist(),
            "sampling_hz": result.sampling_hz, "start_s": result.start_s, "timing_origin": result.timing_origin,
            "mapping_verified": result.mapping_verified, "mapping_source": result.source_metadata.probe.mapping_source,
            "logical_to_physical": result.source_metadata.probe.logical_to_physical,
            "physical_wiring_validation": result.source_metadata.probe.physical_wiring_validation,
            "reconstructed_at_utc": result.reconstructed_at_utc, "image_shape": result.image.shape,
            "warnings": result.warnings}


def save_result(path, result):
    """Atomic NPZ with unnormalized coherent image, coordinates and embedded JSON.

    Numerical arrays and Unicode metadata can be read with allow_pickle=False.
    Saving never changes the source FMC or applies display normalization.
    """
    path = Path(path)
    if path.suffix.lower() != ".npz":
        raise ValueError("Save TFM results as .npz.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez(stream, image=result.image, x_m=result.x_m, z_m=result.z_m, element_x_m=result.element_x_m,
                     metadata_json=np.array(json.dumps(result_metadata(result), allow_nan=False)))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reconstruct(source: AcquisitionDataset, request: TFMRequest, *, source_label="FMC", cancel_check=None, progress=None, chunk_size=1024):
    """Sum samples at (distance_TX + distance_RX)/c without altering the source.

    Nearest rounds ties upward. Linear interpolates adjacent acquired samples.
    Positions outside [0,N-1] contribute zero even if nearest rounding would
    land inside. Chunked NumPy operations bound temporary storage; callbacks
    are worker progress/cancellation hooks and never device callbacks.
    """
    if cancel_check is not None:
        cancel_check()
    timing, origin = request.validate(source)
    _integer(chunk_size, "Chunk size")
    data = np.asarray(source.data)
    x, z = request.grid.coordinates()
    elements = request.geometry.positions_m
    xx, zz = np.meshgrid(x, z)
    lateral, depth = xx.ravel(), zz.ravel()
    image = np.zeros(lateral.size, dtype=np.float64)
    sample_count = data.shape[-1]
    rx = np.arange(data.shape[1])[:, None]
    for begin in range(0, image.size, chunk_size):
        if cancel_check is not None:
            cancel_check()
        end = min(begin + chunk_size, image.size)
        one_way_s = np.hypot(lateral[None, begin:end] - elements[:, None], depth[None, begin:end]) / request.velocity_m_s
        for tx in range(data.shape[0]):
            if cancel_check is not None:
                cancel_check()
            position = (one_way_s[tx][None, :] + one_way_s - timing.start_s) * timing.sampling_hz
            valid = np.isfinite(position) & (position >= 0) & (position <= sample_count - 1)
            safe = np.clip(np.where(valid, position, 0), 0, sample_count - 1)
            if request.method == "nearest":
                indices = np.floor(safe + 0.5).astype(np.intp)
                values = data[tx, rx, indices].astype(np.float64)
            else:
                low = np.floor(safe).astype(np.intp)
                high = np.minimum(low + 1, sample_count - 1)
                fraction = safe - low
                values = data[tx, rx, low].astype(np.float64) * (1 - fraction) + data[tx, rx, high].astype(np.float64) * fraction
            image[begin:end] += np.where(valid, values, 0).sum(axis=0, dtype=np.float64)
        if progress is not None:
            progress(end, image.size)
    if cancel_check is not None:
        cancel_check()
    image = image.reshape(z.size, x.size)
    for array in (image, x, z, elements):
        array.setflags(write=False)
    return TFMResult(image, x, z, elements, request, timing.sampling_hz, timing.start_s, origin, source.metadata, source_label, datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class TFMDisplay:
    values: np.ndarray
    label: str
    cmap: str
    vmin: float
    vmax: float


def display_image(result, mode="absolute", db_floor=-60.0):
    """Derived display only. dB = 20 log10(|I|/peak |I|), clipped at floor.

    An all-zero image is zero normalized magnitude or entirely the dB floor.
    This is magnitude of the coherent sum, not a Hilbert envelope.
    """
    raw = result.image
    magnitude = np.abs(raw)
    peak = float(magnitude.max())
    if mode == "raw":
        return TFMDisplay(raw, "Signed coherent sum (sample amplitude units)", "RdBu_r", -(peak or 1), peak or 1)
    if mode == "absolute":
        return TFMDisplay(magnitude, "Absolute coherent sum (sample amplitude units)", "inferno", 0, peak or 1)
    normalized = magnitude / peak if peak > 0 else np.zeros_like(raw)
    if mode == "normalized":
        return TFMDisplay(normalized, "Magnitude / image peak", "inferno", 0, 1)
    if mode == "db":
        if not math.isfinite(db_floor) or not -300 <= db_floor < 0:
            raise ValueError("dB floor must be between -300 and 0 dB (exclusive of 0).")
        values = np.maximum(20 * np.log10(np.maximum(normalized, 10 ** (db_floor / 20))), db_floor)
        return TFMDisplay(values, f"dB relative to image peak; floor {db_floor:g} dB", "inferno", db_floor, 0)
    raise ValueError("Unknown TFM display mode.")
