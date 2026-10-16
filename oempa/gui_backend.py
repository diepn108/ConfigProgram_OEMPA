"""Worker-owned adapter for FMC and single-element A-scan GUI operations; no Tk calls."""

from concurrent.futures import CancelledError
from dataclasses import asdict, replace
import hashlib
from pathlib import Path

from oempa import api
from oempa.acquisition import OEMPAAcquisition
from oempa.config import FMCConfig, FMCConfigBuilder
from oempa.driver import OEMPADevice
from oempa.fmc import FMCProcessor
from oempa.hardware_state import FieldMismatch, HardwareSnapshot, VerificationReport, collect_snapshot, verify_configuration
from oempa.verified_pa import APPROVED_SHA256, inspect_approved_pa
from oempa.verified_fmc import APPROVED_FMC_SHA256, approved_fmc_application, inspect_approved_fmc
from oempa.dataset import AcquisitionDataset, capture_metadata
from oempa.ascan_config import SingleElementAscanConfig, SingleElementAscanConfigBuilder
from oempa.fmc_acceptance import require_first_frame, first_frame_evidence, FMCFrameRejected
from oempa.timing import FMCTiming
from ui.controller import OperationCancelled, OperationResult


class ConfigurationVerificationError(RuntimeError):
    def __init__(self, verification, requested):
        self.verification = verification
        self.requested_configuration = tuple(asdict(requested).items())
        details = tuple(str(item) for item in verification.mismatches) + tuple("Unavailable: " + item for item in verification.unavailable_required)
        mode = "A-scan" if isinstance(requested, SingleElementAscanConfig) else verification.snapshot.mode
        expected = getattr(requested, "cycle_count", 1)
        summary = (f"{mode} configuration verification failed\nExpected cycles: {expected}\n"
                   f"Observed cycles: {verification.snapshot.cycle_count}\nConfiguration was not accepted")
        summary += f"\n{len(details)} diagnostics (cycle count/configuration fields): " + "; ".join(item[:160] for item in details[:2])
        super().__init__(summary)


class GUIBackend:
    def __init__(self, config_path):
        self.config_path = config_path
        self.device = None
        self.acquisition = None
        self.applied_snapshot = None
        self.requested_configuration = None
        self.applied_fmc_provenance = None

    def connect(self, context, ip_address, port):
        context.check_cancelled()
        self.device = OEMPADevice(ip_address=ip_address, port=port)
        try:
            self.device.connect()
            self.acquisition = OEMPAAcquisition(self.device)
            return OperationResult(payload=self.device.get_status(), connected=True)
        except Exception as exc:
            try:
                self.close(context)
            except Exception as cleanup_error:
                raise RuntimeError(f"Connection failed: {exc}; cleanup failed: {cleanup_error}") from exc
            raise

    def close(self, context):
        # Cleanup must run even when cancellation was requested.
        if self.acquisition is not None:
            self.acquisition.stop()
        if self.device is not None:
            self.device.close()
        self.acquisition = None
        self.device = None
        self.applied_snapshot = None
        self.requested_configuration = None
        self.applied_fmc_provenance = None
        return OperationResult(connected=False, status="Disconnected; cleanup completed")

    def apply(self, context, config):
        requested_mode = "A-scan" if isinstance(config, SingleElementAscanConfig) else "FMC" if isinstance(config, FMCConfig) else None
        if requested_mode is None or context.mode not in {None, requested_mode}:
            raise ValueError(f"Requested configuration ({requested_mode}, {type(config).__name__}) does not match the controller acquisition mode ({context.mode}); no write attempted.")
        if isinstance(config, SingleElementAscanConfig):
            return self.apply_ascan(context, config)
        if context.mode == "FMC" and config.tx_count == config.rx_count == 16:
            path = Path(__file__).resolve().parents[1] / "configs/fmc16_full.txt"
            if config != inspect_approved_fmc(path):
                raise ValueError("Production FMC requires the unchanged verified settings in fmc16_full.txt; requested common settings differ. No write attempted.")
            return self.apply_approved_fmc_file(context, path)
        self.applied_fmc_provenance = None
        self.applied_snapshot = None
        self.requested_configuration = None
        context.check_cancelled()
        FMCConfigBuilder(config).save(self.config_path)
        context.check_cancelled()
        self.device.load_configuration(self.config_path, reconnect=True)
        context.check_cancelled()
        status = self.device.get_status()
        snapshot = collect_snapshot(api, self.device.handle, "FMC", status, context.check_cancelled)
        verification = verify_configuration(config, snapshot)
        if not verification.verified:
            raise ConfigurationVerificationError(verification, config)
        self.applied_snapshot = verification.snapshot
        self.requested_configuration = replace(config)
        return OperationResult(
            payload=(config, status), connected=True, readback_verified=True,
            verification_scope="Mode-aware supported readbacks only; physical validation excluded",
            status="Configuration applied; parameter readback passed",
            verification=verification, requested_configuration=tuple(asdict(config).items()),
        )

    def apply_approved_fmc_file(self, context, path):
        """Existing-file FMC application and callback preparation, entirely OFF."""
        self.applied_snapshot = None
        self.requested_configuration = None
        self.applied_fmc_provenance = None
        context.check_cancelled()
        path = Path(path).resolve()
        requested = inspect_approved_fmc(path)
        self.device.disable_acquisition()
        context.check_cancelled()
        if hashlib.sha256(path.read_bytes()).hexdigest() != APPROVED_FMC_SHA256:
            raise ValueError("Approved FMC file changed before hardware load.")
        self.device.load_configuration(path, reconnect=True)
        self.device.disable_acquisition()
        context.check_cancelled()
        status = self.device.get_status()
        provenance = approved_fmc_application(path, api.get_configuration_diagnostic())
        snapshot = collect_snapshot(api, self.device.handle, "FMC", status, context.check_cancelled, applied_configuration=provenance)
        verification = verify_configuration(requested, snapshot)
        if not verification.verified:
            raise ConfigurationVerificationError(verification, requested)
        snapshot = verification.snapshot
        timing = snapshot.cycles[0]
        capacity = timing.point_count * {0: 1, 1: 2, 2: 2}[timing.bit_size]
        self.acquisition.prepare(requested.cycle_count, callback_capacity_bytes=capacity)
        context.check_cancelled()
        self.applied_snapshot = snapshot
        self.requested_configuration = replace(requested)
        self.applied_fmc_provenance = provenance
        return OperationResult(
            payload=(requested, status), connected=True, readback_verified=verification.hardware_readback_verified,
            configuration_verified=verification.verified,
            verification_scope="Readable fields: hardware readback; FMC classification and base-cycle TX width/delay: applied configuration verified, hardware readback unavailable (AOS 1.1.5.4 limitation); physical mapping unverified",
            status="FMC file verified and buffers prepared; acquisition remains OFF",
            verification=verification, requested_configuration=tuple(asdict(requested).items()) + (("source_path", str(path)), ("source_sha256", APPROVED_FMC_SHA256)),
        )

    def apply_approved_pa_file(self, context, path):
        """Apply the approved unchanged file while OFF; never generate a file."""
        self.applied_snapshot = None
        self.requested_configuration = None
        self.applied_fmc_provenance = None
        context.check_cancelled()
        path = Path(path).resolve()
        requested = inspect_approved_pa(path)
        if self.device.refresh_status()["multichannel_enabled"]:
            raise RuntimeError("Approved PA file omits EnableMultiChannel; existing MultiChannel must already be disabled.")
        self.device.disable_acquisition()
        context.check_cancelled()
        if hashlib.sha256(path.read_bytes()).hexdigest() != APPROVED_SHA256:
            raise ValueError("Approved configuration changed before hardware load.")
        self.device.load_configuration(path, reconnect=True)
        self.device.disable_acquisition()
        context.check_cancelled()
        status = self.device.get_status()
        snapshot = collect_snapshot(api, self.device.handle, "PA", status, context.check_cancelled)
        verification = verify_configuration(requested, snapshot)
        mismatches = list(verification.mismatches)
        # Previously verified effective automatic output, not new GUI defaults.
        if snapshot.cycles:
            cycle = snapshot.cycles[0]
            for field, expected in (("point_count", 3001), ("point_factor", 256), ("sampling_hz", 100e6), ("bit_size", 0)):
                actual = getattr(cycle, field)
                if actual != expected:
                    mismatches.append(FieldMismatch("cycle[0]." + field, expected, actual, "approved candidate acceptance expectation"))
        verification = VerificationReport(snapshot, tuple(mismatches), verification.unchecked)
        if not verification.verified:
            raise ConfigurationVerificationError(verification, requested)
        self.applied_snapshot = snapshot
        self.requested_configuration = replace(requested)
        return OperationResult(
            payload=(requested, status), connected=True, readback_verified=True,
            verification_scope="Approved PA file parameter readback; acquisition unsupported; physical mapping unverified",
            status="Approved PA file applied and verified; acquisition remains OFF",
            verification=verification, requested_configuration=tuple(asdict(requested).items()) + (("source_path", str(path)), ("source_sha256", APPROVED_SHA256), ("file_point_count", 0)),
        )

    def acquire(self, context, config, probe=None):
        if isinstance(config, SingleElementAscanConfig):
            return self.acquire_ascan(context, config, probe)
        profile = FMCTiming()
        profile.mark('worker_start')
        self.last_fmc_timing = profile
        context.check_cancelled()
        if not isinstance(config, FMCConfig):
            raise RuntimeError("Only the verified FMC acquisition workflow is supported.")
        if self.applied_snapshot is None:
            raise RuntimeError("No verified hardware snapshot; apply before acquiring.")
        if config != self.requested_configuration:
            raise RuntimeError("Acquisition request differs from verified configuration.")
        # Measure before considering reuse; unchanged GUI state is not hardware truth.
        with profile.sdk_preparation(api, 'off_readback'):
            profile.call('initial_off', self.device.disable_acquisition)
            status = profile.call('topology_refresh', self.device.refresh_status)
            snapshot = profile.call('full_snapshot', collect_snapshot, api, self.device.handle, "FMC", status, context.check_cancelled, applied_configuration=self.applied_fmc_provenance)
        profile.mark('preflight_readback_done')
        verification = profile.call('python_verification', verify_configuration, config, snapshot)
        if not verification.verified:
            self.applied_snapshot = None
            self.applied_fmc_provenance = None
            raise ConfigurationVerificationError(verification, config)
        snapshot = verification.snapshot
        profile.mark('preflight_verified')
        strict = config.tx_count == config.rx_count == 16
        timing = snapshot.cycles[0]
        def arm_order():
            api.begin_callback_order(self.device.handle, 256, timing.point_count, {0: 1, 1: 2, 2: 2}[timing.bit_size], timing.signed, timing.bit_size)
            api.begin_fmc_first_frame(self.device.handle, timing.point_count, 1, timing.signed, timing.bit_size)
        def validate_records(complete):
            return require_first_frame(api.get_fmc_first_frame(self.device.handle), complete)
        instrumentation = dict(prepared_callback=arm_order, record_validator=validate_records,
                               poll_wait=lambda seconds: api.wait_fmc_first_frame(self.device.handle, seconds), timing=profile) if strict else {}
        try:
            result = self.acquisition.acquire(
                cycle_count=config.cycle_count, timeout_s=5.0,
                progress_callback=context.progress, cancel_event=context.cancel_event,
                callback_capacity_bytes=snapshot.cycles[0].point_count * {0: 1, 1: 2, 2: 2}[snapshot.cycles[0].bit_size],
                **instrumentation,
            )
            if strict:
                validate_records(True)
        except CancelledError as exc:
            raise OperationCancelled("Acquisition cancelled after stopping") from exc
        except Exception as exc:
            if strict:
                try:
                    stats = api.get_callback_record_stats(self.device.handle, 256)
                    order = api.get_callback_order(self.device.handle)
                    frame = api.get_fmc_first_frame(self.device.handle)
                except Exception as diagnostic_error:
                    self.last_fmc_diagnostic = {"reason": str(exc), "diagnostic_error": str(diagnostic_error)}
                    raise exc
                self.last_fmc_diagnostic = {"reason": str(exc), "stats": stats, "order": order, "first_frame": frame}
                profile.counters = dict(frame)
                raise FMCFrameRejected(exc, stats, order, frame) from exc
            raise
        finally:
            if strict:
                try:
                    profile.native_marks(api.get_fmc_timing(self.device.handle))
                except Exception as exc:
                    profile.warnings.append(f'Native timing unavailable: {exc}')
        context.check_cancelled()
        timing = snapshot.cycles[0]
        processor = FMCProcessor(tx_count=config.tx_count, rx_count=config.rx_count, start_us=timing.start_s * 1e6, sampling_hz=timing.sampling_hz)
        fmc = processor.process(result)
        profile.mark('cube_built')
        fmc.metadata = capture_metadata(fmc.data, snapshot, context.revision, config, result, probe=probe)
        if strict:
            stats = api.get_callback_record_stats(self.device.handle, 256)
            order = api.get_callback_order(self.device.handle)
            frame = api.get_fmc_first_frame(self.device.handle)
            self.last_fmc_diagnostic = {"stats": stats, "order": order, "first_frame": frame}
            profile.counters = {name: frame[name] for name in ('accepted_cycles', 'first_frame_complete', 'pre_frame_duplicates', 'unexpected_pre_frame_callbacks', 'malformed_pre_frame_callbacks', 'out_of_order_pre_frame_callbacks', 'post_frame_callback_count', 'unexpected_post_frame_callbacks', 'malformed_post_frame_callbacks', 'total_callbacks')}
            try:
                evidence = first_frame_evidence(frame, order)
            except Exception as exc:
                self.last_fmc_diagnostic['reason'] = str(exc)
                raise FMCFrameRejected(exc, stats, order, frame) from exc
            fmc.metadata = replace(fmc.metadata, acquisition_acceptance="accepted", frame_evidence=evidence)
        profile.mark('metadata_verified')
        fmc.timing = profile
        return OperationResult(payload=fmc, status="FMC acquisition complete", verification=verification)

    def _ascan_readback(self, context, status):
        # Wrong topology blocks immediately; never inspect an old FMC table as a normal cycle.
        if status["cycle_count"] != 1 or status["multichannel_enabled"] is not False:
            return HardwareSnapshot("A-scan", status["cycle_count"], status["multichannel_supported"], status["multichannel_enabled"])
        return collect_snapshot(api, self.device.handle, "A-scan", status, context.check_cancelled)

    def apply_ascan(self, context, config):
        self.applied_snapshot = None
        self.requested_configuration = None
        self.applied_fmc_provenance = None
        context.check_cancelled()
        config.validate()
        path = Path(self.config_path).with_name("gui_ascan_config.txt")
        self.device.disable_acquisition()
        SingleElementAscanConfigBuilder(config).save(path)
        context.check_cancelled()
        self.device.load_configuration(path, reconnect=True)
        self.device.disable_acquisition()
        context.check_cancelled()
        status = self.device.refresh_status()
        snapshot = self._ascan_readback(context, status)
        verification = verify_configuration(config, snapshot)
        if not verification.verified:
            raise ConfigurationVerificationError(verification, config)
        self.applied_snapshot = verification.snapshot
        self.requested_configuration = replace(config)
        return OperationResult(payload=(config, status), connected=True, readback_verified=True,
                               verification=verification, requested_configuration=tuple(asdict(config).items()),
                               status="Single-element A-scan applied/readback verified; acquisition OFF",
                               verification_scope="Single-element critical hardware readbacks; physical mapping unverified")

    def acquire_ascan(self, context, config, probe=None):
        context.check_cancelled()
        if self.applied_snapshot is None or config != self.requested_configuration:
            raise RuntimeError("Apply and verify this A-scan configuration before acquiring.")
        self.device.disable_acquisition()
        status = self.device.refresh_status()
        snapshot = self._ascan_readback(context, status)
        verification = verify_configuration(config, snapshot)
        if not verification.verified:
            self.applied_snapshot = None
            raise ConfigurationVerificationError(verification, config)
        snapshot = verification.snapshot
        try:
            result = self.acquisition.acquire(cycle_count=1, timeout_s=5.0, progress_callback=context.progress,
                                              cancel_event=context.cancel_event, callback_capacity_bytes=snapshot.cycles[0].point_count)
        except CancelledError as exc:
            raise OperationCancelled("A-scan cancelled after stopping") from exc
        context.check_cancelled()
        if result.scans.shape != (1, snapshot.cycles[0].point_count):
            raise ValueError("Single-element acquisition must contain exactly one complete cycle.")
        data = result.scans[0].copy()
        metadata = capture_metadata(data, snapshot, context.revision, config, result, probe=probe)
        return OperationResult(payload=AcquisitionDataset(data, metadata), verification=verification, status="A-scan acquisition complete")
