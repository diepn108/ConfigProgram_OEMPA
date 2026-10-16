"""Immutable SI-unit readbacks and mode-aware verification; no SDK import."""

from dataclasses import dataclass, fields, replace
import math


@dataclass(frozen=True)
class CycleSnapshot:
    cycle: int
    start_s: float | None = None
    normal_ascan_start_s: float | None = None
    range_s: float | None = None
    point_count: int | None = None
    point_factor: int | None = None
    sampling_hz: float | None = None
    compression_type: int | None = None
    bit_size: int | None = None
    rectification: int | None = None
    gain_analog_db: float | None = None
    gain_digital_db: float | None = None
    beam_correction_db: float | None = None
    filter_index: int | None = None
    time_slot_s: float | None = None
    tx_aperture: tuple[int, ...] | None = None
    rx_aperture: tuple[int, ...] | None = None
    widths_s: tuple[float, ...] | None = None
    tx_delays_s: tuple[float, ...] | None = None
    rx_delays_s: tuple[float, ...] | None = None
    rx_focusing: int | None = None
    ddf_enabled: bool | None = None
    focal_tof_s: tuple[float, ...] | None = None
    receive_gains_db: tuple[float, ...] | None = None
    emission_wedge_delay_s: float | None = None
    reception_wedge_delay_s: float | None = None
    hw_acquisition: bool | None = None
    multi_starts_s: tuple[float, ...] | None = None
    multi_decimation_bytes: tuple[int, ...] | None = None
    read_errors: tuple[str, ...] = ()

    @property
    def signed(self):
        return None if self.rectification is None else self.rectification == 0


@dataclass(frozen=True)
class AppliedFMCConfiguration:
    source_path: str
    source_sha256: str
    cycle_flags: tuple[bool, ...]
    requested_parameters: tuple[tuple[str, object], ...]
    parsed_cycle_count: int
    load_stages: tuple[bool, ...]
    acquisition_off: bool


@dataclass(frozen=True)
class FieldVerification:
    field: str
    status: str
    source: str
    requested: object = None
    actual: object = None
    value: object = None
    reason: str = ""


@dataclass(frozen=True)
class HardwareSnapshot:
    mode: str
    cycle_count: int | None
    multichannel_supported: bool | None
    multichannel_enabled: bool | None
    cycles: tuple[CycleSnapshot, ...] = ()
    read_errors: tuple[str, ...] = ()
    applied_configuration: AppliedFMCConfiguration | None = None
    field_verification: tuple[FieldVerification, ...] = ()


@dataclass(frozen=True)
class FieldMismatch:
    field: str
    requested: object
    actual: object
    reason: str = "mismatch"

    def __str__(self):
        return f"{self.field}: requested {self.requested!r}, readback {self.actual!r} ({self.reason})"


@dataclass(frozen=True)
class VerificationReport:
    snapshot: HardwareSnapshot
    mismatches: tuple[FieldMismatch, ...]
    unchecked: tuple[str, ...] = ()
    field_verification: tuple[FieldVerification, ...] = ()
    unavailable_required: tuple[str, ...] = ()

    @property
    def verified(self):
        return not self.mismatches and not self.unavailable_required

    @property
    def hardware_readback_verified(self):
        return self.verified and not any(item.source == "applied_configuration" for item in self.field_verification)


def usable_seeded_flag(false_read, true_read):
    """A getter must succeed and replace both valid seeds with the same state."""
    if not all(item.get("getter_success") and item.get("unlock_success") for item in (false_read, true_read)):
        return None
    first, second = false_read.get("acquisition_state"), true_read.get("acquisition_state")
    return first if isinstance(first, bool) and first == second else None


def valid_fmc_provenance(provenance, requested=None):
    from dataclasses import asdict
    from pathlib import Path
    from oempa.verified_fmc import APPROVED_FMC_SHA256
    return (
        isinstance(provenance, AppliedFMCConfiguration)
        and Path(provenance.source_path).resolve() == Path(__file__).resolve().parents[1] / "configs/fmc16_full.txt"
        and provenance.source_sha256 == APPROVED_FMC_SHA256
        and provenance.parsed_cycle_count == 256
        and provenance.load_stages == (True, True, True, True)
        and provenance.acquisition_off is True
        and provenance.cycle_flags == tuple(index % 16 == 0 for index in range(256))
        and all(isinstance(value, bool) for value in provenance.cycle_flags)
        and all(dict(provenance.requested_parameters).get(key) == value for key, value in {
            "tx_count": 16, "rx_count": 16, "range_us": 30.0, "time_slot_us": 2000.0,
            "analog_gain_db": 20.0, "digital_gain_db": 0.0, "beam_correction_db": 0.0,
            "filter_index": 1, "pulser_width_us": 0.5, "driver_version": "1.1.5.4",
        }.items())
        and (requested is None or dict(provenance.requested_parameters) == asdict(requested))
    )


@dataclass(frozen=True)
class AscanRequest:
    """Explicit standalone A-scan verification request, not a hardware writer."""
    start_us: float
    range_us: float
    time_slot_us: float
    analog_gain_db: float
    digital_gain_db: float
    beam_correction_db: float
    filter_index: int
    pulser_width_us: float
    tx_aperture: tuple[int, ...]
    rx_aperture: tuple[int, ...]
    bit_size: int
    rectification: int
    compression_type: int


class _BatchSnapshotReader:
    """Replay freshly read native outputs through the unchanged field assembly."""
    def __init__(self, batch):
        self.batch = batch

    def get_cycle_snapshot(self, handle, cycle):
        return self.batch['normal'][cycle]

    def get_extended_cycle_snapshot(self, handle, cycle, multi_channel=False):
        return self.batch['multi' if multi_channel else 'tx'][cycle]


def collect_snapshot(reader, handle, mode, status, check_cancelled=lambda: None, applied_configuration=None):
    """Reader is the existing API or a fake. Failed getters remain unavailable."""
    count = status.get("cycle_count")
    errors = []
    cycles = []
    if not isinstance(count, int) or not 0 < count <= 2047:
        return HardwareSnapshot(mode, count, status.get("multichannel_supported"), status.get("multichannel_enabled"), read_errors=("Invalid cycle count",))
    # Batch only the exact approved full FMC workflow; no cached verification.
    batch_reader = getattr(reader, 'get_fmc_snapshot_batch', None)
    if mode == "FMC" and count == 256 and valid_fmc_provenance(applied_configuration) and callable(batch_reader):
        check_cancelled()
        batch = batch_reader(handle, applied_configuration.cycle_flags)
        check_cancelled()
        if batch is not None:
            if any(batch['status'][name] != status.get(name) for name in ('cycle_count', 'multichannel_supported', 'multichannel_enabled')):
                raise RuntimeError('FMC topology changed during OFF readback; configuration not accepted')
            reader = _BatchSnapshotReader(batch)
            status = batch['status']
    names = {field.name for field in fields(CycleSnapshot)}
    for index in range(count):
        check_cancelled()
        values = {"cycle": index}
        failed = []
        def read(name, *args, **kwargs):
            try:
                return getattr(reader, name)(handle, index, *args, **kwargs)
            except (AttributeError, RuntimeError) as exc:
                failed.append(f"cycle[{index}].{name}: {exc}")
                return {}
        raw = read("get_cycle_snapshot")
        values.update({key: value for key, value in raw.items() if key in names and key != "start_s"})
        values["normal_ascan_start_s"] = raw.get("start_s")
        values["start_s"] = raw.get("start_s") if mode != "FMC" else None
        for source, target in (("tx_enabled", "tx_aperture"), ("rx_enabled", "rx_aperture")):
            enabled = raw.get(source)
            values[target] = None if enabled is None else tuple(i for i, value in enumerate(enabled) if value)
        extended = read("get_extended_cycle_snapshot", multi_channel=mode == "FMC")
        values.update({key: value for key, value in extended.items() if key in names})
        if mode == "FMC" and valid_fmc_provenance(applied_configuration) and index < 256 and applied_configuration.cycle_flags[index]:
            # Independently read TX fields; this does not enable/disable MultiHWChannel.
            emission = read("get_extended_cycle_snapshot", multi_channel=False)
            for name in ("widths_s", "tx_delays_s"):
                values[name] = emission.get(name)
        if mode in {"PA", "A-scan"}:
            values.update({key: value for key, value in read("get_pa_delay_snapshot").items() if key in names})
            receive = read("get_pa_receive_snapshot")
            values.update({key: value for key, value in receive.items() if key in names})
            values["receive_gains_db"] = receive.get("gains_db")
        for key, value in tuple(values.items()):
            if isinstance(value, list):
                values[key] = tuple(value)
        values["read_errors"] = tuple(failed)
        errors.extend(failed)
        cycles.append(CycleSnapshot(**values))
    if mode == "FMC":
        acquisition = None
        for index, cycle in enumerate(cycles):
            from_applied = valid_fmc_provenance(applied_configuration) and index < 256
            is_hw = applied_configuration.cycle_flags[index] if from_applied else cycle.hw_acquisition
            if is_hw is True:
                acquisition = cycle
            start = None
            if acquisition is not None and cycle.rx_aperture is not None and len(cycle.rx_aperture) == 1:
                rx = cycle.rx_aperture[0]
                if acquisition.multi_starts_s is not None and rx < len(acquisition.multi_starts_s):
                    start = acquisition.multi_starts_s[rx]
            cycles[index] = replace(cycle, start_s=start)
    return HardwareSnapshot(mode, count, status.get("multichannel_supported"), status.get("multichannel_enabled"), tuple(cycles), tuple(errors), applied_configuration)


def verify_configuration(requested, snapshot):
    """Compare requested fields only, and validate derived timing/encoding.

    Automatic point count/factor/rate are actual readbacks, never GUI constants.
    FMC replay cycles have no TX aperture and do not request PA receive delays.
    """
    mismatches = []
    unchecked = []
    evidence = []
    unavailable_required = []
    def compare(name, expected, actual, tolerance=0.0):
        before = len(mismatches)
        if actual is None:
            unavailable_required.append(name + " (unavailable/not read)")
        elif isinstance(expected, float):
            if not isinstance(actual, (int, float)) or not math.isfinite(actual) or not math.isclose(expected, actual, abs_tol=tolerance, rel_tol=1e-6):
                mismatches.append(FieldMismatch(name, expected, actual))
        elif actual != expected:
            mismatches.append(FieldMismatch(name, expected, actual))
        evidence.append(FieldVerification(name, "unavailable" if actual is None else "mismatch" if len(mismatches) != before else "hardware_readback_verified", "unavailable" if actual is None else "hardware_readback", expected, actual, actual))
    mode = snapshot.mode
    if mode not in {"FMC", "PA", "A-scan"}:
        mismatches.append(FieldMismatch("mode", "FMC/PA/A-scan", mode))
        return VerificationReport(snapshot, tuple(mismatches))
    expected_count = requested.cycle_count if mode == "FMC" else 1
    compare("cycle_count", expected_count, snapshot.cycle_count)
    compare("multichannel_enabled", mode == "FMC", snapshot.multichannel_enabled)
    if mode == "FMC":
        compare("multichannel_supported", True, snapshot.multichannel_supported)
    provenance_ok = mode == "FMC" and valid_fmc_provenance(snapshot.applied_configuration, requested) and expected_count == snapshot.cycle_count == 256 and snapshot.multichannel_supported is True and snapshot.multichannel_enabled is True
    def applied_tx(name, expected):
        # Only the two documented SDK-unreadable base-cycle TX fields qualify.
        evidence.append(FieldVerification(name, "applied_configuration_verified", "applied_configuration", expected, None, expected, "AOS 1.1.5.4 MultiHWChannel hardware readback unavailable; exact successful OFF file application"))
    compare("cycles.length", expected_count, len(snapshot.cycles))
    law = None
    if mode == "PA":
        from oempa.pa_config import PAConfigBuilder
        law = PAConfigBuilder(requested).calculate_law()
    for position, cycle in enumerate(snapshot.cycles):
        prefix = f"cycle[{cycle.cycle}]."
        compare(f"cycles[{position}].cycle", position, cycle.cycle)
        for field, expected in (
            ("range_s", requested.range_us * 1e-6), ("time_slot_s", requested.time_slot_us * 1e-6),
            ("gain_digital_db", requested.digital_gain_db), ("beam_correction_db", requested.beam_correction_db),
            ("filter_index", requested.filter_index), ("rectification", getattr(requested, "rectification", 0)),
            ("compression_type", getattr(requested, "compression_type", 0)),
        ):
            compare(prefix + field, expected, getattr(cycle, field), 1e-9 if field.endswith("_s") else 1e-4)
        for field in ("point_count", "point_factor", "sampling_hz"):
            value = getattr(cycle, field)
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                mismatches.append(FieldMismatch(prefix + field, "positive actual readback", value, "invalid or unavailable"))
        for field in ("point_count", "point_factor"):
            value = getattr(cycle, field)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                mismatches.append(FieldMismatch(prefix + field, "integer readback", value))
        if isinstance(cycle.point_count, int) and isinstance(cycle.sampling_hz, (float, int)) and cycle.sampling_hz > 0 and cycle.range_s is not None:
            span = (cycle.point_count - 1) / cycle.sampling_hz
            if not math.isclose(span, cycle.range_s, rel_tol=1e-6, abs_tol=1.1 / cycle.sampling_hz):
                mismatches.append(FieldMismatch(prefix + "timing_span_s", cycle.range_s, span, "point count/rate/range inconsistent"))
        if cycle.bit_size not in (0, 1, 2):
            mismatches.append(FieldMismatch(prefix + "bit_size", "supported 8/12/16-bit encoding", cycle.bit_size))
        if mode == "A-scan":
            compare(prefix + "bit_size", requested.bit_size, cycle.bit_size)
        if mode == "FMC":
            tx, rx = divmod(cycle.cycle, requested.rx_count)
            is_hw = rx == 0
            if cycle.hw_acquisition is None:
                evidence.append(FieldVerification(prefix + "hw_acquisition", "unavailable", "unavailable", is_hw, reason="AOS 1.1.5.4 getter leaves output unchanged"))
                if provenance_ok and 0 <= cycle.cycle < 256:
                    evidence.append(FieldVerification(prefix + "classification", "applied_configuration_verified", "applied_configuration", is_hw, value=snapshot.applied_configuration.cycle_flags[cycle.cycle]))
                else:
                    unavailable_required.append(prefix + "hw_acquisition (no eligible applied configuration provenance)")
            else:
                compare(prefix + "hw_acquisition", is_hw, cycle.hw_acquisition)
            compare(prefix + "rx_aperture", (rx,), cycle.rx_aperture)
            compare(prefix + "tx_aperture", (tx,) if is_hw else (), cycle.tx_aperture)
            compare(prefix + "start_s", 0.0, cycle.start_s, 1e-9)
            if provenance_ok:
                # Prior verified effective output of this exact automatic-count file.
                for field, expected in (("point_count", 3001), ("point_factor", 256), ("sampling_hz", 100e6), ("bit_size", 0)):
                    compare(prefix + field, expected, getattr(cycle, field))
                compare(prefix + "gain_analog_db", requested.analog_gain_db, cycle.gain_analog_db, 1e-4)
            if is_hw:
                compare(prefix + "gain_analog_db", requested.analog_gain_db, cycle.gain_analog_db, 1e-4)
                if cycle.multi_starts_s is None or len(cycle.multi_starts_s) != requested.rx_count:
                    mismatches.append(FieldMismatch(prefix + "multi_starts_s.length", requested.rx_count, None if cycle.multi_starts_s is None else len(cycle.multi_starts_s)))
                compare(prefix + "multi_decimation_bytes", (0,) * 8, cycle.multi_decimation_bytes)
                delays = cycle.tx_delays_s
                if delays is None and provenance_ok:
                    applied_tx(prefix + "tx_delays_s", (0.0,))
                elif delays is None or not delays:
                    unavailable_required.append(prefix + "tx_delays_s (required zero TX delay unavailable)")
                else:
                    delay = delays[0] if len(delays) == 1 else delays[tx] if tx < len(delays) else None
                    compare(prefix + "tx_delays_s", 0.0, delay, 1e-10)
            unchecked.append(prefix + "PA receive focusing/delays (not applicable to FMC replay)")
        elif mode == "PA":
            is_hw = True
            compare(prefix + "start_s", 0.0, cycle.start_s, 1e-9)
            aperture = tuple(int(value) for value in law.element_indices)
            compare(prefix + "tx_aperture", aperture, cycle.tx_aperture)
            compare(prefix + "rx_aperture", aperture, cycle.rx_aperture)
            compare(prefix + "gain_analog_db", requested.analog_gain_db, cycle.gain_analog_db, 1e-4)
            compare(prefix + "rx_focusing", 0, cycle.rx_focusing)
            compare(prefix + "ddf_enabled", False, cycle.ddf_enabled)
            compare(prefix + "focal_tof_s", (0.0,), cycle.focal_tof_s)
            for field, expected in (("tx_delays_s", law.tx_delays_us * 1e-6), ("rx_delays_s", law.rx_delays_us * 1e-6)):
                actual = getattr(cycle, field)
                if actual is None or len(actual) != len(expected):
                    mismatches.append(FieldMismatch(prefix + field, tuple(expected), actual))
                else:
                    for index, delay in enumerate(expected):
                        compare(prefix + f"{field}[{index}]", float(delay), actual[index], 1e-10)
            for field in ("emission_wedge_delay_s", "reception_wedge_delay_s"):
                compare(prefix + field, 0.0, getattr(cycle, field), 1e-10)
            compare(prefix + "receive_gains_db", (0.0,) * requested.element_count, cycle.receive_gains_db)
        else:
            is_hw = True
            compare(prefix + "start_s", requested.start_us * 1e-6, cycle.start_s, 1e-9)
            compare(prefix + "tx_aperture", requested.tx_aperture, cycle.tx_aperture)
            compare(prefix + "rx_aperture", requested.rx_aperture, cycle.rx_aperture)
            compare(prefix + "gain_analog_db", requested.analog_gain_db, cycle.gain_analog_db, 1e-4)
            if hasattr(requested, "tx_delay_us"):
                for field, delay in (("tx_delays_s", requested.tx_delay_us), ("rx_delays_s", requested.rx_delay_us)):
                    actual = getattr(cycle, field)
                    if actual is None or len(actual) != 1:
                        compare(prefix + field, (delay * 1e-6,), actual)
                    else:
                        compare(prefix + field + "[0]", delay * 1e-6, actual[0], 1e-10)
                for field, expected in (("rx_focusing", 0), ("ddf_enabled", False), ("focal_tof_s", (0.0,)),
                                        ("receive_gains_db", (0.0,)), ("emission_wedge_delay_s", 0.0), ("reception_wedge_delay_s", 0.0)):
                    compare(prefix + field, expected, getattr(cycle, field), 1e-10)
        if is_hw:
            widths = cycle.widths_s
            if widths is None and mode == "FMC" and provenance_ok:
                applied_tx(prefix + "widths_s", (requested.pulser_width_us * 1e-6,))
            elif widths is None or cycle.tx_aperture is None:
                unavailable_required.append(prefix + "widths_s (required pulser width unavailable)")
            else:
                # SDK width arrays can be full-channel or aperture-sized.
                selected = widths if len(widths) == len(cycle.tx_aperture) else tuple(widths[i] for i in cycle.tx_aperture if i < len(widths))
                if len(selected) != len(cycle.tx_aperture):
                    mismatches.append(FieldMismatch(prefix + "widths_s.length", len(cycle.tx_aperture), len(selected)))
                for index, width in enumerate(selected):
                    compare(prefix + f"widths_s[{index}]", requested.pulser_width_us * 1e-6, width, 2.1e-9)
    if snapshot.cycles:
        first = snapshot.cycles[0]
        for cycle in snapshot.cycles[1:]:
            for field in ("start_s", "range_s", "point_count", "point_factor", "sampling_hz", "bit_size", "rectification", "compression_type"):
                compare(f"cycle[{cycle.cycle}].shared_{field}", getattr(first, field), getattr(cycle, field), 1e-10)
    for error in snapshot.read_errors:
        mismatches.append(FieldMismatch("read_error", "successful readback", error, "getter failed"))
    # Derived positive readbacks also carry evidence; invalid values still block above.
    recorded = {item.field for item in evidence}
    for cycle in snapshot.cycles:
        for field in fields(CycleSnapshot):
            if field.name in {"cycle", "read_errors"}:
                continue
            name = f"cycle[{cycle.cycle}].{field.name}"
            if name not in recorded:
                value = getattr(cycle, field.name)
                status = "unavailable" if value is None else "mismatch" if any(item.field == name for item in mismatches) else "hardware_readback_verified" if field.name in {"point_count", "point_factor", "sampling_hz"} else "observed"
                evidence.append(FieldVerification(name, status, "unavailable" if value is None else "hardware_readback", actual=value, value=value))
    if provenance_ok:
        evidence = [replace(item, reason="Hardware start array selected using applied configuration grouping") if item.field.endswith(".start_s") else item for item in evidence]
    snapshot = replace(snapshot, field_verification=tuple(evidence))
    return VerificationReport(snapshot, tuple(mismatches), tuple(unchecked), tuple(evidence), tuple(unavailable_required))
