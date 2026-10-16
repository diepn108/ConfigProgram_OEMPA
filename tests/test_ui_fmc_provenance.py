"""Pure/fake verification and temporary persistence tests; never load SDK/device."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from oempa.dataset import capture_metadata, load_dataset, save_dataset
from oempa.hardware_state import collect_snapshot, usable_seeded_flag, verify_configuration
from oempa.verified_fmc import approved_fmc_application, inspect_approved_fmc
from ui.controller import OperationResult
from ui.state import ApplicationState, ConnectionState, Operation
from ui_readback_fakes import FakeReadbackAPI, matching_fmc


class FMCProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parents[1] / "configs/fmc16_full.txt"
        self.request = inspect_approved_fmc(self.path)
        self.truth = matching_fmc(self.request, 100e6)
        self.provenance = approved_fmc_application(self.path, FakeReadbackAPI(self.truth).get_configuration_diagnostic())
        unreadable = tuple(replace(cycle, hw_acquisition=None) for cycle in self.truth.cycles)
        unreadable = tuple(replace(cycle, gain_analog_db=self.request.analog_gain_db) for cycle in unreadable)
        self.reader = FakeReadbackAPI(replace(self.truth, cycles=unreadable))
        self.status = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        self.snapshot = collect_snapshot(self.reader, "fake", "FMC", self.status, applied_configuration=self.provenance)

    def test_seed_preserving_getter_is_unusable_not_false(self):
        false = {"getter_success": True, "unlock_success": True, "acquisition_state": False}
        true = {**false, "acquisition_state": True}
        self.assertIsNone(usable_seeded_flag(false, true))
        self.assertIs(usable_seeded_flag(false, false), False)
        self.assertIs(usable_seeded_flag(true, true), True)
        self.assertIsNone(usable_seeded_flag(false, {**false, "getter_success": False}))

    def test_unavailable_classification_preserved_with_applied_source(self):
        report = verify_configuration(self.request, self.snapshot)
        self.assertTrue(report.verified, report.mismatches)
        self.assertFalse(report.hardware_readback_verified)
        self.assertTrue(all(cycle.hw_acquisition is None for cycle in report.snapshot.cycles))
        evidence = {item.field: item for item in report.field_verification}
        self.assertEqual(evidence["cycle[0].hw_acquisition"].source, "unavailable")
        self.assertIsNone(evidence["cycle[0].hw_acquisition"].actual)
        self.assertEqual(evidence["cycle[0].classification"].source, "applied_configuration")
        self.assertTrue(evidence["cycle[0].classification"].value)
        self.assertFalse(evidence["cycle[1].classification"].value)
        self.assertEqual(evidence["cycle[0].filter_index"].source, "hardware_readback")

    def test_mixed_verification_readiness_and_honest_label(self):
        report = verify_configuration(self.request, self.snapshot)
        state = ApplicationState(connection=ConnectionState.CONNECTED, draft_valid=True)
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, 0, "FMC", OperationResult(configuration_verified=report.verified, verification=report))
        self.assertTrue(state.acquisition_ready)
        self.assertFalse(state.readback_verified)
        self.assertEqual(state.configuration_label, "Verified (mixed sources)")
        state.edit_configuration(True)
        self.assertFalse(state.acquisition_ready)

    def test_readable_mismatch_still_blocks_readiness(self):
        for field, actual in (("gain_analog_db", 19), ("filter_index", 2), ("time_slot_s", 0.003), ("point_factor", 1), ("bit_size", 2)):
            with self.subTest(field=field):
                cycles = list(self.snapshot.cycles)
                cycles[0] = replace(cycles[0], **{field: actual})
                report = verify_configuration(self.request, replace(self.snapshot, cycles=tuple(cycles)))
                self.assertFalse(report.verified)
                self.assertTrue(any(field in item.field for item in report.mismatches))
                state = ApplicationState(connection=ConnectionState.CONNECTED, draft_valid=True)
                state.begin(Operation.APPLYING)
                state.complete(Operation.APPLYING, 0, "FMC", OperationResult(configuration_verified=True, verification=report))
                self.assertFalse(state.acquisition_ready)

    def test_exception_does_not_cover_other_missing_fields(self):
        for field in ("filter_index", "time_slot_s", "tx_aperture", "rx_aperture", "gain_digital_db", "multi_starts_s", "sampling_hz"):
            with self.subTest(field=field):
                cycles = list(self.snapshot.cycles)
                cycles[0] = replace(cycles[0], **{field: None})
                report = verify_configuration(self.request, replace(self.snapshot, cycles=tuple(cycles)))
                self.assertFalse(report.verified)
                if field in {"filter_index", "time_slot_s", "tx_aperture", "rx_aperture", "gain_digital_db"}:
                    self.assertTrue(any(field in item for item in report.unavailable_required))
                    self.assertFalse(any(item.field == "cycle[0]." + field for item in report.mismatches))

    def test_unapplied_or_invalid_provenance_cannot_replace_readback(self):
        for value in (None, replace(self.provenance, acquisition_off=False), replace(self.provenance, load_stages=(True, True, False, False)), replace(self.provenance, source_sha256="invalid"), replace(self.provenance, cycle_flags=(False,) * 256)):
            with self.subTest(provenance=value):
                report = verify_configuration(self.request, replace(self.snapshot, applied_configuration=value))
                self.assertFalse(report.verified)
                self.assertTrue(report.unavailable_required)
                self.assertFalse(any(item.field.endswith(".hw_acquisition") for item in report.mismatches))
        self.assertFalse(verify_configuration(replace(self.request, tx_count=8), self.snapshot).verified)

    def test_successful_readable_flag_mismatch_is_not_ignored(self):
        cycles = list(self.snapshot.cycles)
        cycles[0] = replace(cycles[0], hw_acquisition=False)
        report = verify_configuration(self.request, replace(self.snapshot, cycles=tuple(cycles)))
        self.assertFalse(report.verified)
        self.assertTrue(any(item.field == "cycle[0].hw_acquisition" for item in report.mismatches))

    def test_start_and_emission_are_independent_hardware_readbacks(self):
        self.assertEqual(self.snapshot.cycles[255].start_s, 0.0)
        self.assertEqual(self.snapshot.cycles[240].widths_s, (0.5e-6,))
        self.assertTrue(all(cycle.hw_acquisition is None for cycle in self.snapshot.cycles))
        self.assertEqual(len(self.reader.calls), 256 * 2 + 16)

    def test_failed_apply_completion_cannot_create_provenance(self):
        with self.assertRaisesRegex(RuntimeError, "completion"):
            approved_fmc_application(self.path, {"entered": True, "before_hw": True, "after_hw": False, "left": False, "parsed_cycle_count": 256})

    def test_metadata_roundtrip_preserves_each_field_source(self):
        cycles = tuple(replace(cycle, widths_s=None, tx_delays_s=None) if cycle.cycle % 16 == 0 else cycle for cycle in self.snapshot.cycles)
        report = verify_configuration(self.request, replace(self.snapshot, cycles=cycles))
        self.assertTrue(report.verified)
        data = np.zeros((16, 16, 3001), dtype=np.int8)
        result = SimpleNamespace(point_count=3001, data_size=1, signed=True, bit_size=0)
        metadata = capture_metadata(data, report.snapshot, 7, self.request, result)
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "synthetic.npy", data, metadata)
            loaded = load_dataset(path)
        self.assertEqual(loaded.metadata, metadata)
        self.assertEqual(loaded.metadata.cycle_mapping, "cycle = tx * 16 + rx")
        self.assertTrue(np.array_equal(loaded.data, data))
        self.assertIsNone(loaded.metadata.hardware.cycles[0].hw_acquisition)
        self.assertEqual(loaded.metadata.hardware.applied_configuration.source_sha256, self.provenance.source_sha256)
        self.assertIsNone(loaded.metadata.hardware.cycles[0].widths_s)
        self.assertIsNone(loaded.metadata.hardware.cycles[0].tx_delays_s)
        evidence = {item.field: item for item in loaded.metadata.hardware.field_verification}
        for field in ("widths_s", "tx_delays_s", "classification"):
            self.assertEqual(evidence["cycle[0]." + field].source, "applied_configuration")
            self.assertIsNone(evidence["cycle[0]." + field].actual)
        self.assertFalse(loaded.metadata.probe.mapping_verified)

    def test_only_documented_base_tx_fields_can_use_provenance(self):
        cycles = tuple(replace(cycle, widths_s=None, tx_delays_s=None) if cycle.cycle % 16 == 0 else cycle for cycle in self.snapshot.cycles)
        snapshot = replace(self.snapshot, cycles=cycles)
        report = verify_configuration(self.request, snapshot)
        self.assertTrue(report.verified, (report.mismatches, report.unavailable_required))
        for cycle in report.snapshot.cycles:
            if cycle.cycle % 16 == 0:
                self.assertIsNone(cycle.widths_s)
                self.assertIsNone(cycle.tx_delays_s)
        applied = {item.field for item in report.field_verification if item.source == "applied_configuration"}
        self.assertEqual(applied, {f"cycle[{index}].classification" for index in range(256)} | {f"cycle[{index}].{field}" for index in range(0, 256, 16) for field in ("widths_s", "tx_delays_s")})
        for bad in (None, replace(self.provenance, acquisition_off=False), replace(self.provenance, source_path="other.txt")):
            blocked = verify_configuration(self.request, replace(snapshot, applied_configuration=bad))
            self.assertFalse(blocked.verified)
            self.assertTrue(any("widths_s" in field for field in blocked.unavailable_required))
            self.assertTrue(any("tx_delays_s" in field for field in blocked.unavailable_required))

    def test_tx_provenance_cannot_mask_readable_tx_or_acquisition_mismatch(self):
        cycles = tuple(replace(cycle, widths_s=None, tx_delays_s=None) if cycle.cycle % 16 == 0 else cycle for cycle in self.snapshot.cycles)
        for field, value in (("widths_s", (1e-6,)), ("tx_delays_s", (4e-9,)), ("tx_aperture", (1,)), ("filter_index", 2), ("gain_analog_db", 19), ("time_slot_s", 0.003), ("point_count", 3000)):
            with self.subTest(field=field):
                changed = (replace(cycles[0], **{field: value}),) + cycles[1:]
                report = verify_configuration(self.request, replace(self.snapshot, cycles=changed))
                self.assertFalse(report.verified)
                self.assertTrue(any(field in item.field for item in report.mismatches))

    def test_tx_exception_does_not_apply_to_pa_or_unapproved_fmc(self):
        cycles = tuple(replace(cycle, widths_s=None, tx_delays_s=None) for cycle in self.snapshot.cycles)
        for snapshot in (replace(self.snapshot, cycles=cycles, applied_configuration=None), replace(self.snapshot, cycles=cycles, multichannel_enabled=False)):
            self.assertFalse(verify_configuration(self.request, snapshot).verified)
        from oempa.pa_config import PAConfig
        pa = replace(self.snapshot, mode="PA", cycle_count=1, multichannel_enabled=False, cycles=(replace(cycles[0], tx_aperture=tuple(range(16)), rx_aperture=tuple(range(16))),))
        report = verify_configuration(PAConfig(), pa)
        self.assertFalse(report.verified)
        self.assertFalse(any(item.source == "applied_configuration" for item in report.field_verification))
