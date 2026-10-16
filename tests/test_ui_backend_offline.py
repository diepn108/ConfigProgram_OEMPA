"""Load changed backend modules with a fake API, never the native DLL loader."""

from concurrent.futures import CancelledError
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np

from ui.controller import WorkerContext, OperationCancelled
from oempa.config import FMCConfig
from ui_readback_fakes import FakeReadbackAPI, matching_fmc


ROOT = Path(__file__).resolve().parents[1]


def load_source(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackendTests(unittest.TestCase):
    def test_frame_boundary_wakes_worker_before_next_count_poll_and_stops_before_copy(self):
        device = SimpleNamespace(is_connected=True, handle='fake', cycle_count=256)
        acquisition = self.acquisition.OEMPAAcquisition(device)
        acquisition.prepare = Mock(return_value=256)
        acquisition.start = Mock()
        events = []
        acquisition.stop = Mock(side_effect=lambda: events.append('OFF'))
        acquisition.read_cycles = Mock(side_effect=lambda count: events.append('copy') or 'first frame')
        self.api.get_multiascan_count.return_value = 0
        acquisition.get_received_cycles = Mock(return_value=list(range(256)))
        validator = Mock(side_effect=[False, True, True])
        wait = Mock()
        result = acquisition.acquire(record_validator=validator, poll_wait=wait)
        self.assertEqual(result, 'first frame')
        wait.assert_called_once()
        acquisition.stop.assert_called_once()
        self.assertEqual(events, ['OFF', 'copy'])

    def test_off_failure_prevents_first_frame_copy_and_acceptance(self):
        from oempa.timing import FMCTiming
        timing = FMCTiming()
        device = SimpleNamespace(is_connected=True, handle='fake', cycle_count=256)
        acquisition = self.acquisition.OEMPAAcquisition(device)
        acquisition.prepare = Mock(return_value=256)
        acquisition.start = Mock()
        acquisition.stop = Mock(side_effect=RuntimeError('OFF failed'))
        acquisition.read_cycles = Mock()
        self.api.get_multiascan_count.return_value = 256
        with self.assertRaisesRegex(RuntimeError, 'OFF failed'):
            acquisition.acquire(record_validator=Mock(return_value=True), timing=timing)
        acquisition.read_cycles.assert_not_called()
        self.assertIn('off_request', timing.marks)
        self.assertNotIn('off_return', timing.marks)

    def test_first_frame_backend_accepts_post_frame_after_shutdown(self):
        from test_ui_fmc_first_frame import FirstFrameTests
        frame, order, raw = FirstFrameTests().evidence('late25')
        cfg = FMCConfig(range_us=.12)
        snapshot = matching_fmc(cfg)
        backend = self.backend_module.GUIBackend('unused')
        backend.device = Mock(handle='fake')
        backend.device.refresh_status.return_value = {'cycle_count': 256, 'multichannel_supported': True, 'multichannel_enabled': True}
        backend.applied_snapshot = snapshot
        backend.requested_configuration = cfg
        backend.acquisition = Mock()
        # Fake acquisition returns only after its simulated safe OFF has completed.
        backend.acquisition.acquire.return_value = SimpleNamespace(cycle_count=256, point_count=7, data_size=1, signed=True, bit_size=0, scans=raw)
        for name, result in (('get_fmc_first_frame', frame), ('get_callback_order', order), ('get_callback_record_stats', {'total': 281, 'duplicates': 25, 'unexpected': 0, 'malformed': 0, 'cycle_counts': (2,) * 25 + (1,) * 231})):
            setattr(self.api, name, Mock(return_value=result))
        with patch.object(self.backend_module, 'collect_snapshot', return_value=snapshot):
            result = backend.acquire(self.context, cfg)
        self.assertEqual(result.payload.data.shape, (16, 16, 7))
        np.testing.assert_array_equal(result.payload.data.reshape(256, 7), raw)
        self.assertEqual(result.payload.metadata.acquisition_acceptance, 'accepted')
        self.assertEqual(result.payload.metadata.frame_evidence.post_frame_callback_count, 25)

    def test_production_fmc_apply_dispatches_exact_approved_file_not_ascan(self):
        backend = self.backend_module.GUIBackend('unused')
        backend.apply_approved_fmc_file = Mock(return_value='approved')
        context = WorkerContext(threading.Event(), lambda *args: None, mode='FMC')
        with patch.object(self.backend_module, 'FMCConfigBuilder') as builder:
            self.assertEqual(backend.apply(context, FMCConfig()), 'approved')
            builder.assert_not_called()
        path = backend.apply_approved_fmc_file.call_args.args[1]
        self.assertEqual(path, ROOT / 'configs/fmc16_full.txt')
        self.assertEqual(self.backend_module.inspect_approved_fmc(path).cycle_count, 256)

    def test_production_fmc_changed_common_request_never_silently_applies_defaults(self):
        backend = self.backend_module.GUIBackend('unused')
        backend.device = Mock()
        context = WorkerContext(threading.Event(), lambda *args: None, mode='FMC')
        with self.assertRaisesRegex(ValueError, 'No write attempted'):
            backend.apply(context, FMCConfig(analog_gain_db=21))
        backend.device.load_configuration.assert_not_called()

    def test_strict_poll_failure_stops_before_array_copy(self):
        device = SimpleNamespace(is_connected=True, handle='fake', cycle_count=256)
        acquisition = self.acquisition.OEMPAAcquisition(device)
        acquisition.prepare = Mock(return_value=256)
        acquisition.start = Mock()
        acquisition.stop = Mock()
        acquisition.read_cycles = Mock()
        self.api.get_multiascan_count.return_value = 256
        validator = Mock(side_effect=RuntimeError('duplicate rejected'))
        armed = Mock()
        with self.assertRaisesRegex(RuntimeError, 'duplicate rejected'):
            acquisition.acquire(prepared_callback=armed, record_validator=validator)
        armed.assert_called_once()
        validator.assert_called_once_with(False)
        acquisition.stop.assert_called_once()
        acquisition.read_cycles.assert_not_called()

    def test_strict_shutdown_validation_rejects_later_duplicates_before_copy(self):
        device = SimpleNamespace(is_connected=True, handle='fake', cycle_count=256)
        acquisition = self.acquisition.OEMPAAcquisition(device)
        acquisition.prepare = Mock(return_value=256)
        acquisition.start = Mock()
        acquisition.stop = Mock()
        acquisition.read_cycles = Mock()
        self.api.get_multiascan_count.return_value = 256
        validator = Mock(side_effect=[None, RuntimeError('shutdown duplicate rejected')])
        with self.assertRaisesRegex(RuntimeError, 'shutdown duplicate rejected'):
            acquisition.acquire(record_validator=validator)
        self.assertEqual([call.args for call in validator.call_args_list], [(False,), (True,)])
        acquisition.stop.assert_called_once()
        acquisition.read_cycles.assert_not_called()

    def setUp(self):
        self.api = ModuleType("oempa.api")
        for name in ("create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition",
                     "enable_acquisition", "get_cycle_count", "get_multichannel_state",
                     "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan",
                     "get_multiascan_count", "load_configuration"):
            setattr(self.api, name, Mock())
        self.api.create_handle.return_value = "fake handle"
        self.api.get_cycle_count.return_value = 1
        self.api.get_multichannel_state.return_value = {"supported": True, "enabled": True}
        import oempa
        self.modules = patch.dict(sys.modules, {"oempa.api": self.api})
        self.modules.start()
        self.package_api = patch.object(oempa, "api", self.api, create=True)
        self.package_api.start()
        self.addCleanup(self.modules.stop)
        self.addCleanup(self.package_api.stop)
        self.driver = load_source("offline_driver", "oempa/driver.py")
        self.acquisition = load_source("offline_acquisition", "oempa/acquisition.py")
        with patch.dict(sys.modules, {"oempa.driver": self.driver, "oempa.acquisition": self.acquisition}):
            self.backend_module = load_source("offline_gui_backend", "oempa/gui_backend.py")
        self.context = WorkerContext(threading.Event(), lambda *args: None)

    def test_partial_connect_failure_disconnects_before_handle_destruction(self):
        self.api.connect.side_effect = RuntimeError("partial connect")
        backend = self.backend_module.GUIBackend("unused")
        with self.assertRaisesRegex(RuntimeError, "partial connect"):
            backend.connect(self.context, "fake", 5001)
        self.api.disconnect.assert_called_once_with("fake handle")
        self.api.destroy_handle.assert_called_once_with("fake handle")
        self.assertIsNone(backend.device)

    def test_failed_disconnect_retains_handle_and_error_details(self):
        self.api.connect.side_effect = RuntimeError("partial connect")
        self.api.disconnect.side_effect = RuntimeError("disconnect failed")
        backend = self.backend_module.GUIBackend("unused")
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            backend.connect(self.context, "fake", 5001)
        self.api.destroy_handle.assert_not_called()
        self.assertIsNotNone(backend.device)
        self.api.disconnect.side_effect = None
        backend.close(self.context)
        self.api.destroy_handle.assert_called_once()

    def test_stop_failure_prevents_device_destruction(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.acquisition.stop.side_effect = RuntimeError("OFF failed")
        with self.assertRaisesRegex(RuntimeError, "OFF failed"):
            backend.close(self.context)
        backend.device.close.assert_not_called()

    def test_reconnect_failure_cleans_partial_native_connection(self):
        device = self.driver.OEMPADevice()
        device.connect()
        self.api.connect.side_effect = RuntimeError("partial reconnect")
        with self.assertRaisesRegex(RuntimeError, "partial reconnect"):
            device.load_configuration("unused")
        self.assertFalse(device.is_connected)
        self.assertEqual(self.api.disconnect.call_count, 2)
        device.close()
        self.api.destroy_handle.assert_called_once()

    def test_reconnect_cleanup_failure_does_not_destroy_live_handle(self):
        device = self.driver.OEMPADevice()
        device.connect()
        self.api.connect.side_effect = RuntimeError("partial reconnect")
        self.api.disconnect.side_effect = [None, RuntimeError("disconnect failed"), RuntimeError("still failed")]
        with self.assertRaisesRegex(RuntimeError, "disconnect failed"):
            device.load_configuration("unused")
        with self.assertRaisesRegex(RuntimeError, "still failed"):
            device.close()
        self.api.destroy_handle.assert_not_called()

    def test_backend_close_ignores_cancel_to_complete_cleanup(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        device = backend.device
        self.context.cancel_event.set()
        result = backend.close(self.context)
        device.close.assert_called_once()
        self.assertFalse(result.connected)

    def test_acquisition_cancel_before_prepare_touches_no_fake_api(self):
        acquisition = self.acquisition.OEMPAAcquisition(SimpleNamespace(is_connected=True, cycle_count=1, handle="fake"))
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(CancelledError):
            acquisition.acquire(cancel_event=cancelled)
        self.api.enable_acquisition.assert_not_called()
        self.api.set_multiascan_cycle_count.assert_not_called()

    def test_poll_cancellation_stops_in_finally(self):
        acquisition = self.acquisition.OEMPAAcquisition(SimpleNamespace(is_connected=True, cycle_count=1, handle="fake"))
        cancelled = threading.Event()
        def received(handle):
            cancelled.set()
            return 0
        self.api.get_multiascan_count.side_effect = received
        with self.assertRaises(CancelledError):
            acquisition.acquire(cancel_event=cancelled)
        self.api.enable_acquisition.assert_called_once()
        self.assertEqual(self.api.disable_acquisition.call_count, 2)

    def test_stop_error_overrides_cancellation(self):
        acquisition = self.acquisition.OEMPAAcquisition(SimpleNamespace(is_connected=True, cycle_count=1, handle="fake"))
        cancelled = threading.Event()
        self.api.disable_acquisition.side_effect = [None, RuntimeError("OFF failed")]
        def received(handle):
            cancelled.set()
            return 0
        self.api.get_multiascan_count.side_effect = received
        with self.assertRaisesRegex(RuntimeError, "OFF failed"):
            acquisition.acquire(cancel_event=cancelled)

    def test_no_cancel_preserves_acquisition_result_path(self):
        acquisition = self.acquisition.OEMPAAcquisition(SimpleNamespace(is_connected=True, cycle_count=1, handle="fake"))
        self.api.get_multiascan_count.return_value = 1
        acquisition.get_received_cycles = Mock(return_value=[0])
        acquisition.read_cycles = Mock(return_value="unchanged result")
        self.assertEqual(acquisition.acquire(), "unchanged result")
        self.assertEqual(self.api.disable_acquisition.call_count, 2)

    def test_adapter_translates_cancellation_only_after_backend_stop(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.acquisition = Mock()
        backend.acquisition.acquire.side_effect = CancelledError()
        config = FMCConfig()
        backend.device = Mock()
        backend.device.refresh_status.return_value = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        backend.applied_snapshot = matching_fmc(config)
        backend.requested_configuration = config
        with patch.object(self.backend_module, "collect_snapshot", return_value=matching_fmc(config)):
            with self.assertRaises(OperationCancelled):
                backend.acquire(self.context, config)

    def test_apply_checks_existing_topology_without_writing_test_files(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        config = FMCConfig()
        status = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        backend.device.get_status.return_value = status
        with patch.object(self.backend_module, "FMCConfigBuilder") as builder, patch.object(self.backend_module, "collect_snapshot", return_value=matching_fmc(config)):
            result = backend.apply(self.context, config)
            builder.return_value.save.assert_called_once_with("unused")
        self.assertTrue(result.readback_verified)
        self.assertIn("only", result.verification_scope)

    def test_failed_apply_readback_is_not_success(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.device.get_status.return_value = {"cycle_count": 1}
        from dataclasses import replace
        config = FMCConfig()
        snapshot = replace(matching_fmc(config), cycle_count=1)
        with patch.object(self.backend_module, "FMCConfigBuilder"), patch.object(self.backend_module, "collect_snapshot", return_value=snapshot):
            with self.assertRaisesRegex(RuntimeError, "cycle count"):
                backend.apply(self.context, config)

    def test_fake_acquisition_pipeline_uses_readback_rate_and_captured_revision(self):
        config = FMCConfig(tx_count=2, rx_count=2)
        snapshot = matching_fmc(config, 25e6)
        reader = FakeReadbackAPI(snapshot)
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        status = {"cycle_count": 4, "multichannel_supported": True, "multichannel_enabled": True}
        backend.device.get_status.return_value = status
        backend.device.refresh_status.return_value = status
        backend.acquisition = Mock()
        count = snapshot.cycles[0].point_count
        result = SimpleNamespace(scans=np.zeros((4, count), dtype=np.int8), point_count=count, data_size=1, signed=True, bit_size=0)
        backend.acquisition.acquire.return_value = result
        context = WorkerContext(threading.Event(), lambda *args: None, revision=9, mode="FMC")
        with patch.object(self.backend_module, "api", reader), patch.object(self.backend_module, "FMCConfigBuilder"):
            backend.apply(context, config)
            acquired = backend.acquire(context, config)
        self.assertEqual(acquired.payload.sampling_hz, 25e6)
        np.testing.assert_allclose(acquired.payload.time_us[:3], [0, 0.04, 0.08])
        self.assertEqual(acquired.payload.metadata.configuration_revision, 9)
        self.assertEqual(acquired.payload.shape, (2, 2, 751))
        backend.device.disable_acquisition.assert_called_once()

    def test_external_readback_mismatch_blocks_before_fake_acquisition(self):
        from dataclasses import replace
        config = FMCConfig(tx_count=2, rx_count=2)
        snapshot = matching_fmc(config)
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.applied_snapshot = snapshot
        backend.requested_configuration = config
        backend.device.refresh_status.return_value = {"cycle_count": 4, "multichannel_supported": True, "multichannel_enabled": True}
        mismatch = replace(snapshot, cycles=(replace(snapshot.cycles[0], gain_analog_db=99),) + snapshot.cycles[1:])
        with patch.object(self.backend_module, "api", FakeReadbackAPI(mismatch)):
            with self.assertRaises(self.backend_module.ConfigurationVerificationError) as caught:
                backend.acquire(self.context, config)
        backend.acquisition.acquire.assert_not_called()
        self.assertEqual(caught.exception.verification.snapshot.cycles[0].gain_analog_db, 99)


    def test_unchanged_verified_request_still_reads_all_cycles_before_acquisition(self):
        config = FMCConfig(tx_count=2, rx_count=2)
        snapshot = matching_fmc(config)
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.applied_snapshot = snapshot
        backend.requested_configuration = config
        backend.device.refresh_status.return_value = {"cycle_count": 4, "multichannel_supported": True, "multichannel_enabled": True}
        reader = FakeReadbackAPI(snapshot)
        reader.get_cycle_snapshot = Mock(wraps=reader.get_cycle_snapshot)
        reader.get_extended_cycle_snapshot = Mock(wraps=reader.get_extended_cycle_snapshot)
        backend.acquisition.acquire.side_effect = CancelledError()
        with patch.object(self.backend_module, "api", reader):
            with self.assertRaises(OperationCancelled):
                backend.acquire(self.context, config)
        self.assertEqual(reader.get_cycle_snapshot.call_count, 4)
        self.assertEqual(reader.get_extended_cycle_snapshot.call_count, 4)
        backend.device.disable_acquisition.assert_called_once()
        self.assertIn('initial_off', backend.last_fmc_timing.preparation)
        self.assertIn('full_snapshot', backend.last_fmc_timing.preparation)
        self.assertIn('python_verification', backend.last_fmc_timing.preparation)

    def test_approved_pa_file_apply_preserves_source_and_never_acquires(self):
        from dataclasses import replace
        from test_ui_phase2 import matching_pa
        from oempa.verified_pa import inspect_approved_pa
        path = ROOT / "configs/pa_test_0deg_timeslot_2600us_estimate.txt"
        original = path.read_bytes()
        request = inspect_approved_pa(path)
        snapshot = matching_pa(request)
        snapshot = replace(snapshot, cycles=(replace(snapshot.cycles[0], point_count=3001, sampling_hz=100e6),))
        backend = self.backend_module.GUIBackend("must_not_write")
        backend.device = Mock()
        status = {"cycle_count": 1, "multichannel_supported": True, "multichannel_enabled": False}
        backend.device.get_status.return_value = status
        backend.device.refresh_status.return_value = status
        with patch.object(self.backend_module, "api", FakeReadbackAPI(snapshot)), patch.object(self.backend_module, "FMCConfigBuilder") as builder:
            result = backend.apply_approved_pa_file(self.context, path)
        self.assertTrue(result.readback_verified)
        self.assertEqual(result.verification.snapshot.mode, "PA")
        self.assertEqual(dict(result.requested_configuration)["file_point_count"], 0)
        builder.assert_not_called()
        backend.device.load_configuration.assert_called_once_with(path.resolve(), reconnect=True)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaisesRegex(RuntimeError, "Only the verified FMC"):
            backend.acquire(self.context, request)

    def test_approved_pa_file_rejects_modified_source_before_write(self):
        import tempfile
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "changed.txt"
            path.write_text("[Root]\nCycleCount=1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                backend.apply_approved_pa_file(self.context, path)
        backend.device.load_configuration.assert_not_called()

    def test_approved_pa_file_stops_if_multichannel_is_enabled(self):
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.device.refresh_status.return_value = {"multichannel_enabled": True}
        with self.assertRaisesRegex(RuntimeError, "must already be disabled"):
            backend.apply_approved_pa_file(self.context, ROOT / "configs/pa_test_0deg_timeslot_2600us_estimate.txt")
        backend.device.load_configuration.assert_not_called()

    def test_approved_pa_readback_mismatch_retains_requested_and_actual(self):
        from dataclasses import replace
        from test_ui_phase2 import matching_pa
        from oempa.verified_pa import inspect_approved_pa
        path = ROOT / "configs/pa_test_0deg_timeslot_2600us_estimate.txt"
        request = inspect_approved_pa(path)
        snapshot = matching_pa(request)
        snapshot = replace(snapshot, cycles=(replace(snapshot.cycles[0], point_count=3001, sampling_hz=100e6, gain_analog_db=19),))
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        status = {"cycle_count": 1, "multichannel_supported": True, "multichannel_enabled": False}
        backend.device.refresh_status.return_value = status
        backend.device.get_status.return_value = status
        with patch.object(self.backend_module, "api", FakeReadbackAPI(snapshot)):
            with self.assertRaises(self.backend_module.ConfigurationVerificationError) as caught:
                backend.apply_approved_pa_file(self.context, path)
        self.assertIsNone(backend.applied_snapshot)
        self.assertEqual(dict(caught.exception.requested_configuration)["analog_gain_db"], 20)
        self.assertEqual(caught.exception.verification.snapshot.cycles[0].gain_analog_db, 19)
        self.assertEqual(backend.device.load_configuration.call_count, 1)

    def test_configuration_only_pa_verification_cannot_enable_acquisition(self):
        from ui.state import ApplicationState, ConnectionState, Operation
        from ui.controller import OperationResult
        state = ApplicationState(connection=ConnectionState.CONNECTED, mode="PA", draft_valid=True, hardware_modes=frozenset({"FMC"}), configuration_modes=frozenset({"FMC", "PA"}))
        state.begin(Operation.APPLYING)
        state.complete(Operation.APPLYING, state.draft_revision, "PA", OperationResult(readback_verified=True))
        self.assertEqual(state.configuration_label, "Verified")
        self.assertFalse(state.acquisition_ready)
        with self.assertRaises(RuntimeError):
            state.begin(Operation.ACQUIRING)

    def test_fmc_file_is_applied_without_regeneration_and_prepared_off(self):
        from oempa.verified_fmc import inspect_approved_fmc
        path = ROOT / "configs/fmc16_full.txt"
        original = path.read_bytes()
        request = inspect_approved_fmc(path)
        snapshot = matching_fmc(request, 100e6)
        from dataclasses import replace
        snapshot = replace(snapshot, cycles=tuple(replace(cycle, gain_analog_db=20) for cycle in snapshot.cycles))
        backend = self.backend_module.GUIBackend("must_not_write")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.device.get_status.return_value = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        with patch.object(self.backend_module, "api", FakeReadbackAPI(snapshot)), patch.object(self.backend_module, "FMCConfigBuilder") as builder:
            result = backend.apply_approved_fmc_file(self.context, path)
        self.assertTrue(result.readback_verified)
        builder.assert_not_called()
        backend.device.load_configuration.assert_called_once_with(path.resolve(), reconnect=True)
        backend.acquisition.prepare.assert_called_once_with(256, callback_capacity_bytes=3001)
        backend.acquisition.acquire.assert_not_called()
        self.assertEqual(original, path.read_bytes())

    def test_callback_preallocation_follows_off_registration_and_clear(self):
        device = Mock()
        device.is_connected = True
        acquisition = self.acquisition.OEMPAAcquisition(device)
        calls = Mock()
        with patch.object(self.acquisition, "api", calls):
            acquisition.prepare(256, callback_capacity_bytes=3001)
        names = [call[0] for call in calls.mock_calls]
        self.assertEqual(names, ["disable_acquisition", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers"])
        calls.enable_acquisition.assert_not_called()

    def test_fmc_unreadable_classification_apply_has_distinct_provenance(self):
        from dataclasses import replace
        from oempa.verified_fmc import inspect_approved_fmc
        path = ROOT / "configs/fmc16_full.txt"
        request = inspect_approved_fmc(path)
        snapshot = matching_fmc(request, 100e6)
        snapshot = replace(snapshot, cycles=tuple(replace(cycle, hw_acquisition=None, gain_analog_db=20, widths_s=None, tx_delays_s=None) for cycle in snapshot.cycles))
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.device.get_status.return_value = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        with patch.object(self.backend_module, "api", FakeReadbackAPI(snapshot)):
            result = backend.apply_approved_fmc_file(self.context, path)
        self.assertTrue(result.configuration_verified)
        self.assertFalse(result.readback_verified)
        self.assertIsNone(result.verification.snapshot.cycles[0].hw_acquisition)
        self.assertIsNone(result.verification.snapshot.cycles[0].widths_s)
        self.assertIsNone(result.verification.snapshot.cycles[0].tx_delays_s)
        self.assertTrue(backend.applied_fmc_provenance.cycle_flags[0])
        self.assertFalse(backend.applied_fmc_provenance.cycle_flags[1])
        backend.acquisition.prepare.assert_called_once_with(256, callback_capacity_bytes=3001)
        backend.acquisition.acquire.assert_not_called()

    def test_fmc_mismatch_prevents_callback_preallocation_with_provenance(self):
        from dataclasses import replace
        from oempa.verified_fmc import inspect_approved_fmc
        path = ROOT / "configs/fmc16_full.txt"
        snapshot = matching_fmc(inspect_approved_fmc(path), 100e6)
        snapshot = replace(snapshot, cycles=tuple(replace(cycle, hw_acquisition=None, gain_analog_db=20, filter_index=2) for cycle in snapshot.cycles))
        backend = self.backend_module.GUIBackend("unused")
        backend.device = Mock()
        backend.acquisition = Mock()
        backend.device.get_status.return_value = {"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True}
        with patch.object(self.backend_module, "api", FakeReadbackAPI(snapshot)):
            with self.assertRaises(self.backend_module.ConfigurationVerificationError):
                backend.apply_approved_fmc_file(self.context, path)
        backend.acquisition.prepare.assert_not_called()
        self.assertIsNone(backend.applied_fmc_provenance)
        self.assertIsNone(backend.applied_snapshot)

if __name__ == "__main__":
    unittest.main()
