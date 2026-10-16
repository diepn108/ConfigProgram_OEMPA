"""Opt-in real TFM window validation with an offline-only adapter and explicit inputs."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import tkinter as tk
import traceback
from types import ModuleType

from PIL import ImageGrab

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ui.controller import OperationResult


class OfflineBackend:
    def __init__(self, path):
        self.device = None
        self.acquisition = None

    def connect(self, *args):
        raise AssertionError("Device operations prohibited in offline validation.")

    apply = connect
    acquire = connect

    def close(self, context):
        return OperationResult(connected=False, status="Offline window cleanup completed")


# The production UI is used unmodified; no native bridge/device module is loaded.
stub = ModuleType("oempa.gui_backend")
stub.GUIBackend = OfflineBackend
sys.modules["oempa.gui_backend"] = stub

from gui import OEMPAGUI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pitch-mm", required=True)
    parser.add_argument("--velocity-m-s", required=True)
    parser.add_argument("--legacy-rate-mhz", required=True)
    parser.add_argument("--legacy-start-us", required=True)
    parser.add_argument("--output", type=Path, default=PROJECT / "artifacts" / "phase4_window")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"source": str(args.source), "example_assumptions": vars(args).copy(), "errors": [], "screenshots": [], "layouts": []}
    report["example_assumptions"] = {key: str(value) for key, value in report["example_assumptions"].items()}
    root = tk.Tk()
    app = OEMPAGUI(root)
    view = app.tfm_workspace
    root.geometry("1300x820+20+20")
    root.report_callback_exception = lambda kind, value, trace: report["errors"].append("".join(traceback.format_exception(kind, value, trace)))
    app.workspace.select(app.display_panels["TFM"])

    def guard(function):
        def run():
            try:
                assert "oempa.api" not in sys.modules and "oempa.driver" not in sys.modules
                assert app.backend.device is None
                assert not report["errors"], report["errors"]
                function()
            except Exception:
                report["errors"].append(traceback.format_exc())
                app.on_close()
        return run

    def wait_then(callback):
        if app.controller.active:
            root.after(25, guard(lambda: wait_then(callback)))
        else:
            callback()

    def capture(name):
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).save(args.output / f"{name}.png")
        report["screenshots"].append(f"{name}.png")
        issues = []
        def walk(widget):
            for child in widget.winfo_children():
                if not child.winfo_ismapped():
                    continue
                if child.winfo_x() + child.winfo_width() > widget.winfo_width() + 2 or child.winfo_y() + child.winfo_height() > widget.winfo_height() + 2:
                    issues.append(str(child))
                walk(child)
        walk(root)
        report["layouts"].append({"name": name, "canvas_height": app.plots["TFM"][2].get_tk_widget().winfo_height(), "issues": issues})

    def after_load():
        assert view.state.source is not None
        assert str(view.reconstruct_button["state"]) == "disabled"
        for name, value in (("pitch", args.pitch_mm), ("velocity", args.velocity_m_s), ("sampling", args.legacy_rate_mhz), ("start", args.legacy_start_us)):
            view.variables[name].set(value)
        assert str(view.reconstruct_button["state"]) == "normal"
        view.start_reconstruction()
        wait_then(after_reconstruct)

    def after_reconstruct():
        assert view.state.result is not None
        assert not view.state.result.mapping_verified
        assert str(app.acquire_button["state"]) == "disabled"
        capture("tfm_absolute")
        view.variables["display"].set("db")
        root.after(250, guard(after_display))

    def after_display():
        capture("tfm_db")
        root.geometry("1100x700+20+20")
        root.after(250, guard(after_resize))

    def after_resize():
        capture("tfm_minimum")
        view.variables["pitch"].set(str(float(args.pitch_mm) * 1.1))
        assert view.state.stale
        root.after(250, guard(after_edit))

    def after_edit():
        capture("tfm_stale")
        report["method"] = view.state.result.method
        report["shape"] = list(view.state.result.image.shape)
        report["metadata_complete"] = view.state.result.source_metadata.complete
        report["timing_origin"] = view.state.result.timing_origin
        app.on_close()

    def start():
        capture("tfm_empty")
        view.load_source(args.source)
        wait_then(after_load)

    root.after(500, guard(start))
    root.after(20000, root.quit)
    root.mainloop()
    report["clean_close"] = app._destroyed and app.state.shutdown_complete and not app.controller.active
    report["sdk_loaded"] = "oempa.api" in sys.modules or "oempa.driver" in sys.modules
    (args.output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["clean_close"] and not report["errors"] and not report["sdk_loaded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
