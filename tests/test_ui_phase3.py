"""Offline widget construction and workflows with a fake adapter only.

Widget fakes enforce geometry ownership; real Matplotlib figures test plotting.
No Tk window, native SDK or physical device is loaded.
"""

import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
import tkinter as tk
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from test_ui_gui_offline import FakeGUIBackend, FakeRoot, FakeVariable
from matplotlib.backends.backend_agg import FigureCanvasAgg
import ui.layout
import ui.setup_panel
import ui.workspace
from oempa.config import FMCConfig
from oempa.dataset import capture_metadata
from oempa.fmc import FMCData
from ui_readback_fakes import matching_fmc
from ui.presentation import dataset_summary
from ui.state import ApplicationState, ConnectionState, ConfigurationState, Operation


class Widget:
    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.options = kwargs
        self.children = []
        self.pages = []
        self.current = None
        self.manager = None
        if parent is not None:
            parent.children.append(self)

    def grid(self, **kwargs):
        self._manage("grid")

    def pack(self, **kwargs):
        self._manage("pack")

    def _manage(self, manager):
        if self.parent is not None:
            for sibling in self.parent.children:
                if sibling is not self and sibling.manager not in {None, manager}:
                    raise AssertionError("Mixed grid/pack children")
        self.manager = manager

    def grid_remove(self):
        self.manager = None

    pack_forget = grid_remove

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def __getitem__(self, key):
        return self.options[key]

    def cget(self, key):
        return self.options.get(key)

    def add(self, page, **kwargs):
        self.pages.append(page)
        page.options.update(kwargs)
        if self.current is None:
            self.current = page

    def tabs(self):
        return self.pages

    def tab(self, page, key):
        return page.options[key]

    def select(self, page=None):
        if page is not None:
            self.current = page
        return self.current

    def winfo_children(self):
        return self.children

    def bind(self, *args):
        pass

    def columnconfigure(self, *args, **kwargs):
        pass

    rowconfigure = columnconfigure

    def insert(self, *args, **kwargs):
        pass

    see = insert
    delete = insert
    create_window = insert
    set = insert

    def yview(self, *args):
        return (0.0, 1.0)


class Root(FakeRoot):
    def __init__(self):
        super().__init__()
        self.children = []

    def columnconfigure(self, *args, **kwargs):
        self.check_thread()

    rowconfigure = columnconfigure

    def update_idletasks(self):
        self.check_thread()


class Canvas(FigureCanvasAgg):
    def __init__(self, figure, master):
        super().__init__(figure)
        self.widget = Widget(master)

    def get_tk_widget(self):
        return self.widget


class ProductionLayoutTests(unittest.TestCase):
    def test_fmc_timing_draw_records_once_and_keeps_original_dataset_values(self):
        from oempa.timing import FMCTiming
        cfg = FMCConfig(range_us=.12)
        snapshot = matching_fmc(cfg)
        raw = np.arange(256 * 7, dtype=np.int16).reshape(16, 16, 7).astype(np.int8)
        original = raw.copy()
        metadata = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=7, data_size=1, signed=True, bit_size=0))
        data = FMCData(raw, 16, 16, 7, 1, True, 0, metadata=metadata)
        data.timing = FMCTiming()
        data.timing.mark('requested')
        data.timing.mark('worker_start')
        data.timing.warnings.append('Synthetic diagnostic warning')
        self.app._acquisition_success(data)
        with patch.object(self.app, 'log') as log:
            self.app._finish_fmc_timing(data)
            self.app.canvas.draw()
        log.assert_not_called()
        self.assertIn('draw_complete', data.timing.marks)
        self.assertIn('total', dict(data.metadata.timing_profile)['durations_s'])
        self.assertIn('Synthetic diagnostic warning', dict(data.metadata.timing_profile)['warnings'])
        self.assertIs(data.metadata.hardware, metadata.hardware)
        self.assertEqual(data.metadata.requested_parameters, metadata.requested_parameters)
        np.testing.assert_array_equal(raw, original)
    def test_legacy_diagonal_and_bscan_normalization_use_sample_indices(self):
        from oempa.dataset import AcquisitionMetadata
        raw = np.arange(16 * 16 * 9, dtype=np.int16).reshape(16, 16, 9).astype(np.int8)
        meta = AcquisitionMetadata('unknown', raw.shape, raw.dtype.str)
        data = FMCData(raw, 16, 16, 9, 1, True, 0, metadata=meta)
        self.app._loaded_fmc_view(data)
        previous = vars(self.app.state).copy()
        with patch.object(self.app.controller, 'submit') as submit:
            self.app.fmc_trace_view_var.set('All diagonal traces')
            self.app.update_data_view()
            self.assertEqual(len(self.app.axes.lines), 16)
            np.testing.assert_array_equal(self.app.axes.lines[0].get_xdata(), np.arange(9))
            self.assertIn('metadata incomplete', self.app.axes.get_xlabel())
            self.app.workspace.select(self.app.display_panels['B-scan'])
            self.app.bscan_gate_start_var.set('not a time')
            self.app.bscan_normalization_var.set('Per trace')
            self.app.change_display()
            self.assertEqual(self.app.axes.images[0].get_array().shape, (9, 16))
            self.assertIn('time gates unavailable', self.app.axes.get_ylabel())
            submit.assert_not_called()
        self.assertEqual(vars(self.app.state), previous)
        self.assertIs(data.metadata, meta)

    def test_bscan_single_sample_gate_and_invalid_gate_keep_raw(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        n = snapshot.cycles[0].point_count
        raw = np.ones((16, 16, n), dtype=np.int8)
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=n, data_size=1, signed=True, bit_size=0))
        self.app._loaded_fmc_view(FMCData(raw, 16, 16, n, 1, True, 0, metadata=meta))
        self.app.workspace.select(self.app.display_panels['B-scan'])
        self.app.bscan_gate_start_var.set('.001')
        self.app.bscan_gate_end_var.set('.041')
        with patch.object(self.app.controller, 'submit') as submit, patch.object(self.module.messagebox, 'showerror') as error:
            self.app.change_display()
            self.assertEqual(self.app.axes.images[0].get_array().shape, (1, 16))
            extent = self.app.axes.images[0].get_extent()
            self.assertGreater(extent[2], extent[3])
            for start, end in (('nan', '1'), ('0', 'inf'), ('2', '1'), ('100', '101')):
                self.app.bscan_gate_start_var.set(start)
                self.app.bscan_gate_end_var.set(end)
                self.app.update_data_view()
            self.assertEqual(error.call_count, 4)
            submit.assert_not_called()
        np.testing.assert_array_equal(raw, np.ones((16, 16, n), dtype=np.int8))

    def test_all_diagonal_trace_view_and_return_to_individual_are_offline(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        n = snapshot.cycles[0].point_count
        raw = np.zeros((16, 16, n), dtype=np.int8)
        for e in range(16):
            raw[e, e, 40] = e + 1
        raw[3, 7, 60] = -42
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=n, data_size=1, signed=True, bit_size=0))
        data = FMCData(raw, 16, 16, n, 1, True, 0, metadata=meta)
        self.app._loaded_fmc_view(data)
        previous = vars(self.app.state).copy()
        original = raw.tobytes()
        with patch.object(self.app.controller, 'submit') as submit:
            self.app.fmc_trace_view_var.set('All diagonal traces')
            for norm in ('None', 'Global', 'Per trace'):
                self.app.fmc_diagonal_normalization_var.set(norm)
                self.app.update_data_view()
                self.assertEqual(len(self.app.axes.lines), 16)
                for e, line in enumerate(self.app.axes.lines):
                    np.testing.assert_array_equal(line.get_xdata(), meta.time_us)
                    expected = e + 1 if norm == 'None' else (e + 1) / 16 if norm == 'Global' else 1
                    self.assertAlmostEqual(line.get_ydata()[40], expected)
                    self.assertEqual(line.get_label(), f'TX {e} / RX {e}')
            self.app.fmc_trace_view_var.set('Individual TX/RX')
            self.app.tx_view_var.set(3)
            self.app.rx_view_var.set(7)
            self.app.update_data_view()
            np.testing.assert_array_equal(self.app.axes.lines[0].get_ydata(), raw[3, 7])
            submit.assert_not_called()
        self.assertEqual(vars(self.app.state), previous)
        self.assertEqual(raw.tobytes(), original)
        self.assertIs(data.metadata, meta)

    def test_bscan_normalization_contrast_and_gate_never_submit_or_modify_data(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        n = snapshot.cycles[0].point_count
        raw = np.zeros((16, 16, n), dtype=np.int8)
        raw[0, 0, 5:8] = (-128, 8, 1)
        raw[1, 1, 5:8] = (-8, 4, 1)
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=n, data_size=1, signed=True, bit_size=0))
        data = FMCData(raw, 16, 16, n, 1, True, 0, metadata=meta)
        self.app._loaded_fmc_view(data)
        original, diagonal = raw.tobytes(), self.app.bscan_data.data.tobytes()
        previous = vars(self.app.state).copy()
        with patch.object(self.app.controller, 'submit') as submit:
            self.app.workspace.select(self.app.display_panels['B-scan'])
            self.app.bscan_gate_start_var.set('0')
            self.app.bscan_gate_end_var.set('1')
            for mode in ('RF', 'Absolute'):
                for norm in ('None', 'Global', 'Per trace'):
                    for contrast in ('Linear', 'Boost weak (sqrt)'):
                        self.app.bscan_display_var.set(mode)
                        self.app.bscan_normalization_var.set(norm)
                        self.app.bscan_contrast_var.set(contrast)
                        self.app.change_display()
                        image = self.app.axes.images[0]
                        self.assertEqual(image.get_array().shape[1], 16)
                        self.assertTrue(np.all(np.isfinite(image.get_array())))
                        self.assertIn('display processing only', self.app.inspection_status_var.get())
            submit.assert_not_called()
        self.assertEqual(vars(self.app.state), previous)
        self.assertEqual(raw.tobytes(), original)
        self.assertEqual(self.app.bscan_data.data.tobytes(), diagonal)
        self.assertIs(data.metadata, meta)

    def test_accepted_frame_reports_post_callbacks_without_invalid_label(self):
        from test_ui_fmc_first_frame import FirstFrameTests
        from oempa.fmc_acceptance import first_frame_evidence
        frame, order, raw = FirstFrameTests().evidence('late25')
        cfg = FMCConfig(range_us=.12)
        snapshot = matching_fmc(cfg)
        cube = raw.reshape(16, 16, 7)
        meta = capture_metadata(cube, snapshot, 7, cfg, SimpleNamespace(point_count=7, data_size=1, signed=True, bit_size=0))
        meta = replace(meta, acquisition_acceptance='accepted', frame_evidence=first_frame_evidence(frame, order))
        data = FMCData(cube, 16, 16, 7, 1, True, 0, metadata=meta)
        with patch.object(self.app, 'log') as log, patch.object(self.app.controller, 'submit') as submit:
            self.app._acquisition_success(data)
            messages = '\n'.join(call.args[0] for call in log.call_args_list)
            self.assertIn('first frame 256/256', messages)
            self.assertIn('shutdown callbacks 25', messages)
            self.assertIn('shape (16, 16, 7)', messages)
            self.assertNotIn('[TIMING]', messages)
            self.assertNotIn('Dataset timing:', messages)
            self.assertEqual(log.call_count, 1)
            self.assertNotIn('Additional/invalid', messages)
            submit.assert_not_called()
        np.testing.assert_array_equal(self.app.bscan_data.data, np.array([cube[e, e] for e in range(16)]))
        warned = replace(meta, frame_evidence=replace(meta.frame_evidence, unexpected_post_frame_callbacks=2, malformed_post_frame_callbacks=1, chronology_overflow=True))
        warned_data = FMCData(cube, 16, 16, 7, 1, True, 0, metadata=warned)
        with patch.object(self.app, 'log') as log:
            self.app._acquisition_success(warned_data)
            messages = '\n'.join(call.args[0] for call in log.call_args_list)
            self.assertIn('[WARN] Post-frame unexpected callbacks: 2; malformed: 1', messages)
            self.assertIn('[WARN] Post-frame chronology overflow', messages)
        self.assertIs(warned_data.metadata, warned)

    def test_documented_mapping_and_wiring_are_separate(self):
        probe = self.app.probe_metadata
        self.assertEqual(probe.logical_to_physical, tuple(range(1, 17)))
        self.assertEqual(probe.mapping_source, 'AOS SDK documentation')
        self.assertEqual(probe.physical_wiring_validation, 'Not independently tested')
        self.assertFalse(probe.mapping_verified)
        self.assertEqual(probe.usable_element_count, 16)
        self.assertEqual(probe.aperture_span_mm, 9.0)

    def test_loaded_fmc_remains_historical_without_hardware_state_change(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        n = snapshot.cycles[0].point_count
        raw = np.zeros((16, 16, n), dtype=np.int8)
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=n, data_size=1, signed=True, bit_size=0))
        data = FMCData(raw, 16, 16, n, 1, True, 0, metadata=meta)
        revision = self.app.state.draft_revision
        with patch.object(self.app.controller, 'submit') as submit:
            self.app._loaded_fmc_view(data)
            submit.assert_not_called()
        self.assertEqual(self.app.state.draft_revision, revision)
        self.assertTrue(self.app.state.dataset_stale)
        self.assertIn('Data: Stale', self.app.header_var.get())
        self.assertFalse(self.app.state.acquisition_ready)
        self.assertIs(self.app.fmc_data.metadata, meta)
        self.assertEqual(self.app.bscan_data.shape, (16, n))


    def test_fmc_selection_and_bscan_are_pure_display_for_dynamic_n(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        count = snapshot.cycles[0].point_count
        raw = np.arange(256 * count, dtype=np.int16).reshape(16, 16, count).astype(np.int8)
        original = raw.copy()
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=count, data_size=1, signed=True, bit_size=0), probe=self.app.probe_metadata)
        data = FMCData(raw, 16, 16, count, 1, True, 0, metadata=meta)
        with patch.object(self.app.controller, 'submit') as submit:
            self.app._acquisition_success(data)
            self.app.workspace.select(self.app.display_panels['FMC'])
            self.app.change_display()
            self.app.tx_view_var.set(4)
            self.app.rx_view_var.set(7)
            self.app.update_data_view()
            np.testing.assert_array_equal(self.app.axes.lines[0].get_ydata(), raw[4, 7])
            np.testing.assert_array_equal(self.app.axes.lines[0].get_xdata(), meta.time_us)
            self.assertEqual(self.app.axes.get_title(), 'FMC A-scan - TX 4 / RX 7')
            self.assertIn('Selected: TX 4 / RX 7', self.app.dataset_summary_var.get())
            self.assertIn('AOS-defined', self.app.dataset_summary_var.get())
            self.assertEqual(self.app.bscan_data.shape, (16, count))
            for e in range(16):
                np.testing.assert_array_equal(self.app.bscan_data.data[e], raw[e, e])
            self.app.workspace.select(self.app.display_panels['B-scan'])
            self.app.bscan_gate_start_var.set('0')
            self.app.bscan_gate_end_var.set('1')
            self.app.change_display()
            self.app.bscan_gate_end_var.set('1')
            for mode in ('RF', 'Absolute'):
                self.app.bscan_display_var.set(mode)
                self.app.update_data_view()
                self.assertIn('FMC Diagonal Pulse-Echo B-scan', self.app.axes.get_title())
                self.assertEqual(self.app.axes.get_xlabel(), 'Logical channel')
                self.assertEqual(self.app.axes.get_ylabel(), 'Time (us)')
            submit.assert_not_called()
        np.testing.assert_array_equal(raw, original)

    @classmethod
    def setUpClass(cls):
        stub = ModuleType("oempa.gui_backend")
        stub.GUIBackend = FakeGUIBackend
        spec = importlib.util.spec_from_file_location("phase3_offline_gui", Path(__file__).resolve().parents[1] / "gui.py")
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"oempa.gui_backend": stub}):
            spec.loader.exec_module(cls.module)

    def setUp(self):
        patches = [patch.object(self.module.tk, kind, FakeVariable) for kind in ("StringVar", "IntVar", "DoubleVar")]
        patches.append(patch.object(ui.layout.tk, "Text", Widget))
        patches.append(patch.object(ui.setup_panel.tk, "Canvas", Widget))
        patches.extend(patch.object(ui.layout.ttk, kind, Widget) for kind in ("Frame", "Label", "LabelFrame", "Entry", "Button", "Combobox", "Spinbox", "Notebook", "Panedwindow", "Progressbar", "Scrollbar"))
        patches.append(patch.object(ui.workspace, "FigureCanvasTkAgg", Canvas))
        patches.append(patch.object(ui.workspace, "NavigationToolbar2Tk", lambda canvas, parent, **kwargs: Widget(parent)))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.root = Root()
        self.app = self.module.OEMPAGUI(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.assertFalse(self.app.controller.active)
        self.app._destroyed = True
        for figure, axes, canvas in self.app.plots.values():
            self.module.plt.close(figure)
        self.root.destroy()

    def test_layout_sections_and_placeholders(self):
        self.assertEqual([self.app.workspace.tab(tab, "text") for tab in self.app.workspace.tabs()], ["A-scan", "FMC", "B-scan", "Phased Array", "TFM"])
        self.assertEqual([self.app.setup_notebook.tab(tab, "text") for tab in self.app.setup_notebook.tabs()], ["Device", "Probe", "Acquisition", "Mode Settings"])
        self.assertEqual(self.app.probe_vars["elements"].get(), "32")
        self.assertEqual(self.app.probe_vars["full_marking"].get(), "AOS F5-N32-P0.6mm 8062 C105 S2")
        self.assertEqual(str(self.app.ip_entry["state"]), "readonly")
        self.assertEqual(str(self.app.acquire_button["state"]), "disabled")
        labels = [child.cget("text") for child in self.app.display_panels["TFM"].winfo_children()]
        self.assertIn("Experimental TFM - Homogeneous medium", labels)
        self.assertEqual(str(self.app.tfm_workspace.reconstruct_button["state"]), "disabled")

    def test_modes_block_unsupported_hardware_even_on_direct_submit(self):
        state = self.app.state
        state.connection = ConnectionState.CONNECTED
        state.draft_valid = True
        for mode in ("Phased Array",):
            self.app.mode_var.set(mode)
            self.app.change_mode()
            self.assertFalse(state.apply_ready)
            self.assertEqual(str(self.app.apply_button["state"]), "disabled")
            with self.assertRaises(RuntimeError):
                state.begin(Operation.APPLYING)
        self.app.mode_var.set("FMC")
        self.app.change_mode()
        self.assertTrue(state.apply_ready)

    def test_verified_dirty_mismatch_and_stale_presentation(self):
        state = self.app.state
        state.connection = ConnectionState.CONNECTED
        state.configuration = ConfigurationState.APPLIED
        state.readback_verified = True
        state.applied_revision = state.draft_revision
        state.applied_mode = "FMC"
        state.dataset_revision = state.draft_revision
        self.app._set_busy(False)
        self.assertIn("Config: Verified", self.app.header_var.get())
        self.assertEqual(str(self.app.acquire_button["state"]), "normal")
        self.app.range_var.set("40")
        self.assertIn("Data: Stale", self.app.header_var.get())
        self.assertIn("STALE", self.app.stale_var.get())
        state.verification_mismatches = ("gain: requested 20, readback 21",)
        self.app._set_busy(False)
        self.assertIn("requested 20, readback 21", self.app.warning_var.get())

    def test_metadata_readback_and_selected_waveform(self):
        cfg = FMCConfig()
        snapshot = matching_fmc(cfg, 25e6)
        count = snapshot.cycles[0].point_count
        raw = np.zeros((16, 16, count), dtype=np.int8)
        raw[2, 3, 0] = 42
        meta = capture_metadata(raw, snapshot, 7, cfg, SimpleNamespace(point_count=count, data_size=1, signed=True, bit_size=0))
        data = FMCData(raw, 16, 16, count, 1, True, 0, metadata=meta)
        self.app.state.actual_snapshot = snapshot
        self.app._acquisition_success(data)
        self.assertIn("25 MHz", self.app.dataset_summary_var.get())
        self.assertIn("Rev 7", dataset_summary(data))
        self.assertIn("25 MHz", self.app.readback_var.get())
        self.app.workspace.select(self.app.display_panels["FMC"])
        self.app.change_display()
        self.app.tx_view_var.set(2)
        self.app.rx_view_var.set(3)
        self.app.update_data_view()
        np.testing.assert_allclose(self.app.axes.lines[0].get_xdata()[:3], [0, .04, .08])
        self.assertEqual(self.app.axes.lines[0].get_ydata()[0], 42)
        self.app.workspace.select(self.app.display_panels["B-scan"])
        self.app.change_display()
        self.app.bscan_gate_start_var.set("0")
        self.app.bscan_gate_end_var.set("1")
        self.app.bscan_display_var.set("RF")
        self.app.update_data_view()
        self.assertEqual(len(self.app.axes.images), 1)

    def test_pa_preview_never_submits_device_operation(self):
        self.app.pa_vars["pitch"].set("0.6")
        self.app.pa_vars["velocity"].set("5900")
        self.app.pa_vars["angle"].set("30")
        with patch.object(self.app.controller, "submit") as submit:
            self.app.preview_pa()
            submit.assert_not_called()
        self.assertEqual(len(self.app.pa_law.tx_delays_us), 16)
        self.assertIn("Offline", self.app.pa_summary_var.get())
        self.assertIn("0.764 us", self.app.pa_summary_var.get())
        self.assertIn("30 deg", self.app.pa_summary_var.get())
        self.assertLess(len(self.app.pa_summary_var.get()), 140)
        self.app.pa_vars["pitch"].set("nan")
        self.app.preview_pa()
        self.assertIsNone(self.app.pa_law)

    def test_stop_and_close_use_controller(self):
        with patch.object(self.app.controller, "cancel") as cancel:
            self.app.stop_operation()
            cancel.assert_called_once()
        with patch.object(self.app.controller, "request_shutdown") as shutdown:
            self.app.on_close()
            shutdown.assert_called_once_with(self.app.backend.close)

    def test_operation_locks_setup_and_enables_cooperative_stop(self):
        self.app.state.operation = Operation.ACQUIRING
        with patch.object(type(self.app.controller), "active", new_callable=lambda: property(lambda controller: True)):
            self.app._set_busy(False)
        self.assertEqual(str(self.app.mode_selector["state"]), "disabled")
        self.assertTrue(all(entry["state"] == "disabled" for entry in self.app.config_entries))
        self.assertEqual(str(self.app.stop_button["state"]), "normal")
        self.assertEqual(str(self.app.preview_button["state"]), "disabled")

    def test_preview_edit_invalidates_law_without_hardware_revision(self):
        self.app.pa_vars["pitch"].set("0.6")
        self.app.pa_vars["velocity"].set("5900")
        self.app.preview_pa()
        self.assertIsNotNone(self.app.pa_law)
        revision = self.app.state.draft_revision
        self.app.pa_vars["angle"].set("10")
        self.assertIsNone(self.app.pa_law)
        self.assertEqual(self.app.state.draft_revision, revision)


    def test_single_element_mode_draft_and_readiness_gate(self):
        self.app.mode_var.set("A-scan")
        self.app.change_mode()
        c = self.app._read_configuration()
        self.assertEqual((c.tx_element, c.rx_element, c.pulser_width_us, c.start_us, c.range_us), (0, 0, .5, 0, 30))
        self.assertEqual(self.app.acquire_button["text"], "Acquire A-scan")
        self.assertFalse(self.app.state.acquisition_ready)
        self.app.state.connection = ConnectionState.CONNECTED
        self.app._set_busy(False)
        self.assertTrue(self.app.state.apply_ready)
        self.assertFalse(self.app.state.acquisition_ready)
        self.app.ascan_vars["rx"].set("16")
        self.assertFalse(self.app.state.draft_valid)
        self.assertFalse(self.app.state.apply_ready)


    def test_single_element_display_preserves_signed_samples_and_metadata(self):
        from oempa.ascan_config import SingleElementAscanConfig
        from oempa.dataset import AcquisitionDataset, capture_metadata, load_dataset
        from test_ui_single_ascan import matching
        from types import SimpleNamespace
        from pathlib import Path
        import tempfile
        c = SingleElementAscanConfig(tx_element=3, rx_element=7, start_us=2)
        raw = np.arange(751).astype(np.int8)
        metadata = capture_metadata(raw, matching(c), self.app.state.draft_revision, c,
                                    SimpleNamespace(point_count=751, data_size=1, signed=True, bit_size=0))
        self.app._acquisition_success(AcquisitionDataset(raw, metadata))
        line = self.app.axes.lines[0]
        np.testing.assert_array_equal(line.get_ydata(), raw)
        np.testing.assert_allclose(line.get_xdata()[[0,1,-1]], [2,2.04,32])
        self.assertEqual(self.app.axes.get_title(), 'Single-element A-scan - TX 3 / RX 7')
        self.assertEqual(self.app.axes.get_xlabel(), 'Time (us)')
        self.assertEqual(self.app.axes.get_ylabel(), 'Signed amplitude')
        summary = self.app.dataset_summary_var.get()
        self.assertEqual(len(summary.splitlines()), 3)
        self.assertIn('TX 3 / RX 7    Pulse width: 0.5 us    Gain: 20 / 0 dB', summary)
        self.assertIn('Start: 2 us    Range: 30 us    Sampling: 25 MHz    Samples: 751', summary)
        self.assertIs(self.app.ascan_data.metadata, metadata)
        self.assertIn("RX 7", self.app.dataset_summary_var.get())
        self.assertIn("Unverified", self.app.dataset_summary_var.get())
        self.assertIsNone(self.app.fmc_data)
        self.assertIsNone(self.app.bscan_data)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'ascan.npy')
            with patch.object(self.module.filedialog, 'asksaveasfilename', return_value=path):
                self.app.save_fmc()
            saved = load_dataset(path)
        np.testing.assert_array_equal(saved.data, raw)
        self.assertEqual(saved.metadata.requested_parameters, metadata.requested_parameters)
        self.app.state.dataset_revision = self.app.state.draft_revision
        self.app.state.dataset_mode = 'A-scan'
        self.app.range_var.set('40')
        self.assertIn('stale', self.app.axes.get_title())
        self.assertAlmostEqual(self.app.ascan_data.metadata.timing.range_s, 30e-6)


    def _apply_ascan_over_existing_fmc(self, hardware_stays_fmc, missed_mode_event=False):
        import test_ui_backend_offline as fixture
        from test_ui_single_ascan import matching
        from oempa.ascan_config import SingleElementAscanConfig
        from oempa.config import FMCConfig
        from oempa.hardware_state import AppliedFMCConfiguration
        from ui_readback_fakes import FakeReadbackAPI, matching_fmc
        from unittest.mock import Mock
        import time
        fixture.BackendTests.setUp(self)
        # The fake GUI import removes newly imported modules on exit; align its retained class reference.
        config_class = patch.object(self.module, "SingleElementAscanConfig", self.backend_module.SingleElementAscanConfig)
        config_class.start()
        self.addCleanup(config_class.stop)
        old = matching_fmc(FMCConfig())
        backend = self.backend_module.GUIBackend('unused/gui_fmc_config.txt')
        backend.applied_snapshot = old
        backend.requested_configuration = FMCConfig()
        backend.applied_fmc_provenance = AppliedFMCConfiguration('previous', 'previous-hash', tuple(i % 16 == 0 for i in range(256)), (), 256, (True,)*4, True)
        backend.device = Mock(handle='fake')
        backend.acquisition = Mock()
        new_config = SingleElementAscanConfig()
        reader = FakeReadbackAPI(old if hardware_stays_fmc else matching(new_config))
        backend.device.refresh_status.return_value = dict(cycle_count=256 if hardware_stays_fmc else 1,
                                                        multichannel_supported=True, multichannel_enabled=hardware_stays_fmc)
        self.app.backend = backend
        self.app.state.connection = ConnectionState.CONNECTED
        self.app.state.actual_snapshot = old
        # No synthetic combobox event: the selected variable must itself reach controller state.
        if missed_mode_event:
            callbacks = self.app.mode_var.callbacks
            self.app.mode_var.callbacks = []
            self.app.mode_var.set('A-scan')
            self.app.mode_var.callbacks = callbacks
            self.assertEqual(self.app.state.mode, 'FMC')
        else:
            self.app.mode_var.set('A-scan')
            self.assertEqual(self.app.state.mode, 'A-scan')
        fresh_status = backend.device.refresh_status.return_value
        def refresh_after_load():
            backend.device.load_configuration.assert_called_once()
            return fresh_status
        backend.device.refresh_status.side_effect = refresh_after_load
        with patch.object(self.backend_module, 'api', reader), patch.object(self.backend_module.SingleElementAscanConfigBuilder, 'save') as save, \
             patch.object(backend, 'apply_ascan', wraps=backend.apply_ascan) as apply_ascan, \
             patch.object(self.backend_module, 'verify_configuration', wraps=self.backend_module.verify_configuration) as verify:
            self.app.apply_configuration()
            deadline = time.monotonic() + 3
            while self.app.controller.active and time.monotonic() < deadline:
                time.sleep(.002)
                self.app._consume_events()
            self.assertFalse(self.app.controller.active)
            self.assertEqual(apply_ascan.call_count, 1, str(self.app.state.error) + " | " + self.app.warning_var.get())
            requested = apply_ascan.call_args.args[1]
            self.assertIsInstance(requested, SingleElementAscanConfig)
            self.assertEqual(requested.cycle_count, 1)
            save.assert_called_once()
            backend.device.load_configuration.assert_called_once()
            backend.device.refresh_status.assert_called_once()
            self.assertEqual(verify.call_count, 1)
            self.assertEqual(verify.call_args.args[1].mode, 'A-scan')
            self.assertIsNone(verify.call_args.args[1].applied_configuration)
        self.assertIsNone(backend.applied_fmc_provenance)
        self.assertIsNot(self.app.state.actual_snapshot, old)
        if hardware_stays_fmc:
            self.assertFalse(self.app.state.acquisition_ready)
            self.assertEqual(self.app.state.actual_snapshot.cycle_count, 256)
            self.assertEqual(reader.calls, [])
            warning = self.app.warning_var.get()
            self.assertIn('A-scan configuration verification failed', warning)
            self.assertIn('Expected cycles: 1', warning)
            self.assertIn('Observed cycles: 256', warning)
            self.assertLessEqual(len(warning), 700)
            self.assertNotIn('hw_acquisition', warning)
        else:
            self.assertTrue(self.app.state.acquisition_ready)
            self.assertTrue(self.app.state.readback_verified)
            self.assertEqual(self.app.state.applied_mode, 'A-scan')
            self.assertEqual(self.app.state.actual_snapshot.cycle_count, 1)
            self.assertFalse(self.app.state.actual_snapshot.multichannel_enabled)
            self.assertEqual(reader.calls, [('cycle', 0), ('extended', 0)])

    def test_fmc_to_ascan_apply_success_routes_selected_mode_and_fresh_snapshot(self):
        self._apply_ascan_over_existing_fmc(False)

    def test_fmc_to_ascan_apply_unchanged_hardware_is_bounded_failure(self):
        self._apply_ascan_over_existing_fmc(True)

    def test_error_banner_and_detail_log_are_bounded(self):
        self.app.state.verification_mismatches = tuple('cycle[%d].gain: requested 20 observed 21' % i for i in range(256))
        self.app._refresh_presentation()
        self.assertLessEqual(len(self.app.warning_var.get()), 700)
        with patch.object(self.app, 'log') as log:
            self.app._log_readback()
        self.assertEqual(log.call_count, 21)
        self.assertIn('236 additional', log.call_args.args[0])
        self.assertEqual(len(self.app.state.verification_mismatches), 256)


    def test_apply_resynchronizes_selected_ascan_after_missed_mode_event(self):
        self._apply_ascan_over_existing_fmc(False, missed_mode_event=True)


    def test_ascan_mode_settings_groups_and_readonly_logical_selectors(self):
        self.app.mode_var.set('A-scan')
        mode_panel = self.app.setup_notebook.tabs()[3]
        self.assertIn('Acquisition Mode', [w.cget('text') for w in mode_panel.children])
        self.assertEqual([w.cget('text') for w in self.app.ascan_settings.children], ['Channels', 'Advanced'])
        channels, timing = self.app.ascan_settings.children
        labels = [w.cget('text') for w in channels.children if w.cget('text')]
        self.assertIn('Transmit (TX)', labels)
        self.assertIn('Receive (RX)', labels)
        self.assertIn('Logical OEM-PA channels 0-15\nAOS-defined probe elements 1-16\nPhysical wiring: Not independently tested', labels)
        self.assertEqual(len(self.app.channel_selectors), 2)
        for selector in self.app.channel_selectors:
            self.assertEqual(selector['values'], tuple(str(i) for i in range(16)))
            self.assertEqual(selector['state'], 'readonly')
        timing_labels = [w.cget('text') for w in timing.children if w.cget('text')]
        self.assertEqual(timing_labels, ['TX Delay', 'us', 'RX Delay', 'us'])
        self.app.ascan_vars['tx'].set('15')
        self.app.ascan_vars['rx'].set('7')
        c = self.app._read_configuration()
        self.assertEqual((c.tx_element, c.rx_element), (15, 7))
        self.app.state.operation = Operation.ACQUIRING
        with patch.object(type(self.app.controller), 'active', new_callable=lambda: property(lambda controller: True)):
            self.app._set_busy(False)
        self.assertTrue(all(w['state'] == 'disabled' for w in self.app.channel_selectors))
        self.app.state.operation = Operation.IDLE
        self.app._set_busy(False)
        self.assertTrue(all(w['state'] == 'readonly' for w in self.app.channel_selectors))

    def test_production_visible_microsecond_labels_are_ascii(self):
        def visit(widget):
            for child in widget.children:
                text = child.cget('text') or ''
                self.assertNotIn('\u00b5s', text)
                self.assertNotIn('\u03bcs', text)
                self.assertNotIn('?s', text)
                self.assertNotIn('0?15', text)
                visit(child)
        visit(self.root)
        original = 'Range 30 \u00b5s; TX delay 0 \u03bcs'
        self.app.state.status = original
        self.app._refresh_presentation()
        self.assertEqual(self.app.warning_var.get(), 'Range 30 us; TX delay 0 us')
        self.assertEqual(self.app.state.status, original)


    def test_probe_edits_are_metadata_only_and_preserve_mapping_limitation(self):
        revision = self.app.state.draft_revision
        description = self.app.probe_metadata.description
        self.assertEqual(dict(description.values)['elements'], '32')
        self.assertEqual(dict(description.sources)['frequency'], 'inferred_unverified')
        self.assertFalse(description.frequency_verified)
        self.assertFalse(self.app.probe_metadata.mapping_verified)
        self.assertEqual(self.app.probe_metadata.logical_to_physical, tuple(range(1, 17)))
        self.assertEqual(self.app.probe_metadata.physical_wiring_validation, 'Not independently tested')
        self.app.probe_vars['model'].set('Manual label edit')
        self.assertEqual(dict(self.app.probe_metadata.description.sources)['model'], 'user_entered')
        self.assertEqual(self.app.state.draft_revision, revision)
        self.assertIsNone(self.app.pa_law)
        self.assertFalse(self.app.controller.active)

    def test_common_controls_and_mode_settings_do_not_duplicate_start(self):
        self.assertEqual(self.app.mode_selector['values'], ('A-scan', 'FMC', 'Phased Array'))
        self.app.mode_var.set('A-scan')
        self.assertEqual(self.app.start_entry['textvariable'], self.app.ascan_vars['start'])
        def variables(widget):
            result = []
            for child in widget.children:
                if child.cget('textvariable') is not None:
                    result.append(child.cget('textvariable'))
                result.extend(variables(child))
            return result
        self.assertNotIn(self.app.ascan_vars['start'], variables(self.app.ascan_settings))
        self.assertIn(self.app.pulser_width_var, variables(self.app.acquisition_form))
        self.app.ascan_vars['start'].set('2')
        self.app.ascan_vars['tx'].set('7')
        self.app.mode_var.set('FMC')
        self.assertEqual(self.app.start_entry.manager, None)
        self.assertEqual(self.app._read_configuration().cycle_count, 256)
        self.app.mode_var.set('Phased Array')
        self.assertEqual(self.app.pa_settings.manager, 'grid')
        self.assertEqual(self.app.acquire_button['text'], 'Acquire PA')
        self.assertEqual(self.app.acquire_button['state'], 'disabled')
        self.app.mode_var.set('A-scan')
        self.assertEqual((self.app._read_configuration().start_us, self.app._read_configuration().tx_element), (2, 7))
        self.assertEqual(self.app.start_entry.manager, 'grid')

    def test_readback_text_is_actual_and_never_uses_draft_sampling(self):
        from test_ui_single_ascan import matching
        from oempa.ascan_config import SingleElementAscanConfig
        self.app.state.actual_snapshot = matching(SingleElementAscanConfig(start_us=2))
        self.app.range_var.set('40')
        self.app._refresh_presentation()
        text = self.app.readback_var.get()
        self.assertIn('25 MHz', text)
        self.assertIn('Samples: 751', text)
        self.assertIn('2 us / 30 us', text)
        self.assertIn('Signed 8-bit', text)
        self.assertIn('Compression: Compression', text)

    def test_clear_log_only_clears_visible_text(self):
        self.app.log('[WARN] Test warning')
        before = tuple(self.app.diagnostic_history.records)
        revision = self.app.state.draft_revision
        actual = self.app.state.actual_snapshot
        dataset = self.app.fmc_data
        self.app.clear_log()
        self.assertEqual(tuple(self.app.diagnostic_history.records), before)
        self.assertEqual(self.app._visible_log_lines, 0)
        self.assertEqual(self.app.state.draft_revision, revision)
        self.assertIs(self.app.state.actual_snapshot, actual)
        self.assertIs(self.app.fmc_data, dataset)
        self.assertEqual(self.app.log_text['state'], 'disabled')
        self.assertEqual(self.app.vertical_panes['orient'], 'vertical')
        self.assertEqual(self.app.log_text['wrap'], 'word')
