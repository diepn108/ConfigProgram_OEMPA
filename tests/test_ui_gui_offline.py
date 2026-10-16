"""Headless GUI integration with fake backend and main-thread-checking Tk objects."""

import importlib.util
from pathlib import Path
import sys
import threading
import time
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

import numpy as np

from oempa.fmc import FMCData
from ui.controller import OperationResult
from oempa.dataset import capture_metadata, load_dataset
from ui_readback_fakes import matching_fmc
from types import SimpleNamespace
import tempfile


class FakeVariable:
    def __init__(self, value=None, **kwargs):
        self.value = value
        self.owner = threading.get_ident()
        self.callbacks = []

    def check_thread(self):
        if threading.get_ident() != self.owner:
            raise AssertionError("Tk variable used from worker")

    def get(self):
        self.check_thread()
        return self.value

    def set(self, value):
        self.check_thread()
        self.value = value
        for callback in self.callbacks:
            callback()

    def trace_add(self, kind, callback):
        self.check_thread()
        self.callbacks.append(callback)


class FakeRoot:
    def __init__(self):
        self.owner = threading.get_ident()
        self.destroyed = False
        self.scheduled = []

    def check_thread(self):
        if threading.get_ident() != self.owner:
            raise AssertionError("Tk root used from worker")

    def after(self, delay, callback):
        self.check_thread()
        self.scheduled.append(callback)

    def destroy(self):
        self.check_thread()
        self.destroyed = True

    def title(self, *args):
        self.check_thread()

    geometry = title
    minsize = title
    protocol = title


class FakeGUIBackend:
    def __init__(self, path):
        self.fail_apply = False
        self.fail_close = False
        self.closed = False

    def connect(self, context, ip_address, port):
        return OperationResult(connected=True, payload={"cycle_count": 256, "multichannel_supported": True, "multichannel_enabled": True})

    def apply(self, context, config):
        if self.fail_apply:
            raise RuntimeError("fake partial apply")
        return OperationResult(connected=True, payload=(config, {"cycle_count": config.cycle_count}), readback_verified=True, verification_scope="fake topology")

    def acquire(self, context, config, probe=None):
        context.progress(config.cycle_count, config.cycle_count)
        data = FMCData(np.zeros((config.tx_count, config.rx_count, 5), dtype=np.int8), config.tx_count, config.rx_count, 5, 1, True, 0)
        return OperationResult(payload=data)

    def close(self, context):
        if self.fail_close:
            raise RuntimeError("fake cleanup failed")
        self.closed = True
        return OperationResult(connected=False)


class GUIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stub = ModuleType("oempa.gui_backend")
        stub.GUIBackend = FakeGUIBackend
        spec = importlib.util.spec_from_file_location("offline_gui", Path(__file__).resolve().parents[1] / "gui.py")
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"oempa.gui_backend": stub}):
            spec.loader.exec_module(cls.module)

    def setUp(self):
        def build(app):
            app.config_entries = [Mock() for _ in range(8)]
            for name in ("ip_entry", "port_entry", "connect_button", "disconnect_button", "apply_button", "acquire_button", "save_button", "tx_spinbox", "rx_spinbox", "axes", "canvas", "figure", "log_text", "bscan_controls", "ascan_controls"):
                setattr(app, name, Mock())
        patches = [patch.object(self.module.OEMPAGUI, "_build_ui", build),
                   patch.object(self.module.tk, "StringVar", FakeVariable),
                   patch.object(self.module.tk, "IntVar", FakeVariable),
                   patch.object(self.module.tk, "DoubleVar", FakeVariable),
                   patch.object(self.module.messagebox, "showerror"),
                   patch.object(self.module.messagebox, "showwarning"),
                   patch.object(self.module.messagebox, "askyesno", return_value=True),
                   patch.object(self.module.plt, "close")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.root = FakeRoot()
        self.app = self.module.OEMPAGUI(self.root)

    def pump(self):
        deadline = time.monotonic() + 3
        while self.app.controller.active and time.monotonic() < deadline:
            self.app._consume_events()
            time.sleep(0.001)
        self.assertFalse(self.app.controller.active)
        if not self.root.destroyed:
            self.app._consume_events()

    def connected_applied(self):
        self.app.connect_device()
        self.pump()
        self.app.apply_configuration()
        self.pump()

    def test_connect_does_not_enable_acquisition_until_apply(self):
        self.app.connect_device()
        self.pump()
        self.assertFalse(self.app.state.acquisition_ready)
        self.app.acquire_button.configure.assert_called_with(state="disabled")
        self.app.apply_configuration()
        self.pump()
        self.assertTrue(self.app.state.acquisition_ready)
        self.app.acquire_button.configure.assert_called_with(state="normal")

    def test_fmc_bscan_and_waveform_paths_preserved_and_edit_marks_stale(self):
        self.connected_applied()
        self.app.acquire_fmc()
        self.pump()
        self.assertEqual(self.app.fmc_data.shape, (16, 16, 5))
        self.assertEqual(self.app.bscan_data.shape, (16, 5))
        self.app.analog_gain_var.set("21.0")
        self.assertTrue(self.app.state.dataset_stale)
        self.assertFalse(self.app.state.acquisition_ready)
        self.assertIn("stale", self.app.data_shape_var.get())
        self.assertIn("stale", self.app.axes.set_title.call_args.args[0])
        self.app.view_mode_var.set("B-Scan")
        self.app.bscan_gate_start_var.set("0.0")
        self.app.bscan_gate_end_var.set("0.04")
        self.app.update_data_view()
        self.app.axes.imshow.assert_called_once()

    def test_config_entries_disabled_while_owned(self):
        self.app.connect_device()
        for entry in self.app.config_entries:
            entry.configure.assert_called_with(state="disabled")
        self.pump()
        for entry in self.app.config_entries:
            entry.configure.assert_called_with(state="normal")

    def test_partial_apply_error_disables_acquisition(self):
        self.connected_applied()
        self.app.backend.fail_apply = True
        self.app.apply_configuration()
        self.pump()
        self.assertFalse(self.app.state.acquisition_ready)
        self.assertIn("partial apply", self.app.state.error)
        self.app.acquire_button.configure.assert_called_with(state="disabled")

    def test_reapply_marks_prior_waveform_stale_before_worker_completion(self):
        self.connected_applied()
        self.app.acquire_fmc()
        self.pump()
        self.app.apply_configuration()
        self.assertTrue(self.app.state.dataset_stale)
        self.assertIn("stale", self.app.axes.set_title.call_args.args[0])
        self.pump()

    def test_nonfinite_draft_does_not_enable_apply(self):
        self.app.analog_gain_var.set("nan")
        self.assertFalse(self.app.state.draft_valid)
        self.assertFalse(self.app.state.acquisition_ready)

    def test_display_failure_keeps_event_pump_running_and_acquisition_blocked(self):
        self.connected_applied()
        self.app.axes.plot.side_effect = RuntimeError("plot failed")
        scheduled = len(self.root.scheduled)
        self.app.acquire_fmc()
        self.pump()
        self.assertGreater(len(self.root.scheduled), scheduled)
        self.assertFalse(self.app.state.acquisition_ready)
        self.assertIn("plot failed", self.app.state.error)

    def test_closing_waits_for_worker_cleanup_and_main_thread_destroys(self):
        self.app.connect_device()
        self.app.on_close()
        self.assertFalse(self.root.destroyed)
        self.pump()
        self.assertTrue(self.app.backend.closed)
        self.assertTrue(self.root.destroyed)

    def test_cleanup_failure_does_not_destroy_window_and_can_retry(self):
        self.connected_applied()
        self.app.backend.fail_close = True
        self.app.on_close()
        self.pump()
        self.assertFalse(self.root.destroyed)
        self.assertFalse(self.app.state.acquisition_ready)
        self.app.backend.fail_close = False
        self.app.on_close()
        self.pump()
        self.assertTrue(self.root.destroyed)

    def test_gui_import_does_not_load_native_api_under_fake_adapter(self):
        self.assertNotIn("oempa.api", sys.modules)

    def test_metadata_plot_and_save_survive_draft_edits(self):
        self.connected_applied()
        config = self.app._applied_config
        snapshot = matching_fmc(config, 25e6)
        count = snapshot.cycles[0].point_count
        raw = np.zeros((16, 16, count), dtype=np.int8)
        metadata = capture_metadata(raw, snapshot, self.app.state.applied_revision, config,
                                    SimpleNamespace(point_count=count, data_size=1, signed=True, bit_size=0))
        cube = FMCData(raw, 16, 16, count, 1, True, 0, metadata=metadata)
        self.app.backend.acquire = lambda context, config, probe=None: OperationResult(payload=cube)
        self.app.acquire_fmc()
        self.pump()
        plotted = self.app.axes.plot.call_args.args[0]
        np.testing.assert_allclose(plotted[:3], [0, 0.04, 0.08])
        self.app.range_var.set("40")
        self.assertEqual(self.app.fmc_data.metadata, metadata)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.npy"
            with patch.object(self.module.filedialog, "asksaveasfilename", return_value=str(path)):
                self.app.save_fmc()
            self.assertEqual(load_dataset(path).metadata, metadata)

    def test_legacy_plots_use_sample_index_and_do_not_apply_time_gates(self):
        self.connected_applied()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.npy"
            np.save(path, np.zeros((16, 16, 8), dtype=np.int8))
            self.app._acquisition_success(FMCData.load(path))
        self.app.axes.set_xlabel.assert_called_with("Sample index (metadata incomplete)")
        self.app.view_mode_var.set("B-Scan")
        self.app.update_data_view()
        self.app.axes.set_ylabel.assert_called_with("Sample index; time gates unavailable")


if __name__ == "__main__":
    unittest.main()
