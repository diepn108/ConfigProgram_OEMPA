"""Offline Phase 2: pure/fake readbacks and synthetic arrays in temporary folders."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from oempa.config import FMCConfig
from oempa.dataset import capture_metadata, load_dataset, save_dataset
from oempa.fmc import FMCData
from oempa.hardware_state import AscanRequest, CycleSnapshot, HardwareSnapshot, collect_snapshot, verify_configuration
from oempa.pa_config import PAConfig, PAConfigBuilder
from ui.controller import OperationError, OperationResult
from ui.state import ApplicationState, ConnectionState, Operation
from ui_readback_fakes import FakeReadbackAPI, matching_fmc


def changed_cycle(snapshot, index=0, **values):
    cycles = list(snapshot.cycles)
    cycles[index] = replace(cycles[index], **values)
    return replace(snapshot, cycles=tuple(cycles))


def matching_pa(config):
    law = PAConfigBuilder(config).calculate_law()
    aperture = tuple(int(value) for value in law.element_indices)
    cycle = CycleSnapshot(
        cycle=0, start_s=0.0, normal_ascan_start_s=0.0, range_s=config.range_us * 1e-6,
        point_count=1501, point_factor=256, sampling_hz=50e6, compression_type=0, bit_size=0, rectification=0,
        gain_analog_db=config.analog_gain_db, gain_digital_db=config.digital_gain_db,
        beam_correction_db=config.beam_correction_db, filter_index=config.filter_index,
        time_slot_s=config.time_slot_us * 1e-6, tx_aperture=aperture, rx_aperture=aperture,
        widths_s=(config.pulser_width_us * 1e-6,) * config.element_count,
        tx_delays_s=tuple(law.tx_delays_us * 1e-6), rx_delays_s=tuple(law.rx_delays_us * 1e-6),
        rx_focusing=0, ddf_enabled=False, focal_tof_s=(0.0,), receive_gains_db=(0.0,) * config.element_count,
        emission_wedge_delay_s=0.0, reception_wedge_delay_s=0.0,
    )
    return HardwareSnapshot("PA", 1, True, False, (cycle,))


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.config = FMCConfig(tx_count=2, rx_count=2)
        self.snapshot = matching_fmc(self.config)

    def test_complete_matching_fmc_readback_verified(self):
        report = verify_configuration(self.config, self.snapshot)
        self.assertTrue(report.verified, report.mismatches)

    def test_each_requested_readback_mismatch_is_reported(self):
        for field, value in (("range_s", 20e-6), ("time_slot_s", 0.004), ("gain_digital_db", 4.0),
                             ("gain_analog_db", 25.0), ("beam_correction_db", 3.0), ("filter_index", 2),
                             ("rectification", 1), ("compression_type", 1), ("tx_aperture", (1,)),
                             ("rx_aperture", (1,)), ("widths_s", (0.7e-6,)), ("tx_delays_s", (4e-9,)),
                             ("start_s", 3e-6), ("sampling_hz", None), ("point_count", None), ("point_factor", None)):
            with self.subTest(field=field):
                report = verify_configuration(self.config, changed_cycle(self.snapshot, **{field: value}))
                self.assertFalse(report.verified)
                self.assertTrue(any(field in mismatch.field for mismatch in report.mismatches))

    def test_multiple_mismatches_preserve_actual_and_requested(self):
        snapshot = changed_cycle(self.snapshot, gain_analog_db=42.0, filter_index=3)
        report = verify_configuration(self.config, snapshot)
        names = {item.field for item in report.mismatches}
        self.assertIn("cycle[0].gain_analog_db", names)
        self.assertIn("cycle[0].filter_index", names)
        self.assertEqual(report.snapshot.cycles[0].gain_analog_db, 42.0)
        self.assertEqual(self.config.analog_gain_db, 20.0)

    def test_state_mismatch_keeps_readback_for_inspection_and_blocks(self):
        report = verify_configuration(self.config, changed_cycle(self.snapshot, filter_index=4))
        state = ApplicationState(connection=ConnectionState.CONNECTED)
        state.edit_configuration(True)
        state.begin(Operation.APPLYING)
        state.fail(Operation.APPLYING, OperationError("readback failed", report, (("filter_index", 1),)))
        self.assertFalse(state.acquisition_ready)
        self.assertEqual(state.actual_snapshot.cycles[0].filter_index, 4)
        self.assertIn("filter_index", state.verification_mismatches[0])
        self.assertEqual(state.requested_configuration, (("filter_index", 1),))

    def test_completed_unverified_report_cannot_enable_readiness(self):
        report = verify_configuration(self.config, changed_cycle(self.snapshot, filter_index=4))
        state = ApplicationState(connection=ConnectionState.CONNECTED)
        state.edit_configuration(True)
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, state.draft_revision, "FMC", OperationResult(readback_verified=True, verification=report))
        self.assertFalse(state.acquisition_ready)

    def test_unavailable_is_not_zero(self):
        missing = changed_cycle(self.snapshot, start_s=None)
        self.assertIsNone(missing.cycles[0].start_s)
        self.assertEqual(self.snapshot.cycles[0].start_s, 0.0)
        self.assertFalse(verify_configuration(self.config, missing).verified)
        self.assertTrue(verify_configuration(self.config, self.snapshot).verified)

    def test_collector_fmc_uses_multichannel_starts_not_normal_ascan(self):
        snapshot = changed_cycle(self.snapshot, normal_ascan_start_s=17e-6)
        reader = FakeReadbackAPI(snapshot)
        collected = collect_snapshot(reader, "fake", "FMC", {"cycle_count": 4, "multichannel_supported": True, "multichannel_enabled": True})
        self.assertEqual(collected.cycles[0].normal_ascan_start_s, 17e-6)
        self.assertEqual(collected.cycles[0].start_s, 0.0)
        self.assertTrue(verify_configuration(self.config, collected).verified)

    def test_collector_failed_getter_retains_none_and_failure(self):
        reader = FakeReadbackAPI(self.snapshot)
        def unavailable(*args, **kwargs):
            raise RuntimeError("not supported")
        reader.get_extended_cycle_snapshot = unavailable
        collected = collect_snapshot(reader, "fake", "FMC", {"cycle_count": 4, "multichannel_supported": True, "multichannel_enabled": True})
        self.assertIsNone(collected.cycles[0].start_s)
        self.assertIsNone(collected.cycles[0].widths_s)
        self.assertTrue(collected.read_errors)
        self.assertFalse(verify_configuration(self.config, collected).verified)

    def test_different_fmc_cycle_timing_blocks_shared_axis(self):
        report = verify_configuration(self.config, changed_cycle(self.snapshot, 1, sampling_hz=25e6))
        self.assertFalse(report.verified)
        self.assertTrue(any("shared_sampling_hz" in item.field for item in report.mismatches))

    def test_nonzero_multichannel_decimation_is_not_guessed(self):
        report = verify_configuration(self.config, changed_cycle(self.snapshot, multi_decimation_bytes=(1,) + (0,) * 7))
        self.assertFalse(report.verified)

    def test_matching_pa_is_mode_aware_and_does_not_require_multichannel(self):
        config = PAConfig(angle_deg=30, element_count=4, start_element=3, time_slot_us=2600)
        snapshot = matching_pa(config)
        reader = FakeReadbackAPI(snapshot)
        actual = collect_snapshot(reader, "fake", "PA", {"cycle_count": 1, "multichannel_supported": True, "multichannel_enabled": False})
        report = verify_configuration(config, actual)
        self.assertTrue(report.verified, report.mismatches)
        self.assertIsNone(actual.cycles[0].multi_starts_s)

    def test_pa_delays_focusing_and_ddf_mismatches(self):
        config = PAConfig(element_count=4, time_slot_us=2600)
        snapshot = changed_cycle(matching_pa(config), rx_delays_s=(0, 0, 0, 5e-9), rx_focusing=1, ddf_enabled=True)
        report = verify_configuration(config, snapshot)
        self.assertFalse(report.verified)
        self.assertTrue(any("rx_delays_s" in item.field for item in report.mismatches))
        self.assertTrue(any("ddf_enabled" in item.field for item in report.mismatches))

    def test_standalone_ascan_explicit_nonzero_start_request_verified(self):
        request = AscanRequest(6, 30, 2600, 20, 0, 0, 1, 0.5, (7,), (7,), 0, 0, 0)
        cycle = replace(self.snapshot.cycles[0], start_s=6e-6, tx_aperture=(7,), rx_aperture=(7,), time_slot_s=2600e-6)
        snapshot = HardwareSnapshot("A-scan", 1, True, False, (cycle,))
        self.assertTrue(verify_configuration(request, snapshot).verified)
        metadata = capture_metadata(np.zeros(1501, dtype=np.int8), snapshot, 3, request,
                                    SimpleNamespace(point_count=1501, data_size=1, signed=True, bit_size=0))
        np.testing.assert_allclose(metadata.time_us[:3], [6, 6.02, 6.04])
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "ascan.npy", np.zeros(1501, dtype=np.int8), metadata)
            self.assertEqual(load_dataset(path).metadata, metadata)

    def test_replay_does_not_require_pulser_or_pa_delays(self):
        snapshot = changed_cycle(self.snapshot, 1, widths_s=None, tx_delays_s=None, rx_delays_s=None)
        self.assertTrue(verify_configuration(self.config, snapshot).verified)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.config = FMCConfig(tx_count=2, rx_count=2)
        self.snapshot = matching_fmc(self.config)
        count = self.snapshot.cycles[0].point_count
        self.array = np.zeros((2, 2, count), dtype=np.int8)
        self.result = SimpleNamespace(point_count=count, data_size=1, signed=True, bit_size=0)
        self.metadata = capture_metadata(self.array, self.snapshot, 7, self.config, self.result)

    def test_non_100mhz_time_axis_from_metadata(self):
        np.testing.assert_allclose(self.metadata.time_us[:3], [0, 0.02, 0.04])
        self.assertEqual(self.metadata.timing.sampling_hz, 50e6)

    def test_nonzero_start_time_axis(self):
        snapshot = replace(self.snapshot, cycles=tuple(replace(cycle, start_s=6e-6) for cycle in self.snapshot.cycles))
        metadata = capture_metadata(self.array, snapshot, 7, self.config, self.result)
        np.testing.assert_allclose(metadata.time_us[:3], [6, 6.02, 6.04])

    def test_dataset_does_not_adopt_new_draft_or_readback(self):
        config = replace(self.config, analog_gain_db=31, range_us=50)
        new_snapshot = matching_fmc(config, 25e6)
        self.assertEqual(self.metadata.timing.gain_analog_db, 20)
        self.assertEqual(self.metadata.timing.sampling_hz, 50e6)
        self.assertEqual(dict(self.metadata.requested_parameters)["range_us"], 30)
        self.assertNotEqual(new_snapshot.cycles[0].sampling_hz, self.metadata.timing.sampling_hz)

    def test_save_load_roundtrip_and_plain_numpy_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "fmc", self.array, self.metadata)
            self.assertEqual(path.name, "fmc.npy")
            np.testing.assert_array_equal(np.load(path, allow_pickle=False), self.array)
            loaded = load_dataset(path)
            self.assertEqual(loaded.metadata, self.metadata)
            np.testing.assert_array_equal(loaded.data, self.array)
            self.assertEqual(loaded.metadata.axis_names, ("TX", "RX", "sample"))
            self.assertEqual(loaded.metadata.shape, (2, 2, 1501))
            text = json.loads(Path(str(path) + ".json").read_text())
            self.assertIsNone(text["metadata"]["probe"]["identity"])
            self.assertFalse(text["metadata"]["probe"]["mapping_verified"])

    def test_legacy_cube_loads_without_assumed_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.npy"
            np.save(path, self.array)
            dataset = load_dataset(path)
            self.assertFalse(dataset.metadata.complete)
            self.assertIsNone(dataset.metadata.hardware)
            self.assertIsNone(dataset.metadata.time_us)
            fmc = FMCData.load(path)
            self.assertIsNone(fmc.sampling_hz)
            np.testing.assert_array_equal(fmc.time_us, np.arange(1501))

    def test_fmc_save_load_uses_immutable_metadata_axis(self):
        fmc = FMCData(self.array, 2, 2, 1501, 1, True, 0, start_us=99, sampling_hz=1e6, metadata=self.metadata)
        np.testing.assert_array_equal(fmc.time_us, self.metadata.time_us)
        with tempfile.TemporaryDirectory() as directory:
            path = fmc.save(Path(directory) / "cube.npy")
            loaded = FMCData.load(path)
            self.assertEqual(loaded.metadata, self.metadata)
            np.testing.assert_array_equal(loaded.time_us, self.metadata.time_us)

    def test_wrong_hash_or_malformed_sidecar_does_not_invent_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "cube.npy", self.array, self.metadata)
            np.save(path, self.array + 1)
            loaded = load_dataset(path)
            self.assertFalse(loaded.metadata.complete)
            self.assertIn("hash", loaded.metadata.warnings[0])
            Path(str(path) + ".json").write_text("{broken", encoding="utf-8")
            self.assertFalse(load_dataset(path).metadata.complete)

    def test_mismatched_array_rejected_before_save(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "shape/dtype"):
                save_dataset(Path(directory) / "bad.npy", self.array.astype(np.int16), self.metadata)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_callback_point_count_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "point count"):
            capture_metadata(self.array, self.snapshot, 7, self.config, replace_result(self.result, point_count=10))

    def test_inconsistent_sidecar_cycles_are_metadata_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "cube.npy", self.array, self.metadata)
            sidecar = Path(str(path) + ".json")
            document = json.loads(sidecar.read_text())
            document["metadata"]["hardware"]["cycles"][1]["sampling_hz"] = 1e6
            sidecar.write_text(json.dumps(document), encoding="utf-8")
            loaded = load_dataset(path)
            self.assertFalse(loaded.metadata.complete)
            self.assertIsNone(loaded.metadata.time_us)

    def test_metadata_free_overwrite_does_not_reuse_old_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "cube.npy", self.array, self.metadata)
            FMCData(self.array, 2, 2, 1501, 1, True, 0).save(path)
            loaded = load_dataset(path)
            self.assertFalse(loaded.metadata.complete)
            self.assertIsNone(loaded.metadata.hardware)

    def test_callback_encoding_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "representation"):
            capture_metadata(self.array, self.snapshot, 7, self.config, replace_result(self.result, signed=False))

    def test_pa_focal_law_metadata_preserves_assumptions_without_physical_claims(self):
        config = PAConfig(angle_deg=30, element_count=4, start_element=3, time_slot_us=2600)
        snapshot = matching_pa(config)
        data = np.zeros(1501, dtype=np.int8)
        metadata = capture_metadata(data, snapshot, 8, config, self.result)
        self.assertEqual(metadata.mode, "PA")
        self.assertEqual(metadata.timing.tx_aperture, (3, 4, 5, 6))
        self.assertEqual(metadata.timing.rx_focusing, 0)
        self.assertEqual(metadata.timing.rx_delays_s, snapshot.cycles[0].rx_delays_s)
        self.assertEqual(dict(metadata.requested_parameters)["angle_deg"], 30)
        self.assertFalse(metadata.probe.mapping_verified)
        self.assertFalse(metadata.probe.identity_verified)
        self.assertIsNone(metadata.probe.identity)
        with tempfile.TemporaryDirectory() as directory:
            path = save_dataset(Path(directory) / "pa.npy", data, metadata)
            self.assertEqual(load_dataset(path).metadata, metadata)


def replace_result(result, **values):
    return SimpleNamespace(**(vars(result) | values))


if __name__ == "__main__":
    unittest.main()
