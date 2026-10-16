"""Single-element software-only tests: fake API and synthetic data, no native imports."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np

import test_ui_backend_offline as backend_fixture
from oempa.ascan_config import SingleElementAscanConfig, SingleElementAscanConfigBuilder
from oempa.hardware_state import CycleSnapshot, HardwareSnapshot, collect_snapshot, verify_configuration
from oempa.dataset import capture_metadata, save_dataset, load_dataset
from ui.state import ApplicationState, ConnectionState, Operation
from ui.controller import OperationResult
from ui_readback_fakes import FakeReadbackAPI


def matching(config):
    cycle = CycleSnapshot(cycle=0, start_s=config.start_us * 1e-6, normal_ascan_start_s=config.start_us * 1e-6,
        range_s=config.range_us * 1e-6, point_count=751, point_factor=256, sampling_hz=25e6,
        compression_type=0, bit_size=0, rectification=0, gain_analog_db=config.analog_gain_db,
        gain_digital_db=config.digital_gain_db, beam_correction_db=0.0, filter_index=config.filter_index,
        time_slot_s=config.time_slot_us * 1e-6, tx_aperture=config.tx_aperture, rx_aperture=config.rx_aperture,
        widths_s=(config.pulser_width_us * 1e-6,), tx_delays_s=(config.tx_delay_us * 1e-6,),
        rx_delays_s=(config.rx_delay_us * 1e-6,), rx_focusing=0, ddf_enabled=False, focal_tof_s=(0.0,),
        receive_gains_db=(0.0,), emission_wedge_delay_s=0.0, reception_wedge_delay_s=0.0)
    return HardwareSnapshot("A-scan", 1, True, False, (cycle,))


class SingleElementTests(unittest.TestCase):
    def test_builder_explicit_normal_single_cycle_without_fmc(self):
        c = SingleElementAscanConfig(tx_element=3, rx_element=7, tx_delay_us=.008, rx_delay_us=.015, start_us=2)
        text = SingleElementAscanConfigBuilder(c).build_text()
        self.assertIn("CycleCount=1", text)
        self.assertIn("EnableMultiChannel=0", text)
        self.assertEqual(text.count("Element.count=1"), 2)
        self.assertIn("Element=3", text)
        self.assertIn("Element=7", text)
        self.assertIn("Delay=0.008000 us", text)
        self.assertIn("Delay=0.015000 us", text)
        self.assertNotIn("HWAcquisition", text)
        self.assertNotIn("EnableFMC", text)
        self.assertIn("AscanBitSize=8Bits", text)

    def test_invalid_values_are_rejected_without_rounding(self):
        for values in (dict(tx_element=16), dict(rx_element=-1), dict(tx_delay_us=.001), dict(rx_delay_us=.004),
                       dict(pulser_width_us=.501), dict(start_us=-1), dict(range_us=0), dict(analog_gain_db=float('nan'))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SingleElementAscanConfigBuilder(SingleElementAscanConfig(**values))

    def test_readback_verifies_all_single_element_critical_fields(self):
        c = SingleElementAscanConfig(tx_element=3, rx_element=7, start_us=2, tx_delay_us=.008, rx_delay_us=.015)
        reader = FakeReadbackAPI(matching(c))
        snapshot = collect_snapshot(reader, 'fake', 'A-scan', dict(cycle_count=1, multichannel_supported=True, multichannel_enabled=False))
        report = verify_configuration(c, snapshot)
        self.assertTrue(report.hardware_readback_verified, report.mismatches)
        self.assertFalse(any(f.source == 'applied_configuration' for f in report.field_verification))

    def test_missing_or_mismatching_critical_fields_never_get_provenance_exception(self):
        c = SingleElementAscanConfig()
        snap = matching(c)
        for field, wrong in (("tx_aperture", (1,)), ("rx_aperture", (1,)), ("tx_delays_s", (.004e-6,)),
                             ("rx_delays_s", (.005e-6,)), ("widths_s", (.7e-6,)), ("gain_analog_db", 21.),
                             ("gain_digital_db", 1.), ("start_s", 2e-6), ("rx_focusing", 1), ("ddf_enabled", True),
                             ("rectification", 1), ("bit_size", 1), ("sampling_hz", None)):
            for value in (wrong, None):
                with self.subTest(field=field, value=value):
                    changed = replace(snap, cycles=(replace(snap.cycles[0], **{field: value}),))
                    self.assertFalse(verify_configuration(c, changed).verified)
        self.assertFalse(verify_configuration(c, replace(snap, multichannel_enabled=True)).verified)

    def test_state_requires_readback_then_edit_stales_original_metadata(self):
        c = SingleElementAscanConfig()
        report = verify_configuration(c, matching(c))
        state = ApplicationState(mode='A-scan', hardware_modes=frozenset({'A-scan', 'FMC'}))
        state.edit_configuration(True)
        self.assertFalse(state.acquisition_ready)
        state.connection = ConnectionState.CONNECTED
        self.assertFalse(state.acquisition_ready)
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, state.draft_revision, 'A-scan', OperationResult(verification=report, readback_verified=True))
        self.assertTrue(state.acquisition_ready)
        state.dataset_revision = state.draft_revision
        state.dataset_mode = 'A-scan'
        state.edit_configuration(True)
        self.assertTrue(state.dataset_stale)
        self.assertFalse(state.acquisition_ready)

    def test_metadata_time_and_signed_save_reload(self):
        c = SingleElementAscanConfig(tx_element=3, rx_element=7, start_us=2)
        report = verify_configuration(c, matching(c))
        data = np.arange(751).astype(np.int8)
        result = SimpleNamespace(point_count=751, data_size=1, signed=True, bit_size=0)
        metadata = capture_metadata(data, report.snapshot, 12, c, result)
        np.testing.assert_allclose(metadata.time_us[[0, 1, -1]], [2, 2.04, 32])
        self.assertFalse(metadata.probe.mapping_verified)
        with tempfile.TemporaryDirectory() as folder:
            save_dataset(Path(folder) / 'ascan.npy', data, metadata)
            restored = load_dataset(Path(folder) / 'ascan.npy')
        np.testing.assert_array_equal(restored.data, data)
        self.assertEqual(restored.metadata.requested_parameters, metadata.requested_parameters)
        self.assertEqual(restored.metadata.hardware.field_verification, metadata.hardware.field_verification)


class SingleElementBackendTests(unittest.TestCase):
    setUp = backend_fixture.BackendTests.setUp

    def configured_backend(self, folder):
        c = SingleElementAscanConfig(tx_element=3, rx_element=7, start_us=2)
        reader = FakeReadbackAPI(matching(c))
        b = self.backend_module.GUIBackend(Path(folder) / 'gui_fmc_config.txt')
        b.device = Mock(handle='fake')
        b.device.refresh_status.return_value = dict(cycle_count=1, multichannel_supported=True, multichannel_enabled=False)
        b.acquisition = Mock()
        return b, c, reader

    def test_apply_and_single_cycle_acquire_use_fake_readback_and_actual_capacity(self):
        with tempfile.TemporaryDirectory() as folder:
            b, c, reader = self.configured_backend(folder)
            with patch.object(self.backend_module, 'api', reader):
                applied = b.apply(self.context, c)
                self.assertTrue(applied.readback_verified)
                self.assertTrue((Path(folder) / 'gui_ascan_config.txt').exists())
                self.assertFalse((Path(folder) / 'gui_fmc_config.txt').exists())
                b.acquisition.acquire.return_value = SimpleNamespace(scans=np.zeros((1,751), dtype=np.int8), point_count=751, data_size=1, signed=True, bit_size=0)
                result = b.acquire(self.context, c)
            self.assertEqual(result.payload.data.shape, (751,))
            self.assertEqual(result.payload.metadata.mode, 'A-scan')
            self.assertEqual(b.acquisition.acquire.call_args.kwargs['cycle_count'], 1)
            self.assertEqual(b.acquisition.acquire.call_args.kwargs['callback_capacity_bytes'], 751)
            self.assertGreaterEqual(b.device.disable_acquisition.call_count, 3)

    def test_changed_readback_blocks_before_single_cycle_start(self):
        with tempfile.TemporaryDirectory() as folder:
            b, c, reader = self.configured_backend(folder)
            with patch.object(self.backend_module, 'api', reader):
                b.apply(self.context, c)
                reader.snapshot = replace(reader.snapshot, cycles=(replace(reader.snapshot.cycles[0], rx_delays_s=None),))
                with self.assertRaises(self.backend_module.ConfigurationVerificationError):
                    b.acquire(self.context, c)
            b.acquisition.acquire.assert_not_called()
            self.assertIsNone(b.applied_snapshot)

    def test_failed_apply_clears_previous_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            b, c, reader = self.configured_backend(folder)
            b.applied_snapshot = matching(c)
            b.requested_configuration = c
            b.device.load_configuration.side_effect = RuntimeError('AOS write failed')
            with self.assertRaisesRegex(RuntimeError, 'AOS write failed'):
                b.apply(self.context, c)
            self.assertIsNone(b.applied_snapshot)
            self.assertIsNone(b.requested_configuration)
            b.acquisition.acquire.assert_not_called()


    def test_controller_mode_configuration_mismatch_stops_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            b, c, reader = self.configured_backend(folder)
            self.context.mode = 'A-scan'
            from oempa.config import FMCConfig
            with self.assertRaisesRegex(ValueError, 'controller acquisition mode'):
                b.apply(self.context, FMCConfig())
            b.device.load_configuration.assert_not_called()
            b.device.disable_acquisition.assert_not_called()
