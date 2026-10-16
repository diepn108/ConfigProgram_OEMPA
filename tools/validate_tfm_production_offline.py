"""Real Tk TFM validation using synthetic current/offline FMC, never the SDK."""

from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import tkinter as tk
import traceback
from types import ModuleType
from unittest.mock import patch

import numpy as np
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from ui.controller import OperationResult


class OfflineBackend:
    def __init__(self, path):
        self.device = None

    def connect(self, *args):
        raise AssertionError('No hardware operations allowed in this offline validation')

    apply = connect
    acquire = connect

    def close(self, context):
        return OperationResult(connected=False)


stub = ModuleType('oempa.gui_backend')
stub.GUIBackend = OfflineBackend
sys.modules['oempa.gui_backend'] = stub
from gui import OEMPAGUI
from oempa.dataset import AcquisitionDataset, ProbeProvenance, save_dataset
from oempa.fmc import FMCData
from oempa.probe import ProbeDescription, PROBE_DEFAULTS, DOCUMENTED_MAPPING, MAPPING_SOURCE
from tfm_synthetic import point_reflector
import ui.tfm_workspace as tfm_ui


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/tfm_production_offline_20261015')
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    fixture = point_reflector(16, .0006, 1480, .001, .012, 100e6, 0, 3001)
    raw = (fixture.data * 100).astype(np.int8)
    probe = ProbeProvenance(description=ProbeDescription.from_values(PROBE_DEFAULTS), logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE)
    hardware = replace(fixture.metadata.hardware, cycles=tuple(replace(cycle, point_factor=256, bit_size=0, rectification=0, compression_type=0) for cycle in fixture.metadata.hardware.cycles))
    metadata = replace(fixture.metadata, hardware=hardware, dtype=raw.dtype.str, probe=probe, data_size=1, signed=True, bit_size=0,
                       acquisition_acceptance='Synthetic offline fixture, not hardware acquisition')
    fixture = AcquisitionDataset(raw, metadata)
    source_path = output / 'synthetic_fmc.npy'
    save_dataset(source_path, raw, metadata)
    before = hashlib.sha256(raw.tobytes()).hexdigest()
    report = {'source': 'Synthetic 16x16x3001 fixture ONLY', 'errors': [], 'layouts': [], 'computations': [], 'ticks': [], 'closing_test': False}
    root = tk.Tk()
    root.attributes('-topmost', True)
    root.geometry('1300x820+20+20')
    app = OEMPAGUI(root)
    view = app.tfm_workspace
    app.workspace.select(app.display_panels['TFM'])
    root.report_callback_exception = lambda kind, value, trace: report['errors'].append(''.join(traceback.format_exception(kind, value, trace)))
    numerical_reconstruct = tfm_ui.reconstruct
    first_image = None

    def instrument(source, request, **kwargs):
        if report['closing_test']:
            while True:
                kwargs['cancel_check']()
                time.sleep(.005)
        started = time.perf_counter()
        result = numerical_reconstruct(source, request, **kwargs)
        report['computations'].append({'seconds': time.perf_counter() - started, 'shape': result.image.shape, 'method': result.method})
        return result

    tfm_ui.reconstruct = instrument

    def guard(function):
        def run():
            try:
                assert 'oempa.api' not in sys.modules and 'oempa.driver' not in sys.modules
                assert app.backend.device is None
                function()
            except Exception:
                report['errors'].append(traceback.format_exc())
                app.on_close()
        return run

    def wait_then(callback):
        if app.controller.active:
            root.after(25, guard(lambda: wait_then(callback)))
        else:
            root.after(150, guard(callback))

    def capture(name):
        root.update()
        issues = []
        def walk(widget):
            for child in widget.winfo_children():
                if not child.winfo_ismapped():
                    continue
                # The settings content intentionally exceeds the scroll viewport.
                if widget is not view.settings_canvas and (child.winfo_x() + child.winfo_width() > widget.winfo_width() + 2 or child.winfo_y() + child.winfo_height() > widget.winfo_height() + 2):
                    issues.append(str(child))
                walk(child)
        walk(root)
        canvas = app.plots['TFM'][2].get_tk_widget()
        assert canvas.winfo_height() >= 150, 'TFM image must retain usable height'
        assert app.log_text.winfo_height() >= 90, 'Diagnostics must remain usable'
        assert str(app.acquire_button['state']) == 'disabled'
        geometry = {}
        if view.state.result is not None:
            figure, axes, drawing = app.plots['TFM']
            drawing.draw()
            renderer = drawing.get_renderer()
            image = axes.get_window_extent(renderer)
            bar = view.colorbar.ax.get_window_extent(renderer)
            width, height = figure.bbox.width, figure.bbox.height
            center_error = abs((image.x0 + bar.x1) / 2 - width / 2) / width
            assert center_error < .08, 'Image/colorbar must be centered, not shifted right'
            assert image.height > height * .55, 'Image must use available vertical space'
            assert bar.width < image.width * .08, 'Colorbar must remain narrow'
            assert 0 <= bar.x0 - image.x1 < image.width * .2, 'Colorbar must stay adjacent'
            result = view.state.result
            aspect = np.ptp(result.x_m) / np.ptp(result.z_m)
            assert np.isclose(image.width / image.height, aspect), 'Physical coordinates must not stretch'
            for text in (axes.xaxis.label, axes.yaxis.label, axes.title, view.colorbar.ax.yaxis.label):
                box = text.get_window_extent(renderer)
                assert box.x0 >= -2 and box.x1 <= width + 2 and box.y0 >= -2 and box.y1 <= height + 2, 'Plot text clipped'
            assert canvas.winfo_width() >= view.image_panel.winfo_width() - 2
            toolbar_height = canvas.master.winfo_height() - canvas.winfo_height()
            assert toolbar_height < 55, 'Toolbar must not reserve excess height'
            geometry = {'canvas_width': width, 'image_bounds': list(image.bounds), 'colorbar_bounds': list(bar.bounds),
                        'center_error_fraction': center_error, 'toolbar_height': toolbar_height}
        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / (name + '.png'))
        report['layouts'].append({'name': name, 'issues': issues, 'canvas_height': canvas.winfo_height(), **geometry})
        assert not issues, issues

    def current_source():
        capture('empty_1300')
        assert str(view.reconstruct_button['state']) == 'disabled'
        app.fmc_data = FMCData(raw, 16, 16, 3001, 1, True, 0, metadata=metadata)
        app.state.dataset_revision, app.state.dataset_mode, app.state.dataset_stale = 12, 'FMC', False
        view.use_current()
        assert view.variables['pitch'].get() == '0.6'
        assert view.variables['velocity'].get() == ''
        view.water_button.invoke()  # Explicit selection, never inferred material.
        view.start_reconstruction()
        wait_then(current_result)

    def current_result():
        nonlocal first_image
        result = view.state.result
        assert result is not None and not view.state.stale
        assert result.image.shape == (231, 201) and result.method == 'linear'
        iz, ix = np.unravel_index(np.argmax(np.abs(result.image)), result.image.shape)
        report['synthetic_maximum_mm'] = [result.x_m[ix] * 1e3, result.z_m[iz] * 1e3]
        assert abs(result.x_m[ix] - .001) <= .0001 and abs(result.z_m[iz] - .012) <= .0001
        first_image = result.image.copy()
        capture('current_normalized_1300')
        root.geometry('1100x700+20+20')
        view.toggle_settings(True)
        root.after(250, guard(minimum_settings))

    def minimum_settings():
        capture('current_settings_1100')
        view.settings_canvas.yview_moveto(.5)
        root.after(150, guard(minimum_scrolled))

    def minimum_scrolled():
        capture('current_settings_scrolled_1100')
        view.toggle_settings(False)
        view.variables['display'].set('db')
        root.after(150, guard(display_only))

    def display_only():
        capture('current_db_1100')
        assert len(report['computations']) == 1
        np.testing.assert_array_equal(view.state.result.image, first_image)
        for name in ('FMC', 'B-scan', 'TFM'):
            app.workspace.select(app.display_panels[name])
            app.change_display()
        assert len(report['computations']) == 1
        view.variables['velocity'].set('1490')
        assert view.state.stale
        capture('parameter_stale_1100')
        view.variables['velocity'].set('1480')
        replacement = replace(metadata, configuration_revision=13)
        app.fmc_data = FMCData(raw.copy(), 16, 16, 3001, 1, True, 0, metadata=replacement)
        view.refresh()
        assert view.state.stale and view.state.source_detached
        assert str(view.reconstruct_button['state']) == 'disabled'
        capture('new_fmc_stale_1100')
        view.load_source(source_path)
        wait_then(offline_loaded)

    def offline_loaded():
        assert view.variables['pitch'].get() == '0.6'
        assert view.state.source.metadata.configuration_revision == 12
        view.start_reconstruction()
        wait_then(offline_result)

    def offline_result():
        np.testing.assert_array_equal(view.state.result.image, first_image)
        assert not view.state.stale and len(report['computations']) == 2
        capture('offline_db_1100')
        with patch('ui.tfm_workspace.filedialog.asksaveasfilename', return_value=str(output / 'synthetic_tfm_result.npz')):
            view.save_result()
        wait_then(saved)

    def saved():
        with np.load(output / 'synthetic_tfm_result.npz', allow_pickle=False) as loaded:
            np.testing.assert_array_equal(loaded['image'], first_image)
        assert hashlib.sha256(raw.tobytes()).hexdigest() == before
        root.geometry('1300x820+20+20')
        view.toggle_settings(True)
        root.after(250, guard(close_during_reconstruct))

    def close_during_reconstruct():
        capture('offline_settings_1300')
        report['closing_test'] = True
        view.start_reconstruction()
        assert app.controller.active
        root.after(75, guard(app.on_close))

    def heartbeat():
        report['ticks'].append(time.monotonic())
        if not app._destroyed:
            root.after(20, heartbeat)

    root.after(20, heartbeat)
    root.after(400, guard(current_source))
    root.after(30000, guard(lambda: (report['errors'].append('Offline validation timed out'), app.on_close())))
    with patch('gui.messagebox.askyesno', return_value=True):
        root.mainloop()
    tfm_ui.reconstruct = numerical_reconstruct
    report['clean_close'] = app.state.shutdown_complete and not app.controller.active and app._destroyed
    report['sdk_loaded'] = 'oempa.api' in sys.modules or 'oempa.driver' in sys.modules
    report['raw_unchanged'] = hashlib.sha256(raw.tobytes()).hexdigest() == before
    report['maximum_tick_interval_s'] = max(np.diff(report.pop('ticks')), default=0)
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if not report['errors'] and report['clean_close'] and not report['sdk_loaded'] and report['raw_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
