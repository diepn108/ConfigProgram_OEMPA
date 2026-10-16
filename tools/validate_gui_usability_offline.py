"""Real-window smoke test: offline adapter installed before GUI import; no SDK."""

import ctypes
import json
from pathlib import Path
import sys
import tkinter as tk
from types import ModuleType
import traceback
from PIL import ImageGrab
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.controller import OperationResult


class OfflineBackend:
    def __init__(self, path):
        self.device = None

    def connect(self, *args):
        raise AssertionError("Hardware operations forbidden in this offline smoke test")

    apply = connect
    acquire = connect

    def close(self, context):
        return OperationResult(connected=False)


stub = ModuleType("oempa.gui_backend")
stub.GUIBackend = OfflineBackend
sys.modules["oempa.gui_backend"] = stub
from gui import OEMPAGUI


def main():
    output = ROOT / "artifacts/fmc_inspection_offline"
    output.mkdir(parents=True, exist_ok=True)
    report = {"errors": [], "layouts": [], "hardware_imported": False}
    root = tk.Tk()
    root.attributes('-topmost', True)
    app = OEMPAGUI(root)
    root.report_callback_exception = lambda kind, value, trace: report['errors'].append(''.join(traceback.format_exception(kind, value, trace)))
    steps = [(size, tab, 'A-scan') for size in ("1300x820", "1100x700") for tab in ("Device", "Probe", "Acquisition", "Mode Settings")]
    steps.extend(('1100x700', 'Mode Settings', mode) for mode in ('FMC', 'Phased Array'))
    steps.extend((size, 'Mode Settings', 'FMC') for size in ('1300x820', '1100x700') for _ in range(2))
    steps.extend((size, 'Mode Settings', 'FMC') for size in ('1300x820', '1100x700') for _ in range(2))
    def inspect_step(index):
        try:
            assert 'oempa.api' not in sys.modules and 'oempa.driver' not in sys.modules
            assert app.backend.device is None
            if index == len(steps):
                app.on_close()
                return
            size, tab, mode = steps[index]
            root.geometry(size + '+20+20')
            root.lift()
            app.mode_var.set(mode)
            app.setup_notebook.select(app.setup_notebook.tabs()[('Device','Probe','Acquisition','Mode Settings').index(tab)])
            if index >= 10:
                if index == 10:
                    from oempa.hardware_state import HardwareSnapshot, CycleSnapshot
                    from oempa.dataset import AcquisitionMetadata
                    from oempa.fmc import FMCData
                    cycles = tuple(CycleSnapshot(i, start_s=2e-6, range_s=30e-6, point_count=751, sampling_hz=25e6) for i in range(256))
                    snapshot = HardwareSnapshot('FMC', 256, True, True, cycles)
                    raw = np.zeros((16, 16, 751), dtype=np.int8)
                    raw[4, 7, 30] = 42
                    for element in range(16):
                        raw[element, element, 40:44] = (element + 1, -(element + 1), 1, -1)
                        raw[element, element, 90] = 1
                    metadata = AcquisitionMetadata('FMC', raw.shape, raw.dtype.str, hardware=snapshot, probe=app.probe_metadata,
                                                   acquisition_acceptance='Synthetic offline viewer fixture')
                    app._loaded_fmc_view(FMCData(raw, 16, 16, 751, 1, True, 0, metadata=metadata))
                    app.tx_view_var.set(4)
                    app.rx_view_var.set(7)
                    app.bscan_gate_start_var.set('2')
                    app.bscan_gate_end_var.set('32')
                display = 'FMC' if index % 2 == 0 else 'B-scan'
                if index >= 14:
                    app.fmc_trace_view_var.set('All diagonal traces')
                    app.bscan_normalization_var.set('Per trace')
                    app.bscan_contrast_var.set('Boost weak (sqrt)')
                    app.bscan_gate_start_var.set('3')
                    app.bscan_gate_end_var.set('6')
                app.workspace.select(app.display_panels[display])
                app.change_display()
                if index >= 14 and display == 'FMC':
                    assert len(app.axes.lines) == 16
                if index >= 14:
                    assert 'display processing only' in app.inspection_status_var.get()
            root.after(200, lambda: capture(index, size, tab))
        except Exception:
            report['errors'].append(traceback.format_exc())
            app.on_close()
    def capture(index, size, tab):
        try:
            root.update_idletasks()
            assert str(app.acquire_button['state']) == 'disabled'
            assert app.setup_notebook.winfo_ismapped(), 'Workspace must remain visible'
            assert app.log_text.master.winfo_height() < root.winfo_height() * .4, 'Diagnostics must not collapse the workspace'
            assert str(app.mode_selector['values'])
            issues = []
            def walk(widget):
                for child in widget.winfo_children():
                    if not child.winfo_ismapped():
                        continue
                    if child is not app.acquisition_form and (child.winfo_x() + child.winfo_width() > widget.winfo_width() + 2 or child.winfo_y() + child.winfo_height() > widget.winfo_height() + 2):
                        issues.append(str(child))
                    walk(child)
            walk(root)
            mode = steps[index][2]
            report['layouts'].append({"size":size, "tab":tab, "mode":mode, "issues":issues,
                                      "diagnostics_height": app.log_text.winfo_height(), "diagnostics_panel_height": app.log_text.master.winfo_height(), "window_height":root.winfo_height()})
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            suffix = '' if mode == 'A-scan' else '_' + mode.replace(' ', '_')
            if index >= 10:
                suffix += '_synthetic_' + ('FMC' if index % 2 == 0 else 'Bscan')
            if index >= 14:
                suffix += '_diagonal' if index % 2 == 0 else '_contrast'
            name = f'{size}_{tab.replace(" ", "_")}{suffix}.png'
            # Screen capture avoids PrintWindow artifacts in embedded TkAgg plots.
            root.update()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / name)
            root.after(25, lambda: inspect_step(index + 1))
        except Exception:
            report['errors'].append(traceback.format_exc())
            app.on_close()
    root.after(300, lambda: inspect_step(0))
    root.mainloop()
    report['clean_close'] = app.state.shutdown_complete and not app.controller.active
    report['hardware_imported'] = 'oempa.api' in sys.modules or 'oempa.driver' in sys.modules
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 1 if report['errors'] or any(item['issues'] for item in report['layouts']) or not report['clean_close'] or report['hardware_imported'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
