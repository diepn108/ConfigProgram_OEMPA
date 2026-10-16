"""Acquisition provenance and transparent .npy + JSON-sidecar persistence."""

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from oempa.probe import ProbeDescription
from oempa.fmc_acceptance import FMCFrameEvidence
from oempa.hardware_state import AppliedFMCConfiguration, CycleSnapshot, FieldVerification, HardwareSnapshot


@dataclass(frozen=True)
class ProbeProvenance:
    identity: str | None = None
    logical_to_physical: tuple[int, ...] | None = None
    identity_verified: bool = False
    mapping_verified: bool = False
    description: ProbeDescription | None = None
    mapping_source: str | None = None
    physical_wiring_validation: str = "Not independently tested"
    usable_element_count: int | None = None
    aperture_span_mm: float | None = None


@dataclass(frozen=True)
class AcquisitionMetadata:
    mode: str
    shape: tuple[int, ...]
    dtype: str
    hardware: HardwareSnapshot | None = None
    configuration_revision: int | None = None
    acquired_at_utc: str | None = None
    requested_parameters: tuple[tuple[str, object], ...] = ()
    probe: ProbeProvenance = ProbeProvenance()
    data_size: int | None = None
    signed: bool | None = None
    bit_size: int | None = None
    complete: bool = False
    warnings: tuple[str, ...] = ()
    axis_names: tuple[str, ...] = ()
    buffer_source: str = "unknown"
    cycle_mapping: str | None = None
    configuration_verification: str | None = None
    acquisition_acceptance: str | None = None
    frame_evidence: FMCFrameEvidence | None = None
    timing_profile: tuple[tuple[str, object], ...] = ()

    @property
    def timing(self):
        if self.hardware is None or not self.hardware.cycles:
            return None
        return self.hardware.cycles[0]

    @property
    def time_us(self):
        timing = self.timing
        if timing is None or timing.start_s is None or timing.sampling_hz is None:
            return None
        if not math.isfinite(timing.start_s) or not math.isfinite(timing.sampling_hz) or timing.sampling_hz <= 0:
            return None
        return (timing.start_s + np.arange(self.shape[-1]) / timing.sampling_hz) * 1e6


def capture_metadata(data, snapshot, revision, requested, result, probe=None):
    data = np.asarray(data)
    if not snapshot.cycles or snapshot.cycle_count != len(snapshot.cycles):
        raise ValueError("Missing acquisition readback.")
    timing = snapshot.cycles[0]
    for cycle in snapshot.cycles:
        for field in ("start_s", "sampling_hz", "point_count", "range_s", "point_factor", "compression_type", "bit_size", "rectification"):
            value = getattr(cycle, field)
            if value is None or value != getattr(timing, field):
                raise ValueError(f"Cannot share acquisition timing/encoding: {field}.")
    if timing.sampling_hz <= 0 or not math.isfinite(timing.sampling_hz) or not math.isfinite(timing.start_s):
        raise ValueError("Invalid acquisition timing.")
    if result.point_count != timing.point_count or data.shape[-1] != timing.point_count:
        raise ValueError("Callback point count differs from verified readback.")
    if result.signed != timing.signed or result.bit_size != timing.bit_size:
        raise ValueError("Callback representation differs from verified readback.")
    if data.dtype.kind not in "iu" or data.dtype.itemsize != result.data_size or (data.dtype.kind == "i") != result.signed:
        raise ValueError("Array encoding differs from callback metadata.")
    expected_bytes = {0: 1, 1: 2, 2: 2}.get(timing.bit_size)
    if result.data_size != expected_bytes:
        raise ValueError("Unsupported callback bit size/data size combination.")
    if snapshot.mode == "FMC" and (data.ndim != 3 or data.shape[:2] != (requested.tx_count, requested.rx_count)):
        raise ValueError("FMC must retain (TX, RX, N) semantics.")
    if snapshot.mode in {"PA", "A-scan"} and data.ndim not in {1, 2}:
        raise ValueError("Invalid A-scan/PA array shape.")
    parameters = tuple((field.name, getattr(requested, field.name)) for field in fields(requested))
    axes = ("TX", "RX", "sample") if snapshot.mode == "FMC" else ("sample",) if data.ndim == 1 else ("cycle", "sample")
    return AcquisitionMetadata(
        mode=snapshot.mode, shape=data.shape, dtype=data.dtype.str, hardware=snapshot,
        configuration_revision=revision, acquired_at_utc=datetime.now(timezone.utc).isoformat(),
        requested_parameters=parameters, probe=probe or ProbeProvenance(),
        data_size=result.data_size, signed=result.signed, bit_size=result.bit_size,
        complete=True, axis_names=axes, buffer_source="AOS callback pBufferMax",
        cycle_mapping=f"cycle = tx * {requested.rx_count} + rx" if snapshot.mode == "FMC" else None,
        configuration_verification="Verified (mixed sources)" if snapshot.applied_configuration is not None else "Verified",
        acquisition_acceptance=None if snapshot.mode == "FMC" else "Accepted",
    )


@dataclass(frozen=True)
class AcquisitionDataset:
    data: np.ndarray
    metadata: AcquisitionMetadata


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(path):
    path = Path(path)
    return path if path.suffix == ".npy" else Path(str(path) + ".npy")


def save_dataset(path, data, metadata):
    path = _normalized_path(path)
    array = np.asarray(data)
    if array.dtype.hasobject:
        raise ValueError("Object arrays are not acquisition data.")
    if tuple(array.shape) != metadata.shape or array.dtype.str != metadata.dtype:
        raise ValueError("Array shape/dtype does not match metadata.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths = []
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            temporary_paths.append(temporary)
            np.save(stream, array, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        document = {"schema_version": 1, "array_sha256": _digest(temporary), "metadata": asdict(metadata)}
        text = json.dumps(document, indent=2, allow_nan=False)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            sidecar_temp = Path(stream.name)
            temporary_paths.append(sidecar_temp)
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Each file replacement is atomic. Hash detects an interrupted pair update.
        os.replace(temporary, path)
        os.replace(sidecar_temp, Path(str(path) + ".json"))
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
    return path


def _decode_metadata(raw):
    def immutable(value):
        return tuple(immutable(item) for item in value) if isinstance(value, list) else value
    hardware = raw.get("hardware")
    if hardware is not None:
        cycles = []
        for item in hardware["cycles"]:
            item = {key: tuple(value) if isinstance(value, list) else value for key, value in item.items()}
            cycles.append(CycleSnapshot(**item))
        applied = hardware.get("applied_configuration")
        if applied is not None:
            applied = AppliedFMCConfiguration(**{key: immutable(value) for key, value in applied.items()})
        evidence = tuple(FieldVerification(**{key: immutable(value) for key, value in item.items()}) for item in hardware.get("field_verification", ()))
        hardware = HardwareSnapshot(
            hardware["mode"], hardware["cycle_count"], hardware["multichannel_supported"],
            hardware["multichannel_enabled"], tuple(cycles), tuple(hardware.get("read_errors", ())), applied, evidence,
        )
    probe_raw = dict(raw.get("probe", {}))
    if probe_raw.get("logical_to_physical") is not None:
        probe_raw["logical_to_physical"] = tuple(probe_raw["logical_to_physical"])
    if probe_raw.get("description") is not None:
        description = probe_raw["description"]
        probe_raw["description"] = ProbeDescription(**{key: immutable(value) for key, value in description.items()})
    values = dict(raw)
    values['timing_profile'] = immutable(raw.get('timing_profile', []))
    if raw.get('frame_evidence') is not None:
        values['frame_evidence'] = FMCFrameEvidence(**{key: immutable(value) for key, value in raw['frame_evidence'].items()})
    values.update(hardware=hardware, probe=ProbeProvenance(**probe_raw),
                  shape=tuple(raw["shape"]), requested_parameters=immutable(raw.get("requested_parameters", [])),
                  warnings=tuple(raw.get("warnings", ())), axis_names=tuple(raw.get("axis_names", ())))
    return AcquisitionMetadata(**values)


def _validate_loaded_metadata(metadata, array):
    if metadata.shape != array.shape or metadata.dtype != array.dtype.str:
        raise ValueError("sidecar shape/dtype does not match array")
    if not metadata.complete:
        return
    hardware = metadata.hardware
    if hardware is None or hardware.mode != metadata.mode or hardware.cycle_count != len(hardware.cycles):
        raise ValueError("missing or inconsistent hardware snapshot")
    timing = metadata.timing
    if metadata.time_us is None or timing.point_count != array.shape[-1]:
        raise ValueError("incomplete or invalid timing")
    for cycle in hardware.cycles:
        for field in ("start_s", "sampling_hz", "range_s", "point_count", "point_factor", "bit_size", "rectification", "compression_type"):
            if getattr(cycle, field) is None or getattr(cycle, field) != getattr(timing, field):
                raise ValueError(f"inconsistent cycle metadata: {field}")
    if metadata.mode == "FMC":
        if array.ndim != 3 or metadata.axis_names != ("TX", "RX", "sample") or hardware.cycle_count != array.shape[0] * array.shape[1]:
            raise ValueError("invalid FMC axes/cycle count")
    if metadata.mode in {"PA", "A-scan"} and array.ndim not in {1, 2}:
        raise ValueError("invalid PA/A-scan axes")
    if array.dtype.kind not in "iu" or array.dtype.itemsize != metadata.data_size or (array.dtype.kind == "i") != metadata.signed:
        raise ValueError("array encoding differs from sidecar")
    if metadata.signed != timing.signed or metadata.bit_size != timing.bit_size:
        raise ValueError("callback encoding differs from readback")


def load_dataset(path):
    path = Path(path)
    array = np.load(path, allow_pickle=False)
    sidecar = Path(str(path) + ".json")
    warning = "Legacy .npy: acquisition metadata unavailable; time axis is sample index."
    if sidecar.exists():
        try:
            document = json.loads(sidecar.read_text(encoding="utf-8"))
            if document["schema_version"] != 1 or document["array_sha256"] != _digest(path):
                raise ValueError("sidecar version/hash does not match array")
            metadata = _decode_metadata(document["metadata"])
            _validate_loaded_metadata(metadata, array)
            return AcquisitionDataset(array, metadata)
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
            warning = f"Metadata incomplete: {exc}; time axis is sample index."
    axes = ("TX", "RX", "sample") if array.ndim == 3 else ("sample",) if array.ndim == 1 else ()
    metadata = AcquisitionMetadata("unknown", array.shape, array.dtype.str, warnings=(warning,), axis_names=axes)
    return AcquisitionDataset(array, metadata)
