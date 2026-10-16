"""TFM UI/state/worker workflows with fake Tk/backend; no DLL or device import."""

from pathlib import Path
from dataclasses import replace
import json
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

import test_ui_phase3 as phase3
from tfm_synthetic import point_reflector
from oempa.dataset import AcquisitionDataset, ProbeProvenance, save_dataset
from oempa.fmc import FMCData
from oempa.probe import ProbeDescription, PROBE_DEFAULTS, DOCUMENTED_MAPPING, MAPPING_SOURCE
from ui.controller import OperationResult
from ui.state import ConnectionState, ConfigurationState, Operation


class TFMWorkspaceTests(unittest.TestCase):
    setUpClass = classmethod(phase3.ProductionLayoutTests.setUpClass.__func__)
    setUp = phase3.ProductionLayoutTests.setUp
    tearDown = phase3.ProductionLayoutTests.tearDown

    def test_tfm_equal_aspect_layout_is_centered_and_responsive_without_reconstruction(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        raw = result.image.copy()
        figure, axes, canvas = self.app.plots['TFM']
        with patch('ui.tfm_workspace.reconstruct') as reconstruct:
            for width, height in ((904, 302), (704, 212), (428, 212), (904, 302)):
                figure.set_size_inches(width / figure.dpi, height / figure.dpi)
                for mode in ('normalized', 'db', 'raw', 'absolute'):
                    view.variables['display'].set(mode)
                    canvas.draw()
                    renderer = canvas.get_renderer()
                    image = axes.get_window_extent(renderer)
                    bar = view.colorbar.ax.get_window_extent(renderer)
                    self.assertLess(abs((image.x0 + bar.x1) / 2 - width / 2), width * .08)
                    self.assertGreater(image.height, height * .55)
                    self.assertLess(bar.width, image.width * .08)
                    self.assertGreaterEqual(bar.x0, image.x1)
                    self.assertLess(bar.x0 - image.x1, image.width * .2)
                    self.assertAlmostEqual(image.width / image.height, 1, places=6)
                    for text in (axes.xaxis.label, axes.yaxis.label, axes.title, view.colorbar.ax.yaxis.label):
                        box = text.get_window_extent(renderer)
                        self.assertGreaterEqual(box.x0, -2)
                        self.assertLessEqual(box.x1, width + 2)
                        self.assertGreaterEqual(box.y0, -2)
                        self.assertLessEqual(box.y1, height + 2)
                    self.assertEqual(axes.get_xlim(), (-4, 4))
                    self.assertEqual(axes.get_ylim(), (12, 4))
            reconstruct.assert_not_called()
        self.assertIs(view.state.result, result)
        np.testing.assert_array_equal(result.image, raw)

    def test_production_defaults_and_explicit_water_preset_are_offline(self):
        view = self.app.tfm_workspace
        self.assertEqual(view.variables['method'].get(), 'linear')
        self.assertEqual(view.variables['display'].get(), 'normalized')
        for name, value in (('x_min', '-10'), ('x_max', '10'), ('z_min', '2'), ('z_max', '25'), ('x_count', '201'), ('z_count', '231')):
            self.assertEqual(view.variables[name].get(), value)
        self.assertEqual(view.variables['velocity'].get(), '')
        mode = self.app.state.mode
        with patch.object(self.app.controller, 'submit') as submit:
            view.water_button['command']()
            self.assertEqual(view.variables['velocity'].get(), '1480')
            submit.assert_not_called()
        self.assertEqual(self.app.state.mode, mode)

    def test_current_cube_prefills_dataset_pitch_not_full_probe_element_count(self):
        source = point_reflector(16, .0006, 1480, 0, .01, 100e6, 0, 3001)
        probe = ProbeProvenance(description=ProbeDescription.from_values(PROBE_DEFAULTS), logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE)
        source = AcquisitionDataset(source.data, replace(source.metadata, probe=probe))
        self.app.fmc_data = FMCData(source.data, 16, 16, 3001, 1, True, 0, metadata=source.metadata)
        self.app.state.dataset_stale = False
        view = self.app.tfm_workspace
        with patch.object(self.app.backend, 'acquire') as acquire, patch.object(self.app.backend, 'apply') as apply:
            view.use_current()
            self.assertEqual(view.variables['pitch'].get(), '0.6')
            view.variables['velocity'].set('1480')
            request = view.read_request()
            self.assertEqual(request.geometry.element_count, 16)
            self.assertIn('Dataset probe metadata', request.geometry_origin)
            self.assertIn('full probe label: 32', view.geometry_var.get())
            self.assertIn('Span: 9 mm', view.geometry_var.get())
            self.assertIn('elements 1-16', view.geometry_var.get())
            view.start_reconstruction()
            self.pump()
            self.assertEqual(view.state.result.image.shape, (231, 201))
            self.assertIs(view.state.result.source_metadata, source.metadata)
            acquire.assert_not_called()
            apply.assert_not_called()

    def test_main_fmc_replacement_invalidates_current_result_without_recomputing(self):
        view, source = self.source_ready()
        self.app.fmc_data = FMCData(source.data, 4, 4, 512, 1, True, 0, metadata=source.metadata)
        view.use_current()
        view.variables['pitch'].set('.6')
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        replacement = replace(source.metadata, configuration_revision=13)
        self.app.fmc_data = FMCData(source.data, 4, 4, 512, 1, True, 0, metadata=replacement)
        with patch('ui.tfm_workspace.reconstruct') as reconstruct, patch.object(self.app.controller, 'submit') as submit:
            view.refresh()
            self.assertTrue(view.state.stale)
            self.assertEqual(view.reconstruct_button['state'], 'disabled')
            self.assertIs(view.state.result, result)
            self.assertIn('STALE', self.app.plots['TFM'][1].get_title())
            view.variables['display'].set('db')
            self.app.workspace.select(self.app.display_panels['FMC'])
            self.app.change_display()
            self.app.workspace.select(self.app.display_panels['TFM'])
            self.app.change_display()
            reconstruct.assert_not_called()
            submit.assert_not_called()

    def test_every_reconstruction_parameter_marks_old_result_stale(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        for name, value in (('velocity', '1480'), ('x_min', '-3'), ('x_max', '3'), ('z_min', '5'), ('z_max', '11'), ('x_count', '21'), ('z_count', '31'), ('method', 'nearest')):
            view.state.result_revision = view.state.revision
            with patch('ui.tfm_workspace.reconstruct') as reconstruct:
                view.variables[name].set(value)
                self.assertTrue(view.state.stale)
                self.assertIs(view.state.result, result)
                reconstruct.assert_not_called()

    def test_gui_save_result_is_offline_and_retains_raw_signed_image(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.pump()
        before = view.state.result.image.copy()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'result.npz'
            with patch('ui.tfm_workspace.filedialog.asksaveasfilename', return_value=str(path)), patch.object(self.app.backend, 'acquire') as acquire, patch.object(self.app.backend, 'apply') as apply:
                view.save_result()
                self.pump()
                acquire.assert_not_called()
                apply.assert_not_called()
            with np.load(path, allow_pickle=False) as loaded:
                np.testing.assert_array_equal(loaded['image'], before)
                metadata = json.loads(str(loaded['metadata_json']))
                self.assertEqual(metadata['request']['method'], 'linear')
                self.assertEqual(metadata['source_configuration_revision'], 12)
                self.assertEqual(metadata['propagation_model'], 'Homogeneous medium')
        np.testing.assert_array_equal(view.state.result.image, before)

    def test_complete_offline_sidecar_supplies_pitch_and_authoritative_timing(self):
        source = point_reflector(4, .0006, 1480, 0, .006, 25e6, 2e-6, 512)
        raw = (source.data * 100).astype(np.int8)
        probe = ProbeProvenance(description=ProbeDescription.from_values(PROBE_DEFAULTS), logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE)
        hardware = replace(source.metadata.hardware, cycles=tuple(replace(c, point_factor=256, bit_size=0, rectification=0, compression_type=0) for c in source.metadata.hardware.cycles))
        metadata = replace(source.metadata, dtype=raw.dtype.str, hardware=hardware, probe=probe, signed=True, data_size=1, bit_size=0)
        view = self.app.tfm_workspace
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.npy'
            save_dataset(path, raw, metadata)
            view.load_source(path)
            self.pump()
        self.assertTrue(view.state.source.metadata.complete)
        self.assertEqual(view.variables['pitch'].get(), '0.6')
        self.assertEqual(view.variables['sampling'].get(), '')
        self.assertEqual(view.entries['sampling']['state'], 'disabled')
        view.variables['velocity'].set('1480')
        view.start_reconstruction()
        self.pump()
        self.assertEqual(view.state.result.sampling_hz, 25e6)
        self.assertEqual(view.state.result.start_s, 2e-6)

    def pump(self):
        deadline = time.monotonic() + 3
        while self.app.controller.active and time.monotonic() < deadline:
            self.app._consume_events()
            time.sleep(.001)
        self.assertFalse(self.app.controller.active)
        if not self.root.destroyed:
            self.app._consume_events()

    def source_ready(self):
        view = self.app.tfm_workspace
        source = point_reflector(4, .0006, 3000, .001, .008, 20e6, 1e-6, 512)
        view.accept_source(source, "synthetic validation ONLY")
        for name, value in (("pitch", ".6"), ("velocity", "3000"), ("x_min", "-4"), ("x_max", "4"), ("z_min", "4"), ("z_max", "12"), ("x_count", "41"), ("z_count", "41")):
            view.variables[name].set(value)
        return view, source

    def test_no_source_or_assumptions_blocks_reconstruction(self):
        view = self.app.tfm_workspace
        self.assertIsNone(view.state.source)
        for name in ("pitch", "velocity", "sampling", "start"):
            self.assertEqual(view.variables[name].get(), "")
        self.assertEqual(view.reconstruct_button["state"], "disabled")
        self.assertEqual(view.current_button["state"], "disabled")
        self.assertEqual(self.app.state.connection, ConnectionState.DISCONNECTED)

    def test_offline_file_loading_requires_explicit_legacy_timing(self):
        view = self.app.tfm_workspace
        revision = self.app.state.draft_revision
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.npy"
            np.save(path, np.zeros((4, 4, 512), dtype=np.int8))
            view.load_source(path)
            self.assertEqual(view.open_button["state"], "disabled")
            self.pump()
        self.assertFalse(view.state.source.metadata.complete)
        self.assertIsNone(view.state.source.metadata.hardware)
        for name, value in (("pitch", ".6"), ("velocity", "3000"), ("sampling", "25")):
            view.variables[name].set(value)
        self.assertEqual(view.reconstruct_button["state"], "disabled")
        view.variables["start"].set("2")
        self.assertEqual(view.reconstruct_button["state"], "normal")
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        self.assertEqual(result.sampling_hz, 25e6)
        self.assertEqual(result.start_s, 2e-6)
        self.assertIsNone(result.source_metadata.hardware)
        self.assertIn("user assumption", result.timing_origin)
        self.assertEqual(self.app.state.draft_revision, revision)
        self.assertIsNone(self.app.state.dataset_revision)
        self.assertFalse(self.app.state.acquisition_ready)

    def test_metadata_timing_is_authoritative_and_locked(self):
        view, source = self.source_ready()
        self.assertEqual(view.entries["sampling"]["state"], "disabled")
        self.assertIn("20 MHz", view.source_var.get())
        view.variables["sampling"].set("100")
        view.start_reconstruction()
        self.pump()
        self.assertEqual(view.state.result.sampling_hz, 20e6)
        self.assertIs(view.state.result.source_metadata, source.metadata)
        self.assertIn("Rev 12", view.provenance_var.get())
        self.assertIn("Probe/channel mapping: Unverified", view.provenance_var.get())

    def test_reconstruction_does_not_require_connection_and_returns_idle(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.assertEqual(self.app.state.operation, Operation.RECONSTRUCTING)
        self.assertTrue(all(entry["state"] == "disabled" for entry in view.entries.values()))
        self.assertEqual(self.app.stop_button["state"], "normal")
        self.pump()
        self.assertEqual(self.app.state.operation, Operation.IDLE)
        self.assertEqual(self.app.state.connection, ConnectionState.DISCONNECTED)
        self.assertIsNone(self.app.backend.device if hasattr(self.app.backend, "device") else None)
        self.assertIsNotNone(view.state.result)
        self.assertFalse(view.settings_visible)
        view.toggle_settings()
        self.assertTrue(view.settings_visible)
        view.toggle_settings()
        self.assertEqual(self.app.progress_var.get(), 100)

    def test_display_modes_colorbar_axes_and_raw_image_are_separate(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        before = result.image.copy()
        figure, axes, canvas = self.app.plots["TFM"]
        colorbar = view.colorbar
        for mode in ("raw", "absolute", "normalized", "db", "absolute"):
            view.variables["display"].set(mode)
            self.assertEqual(len(figure.axes), 2)
            self.assertIs(view.colorbar, colorbar)
            self.assertEqual(axes.get_xlabel(), "Lateral position (mm)")
            self.assertEqual(axes.get_ylabel(), "Depth (mm)")
            self.assertEqual(axes.get_xlim(), (-4, 4))
            self.assertEqual(axes.get_ylim(), (12, 4))
            self.assertEqual(axes.get_aspect(), 1)
            self.assertFalse(view.state.stale)
        np.testing.assert_equal(result.image, before)

    def test_assumption_edit_marks_image_stale_preserving_provenance(self):
        view, source = self.source_ready()
        revision = self.app.state.draft_revision
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        view.variables["pitch"].set(".7")
        self.assertTrue(view.state.stale)
        self.assertIn("STALE", self.app.plots["TFM"][1].get_title())
        self.assertIs(view.state.result, result)
        self.assertEqual(result.request.geometry.pitch_m, .0006)
        self.assertEqual(self.app.state.draft_revision, revision)
        view.start_reconstruction()
        self.pump()
        self.assertFalse(view.state.stale)

    def test_invalid_request_and_rectangular_file_are_blocked(self):
        view, source = self.source_ready()
        view.variables["velocity"].set("nan")
        self.assertEqual(view.reconstruct_button["state"], "disabled")
        view.start_reconstruction()
        self.assertFalse(self.app.controller.active)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not_square.npy"
            np.save(path, np.zeros((2, 3, 4), dtype=np.int8))
            view.load_source(path)
            self.pump()
        self.assertIs(view.state.source, source)
        self.assertIn("square", view.status_var.get())

    def test_source_replacement_keeps_old_image_provenance_until_reconstruct(self):
        view, source = self.source_ready()
        view.start_reconstruction()
        self.pump()
        result = view.state.result
        replacement = point_reflector(4, .0006, 3000, 0, .009, 30e6, 1e-6, 512)
        view.accept_source(replacement, "replacement synthetic ONLY")
        self.assertTrue(view.state.stale)
        self.assertIs(view.state.result.source_metadata, source.metadata)
        self.assertEqual(view.state.result.source_label, result.source_label)
        # A replacement without pitch metadata must not inherit another source's assumption.
        self.assertEqual(view.variables['pitch'].get(), '')
        self.assertEqual(view.reconstruct_button['state'], 'disabled')
        view.variables['pitch'].set('.6')
        view.start_reconstruction()
        self.pump()
        self.assertIs(view.state.result.source_metadata, replacement.metadata)
        self.assertEqual(view.state.result.sampling_hz, 30e6)

    def test_use_current_legacy_fmc_never_adopts_gui_timing_or_revises_hardware(self):
        self.app.connect_device()
        self.pump()
        self.app.apply_configuration()
        self.pump()
        self.app.acquire_fmc()
        self.pump()
        revision = self.app.state.draft_revision
        view = self.app.tfm_workspace
        view.use_current()
        self.assertIs(view.state.source.data, self.app.fmc_data.data)
        self.assertFalse(view.state.source.metadata.complete)
        self.assertIsNone(view.state.source.metadata.hardware)
        self.assertEqual(view.variables["sampling"].get(), "")
        self.assertEqual(view.reconstruct_button["state"], "disabled")
        self.assertEqual(self.app.state.draft_revision, revision)
        self.app.analog_gain_var.set("21")
        self.assertIn("historical/stale", view.status_var.get())

    def test_offline_error_does_not_forget_verified_hardware_truth(self):
        self.app.connect_device()
        self.pump()
        self.app.apply_configuration()
        self.pump()
        revision = self.app.state.applied_revision
        self.app.tfm_workspace.load_source("missing_source_file.npy")
        self.pump()
        self.assertTrue(self.app.state.readback_verified)
        self.assertEqual(self.app.state.applied_revision, revision)
        self.assertEqual(self.app.state.configuration, ConfigurationState.APPLIED)
        self.assertEqual(self.app.state.connection, ConnectionState.CONNECTED)

    def test_cancelled_reconstruction_releases_owner(self):
        view, source = self.source_ready()
        def wait_for_cancel(source, request, **kwargs):
            while True:
                kwargs["cancel_check"]()
                time.sleep(.001)
        with patch("ui.tfm_workspace.reconstruct", wait_for_cancel):
            view.start_reconstruction()
            with self.assertRaises(RuntimeError):
                self.app.controller.submit(Operation.LOADING, lambda context: OperationResult())
            self.app.stop_operation()
            self.pump()
        self.assertIsNone(view.state.result)
        self.assertEqual(self.app.state.operation, Operation.IDLE)
        self.assertIn("cancelled", view.status_var.get())

    def test_close_waits_for_reconstruction_and_cleanup(self):
        view, source = self.source_ready()
        def wait_for_cancel(source, request, **kwargs):
            while True:
                kwargs["cancel_check"]()
                time.sleep(.001)
        with patch("ui.tfm_workspace.reconstruct", wait_for_cancel), patch.object(self.module.messagebox, "askyesno", return_value=True):
            view.start_reconstruction()
            self.app.on_close()
            self.assertFalse(self.root.destroyed)
            self.pump()
        self.assertTrue(self.root.destroyed)
        self.assertTrue(self.app.state.shutdown_complete)
        self.assertTrue(self.app.backend.closed)


if __name__ == "__main__":
    unittest.main()
