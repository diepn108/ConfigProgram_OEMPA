"""Opt-in desktop validation of the disconnected GUI; all device APIs blocked.

Run outside the restricted sandbox with the development Python. Screenshots
contain only this application window. No configuration or dataset is written.
"""

import ctypes
import inspect
import json
from pathlib import Path
import sys
import tkinter as tk
import traceback

from PIL import ImageGrab


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from oempa import api


api_calls = []


def block_device_api(*args, **kwargs):
    api_calls.append("blocked device API invocation")
    raise AssertionError("Hardware APIs are prohibited during window validation.")


# Import the real adapter/GUI, but make every Python device API fail closed.
for name, function in inspect.getmembers(api, inspect.isfunction):
    if function.__module__ == api.__name__:
        setattr(api, name, block_device_api)

from gui import OEMPAGUI


def main():
    output = PROJECT / "artifacts" / "phase3_window"
    output.mkdir(parents=True, exist_ok=True)
    report = {"python": sys.version, "executable": sys.executable, "screenshots": [], "layouts": [], "errors": []}
    root = tk.Tk()
    root.geometry("1300x820+20+20")

    def callback_error(kind, value, trace):
        report["errors"].append("".join(traceback.format_exception(kind, value, trace)))

    root.report_callback_exception = callback_error
    app = OEMPAGUI(root)
    report["tcl"] = root.tk.call("info", "patchlevel")
    report["tk"] = root.tk.call("package", "provide", "Tk")
    report["tcl_library"] = root.tk.call("info", "library")
    report["tk_library"] = str(root.tk.getvar("tk_library"))

    def settle():
        root.update_idletasks()
        root.update()
        assert not report["errors"], report["errors"]
        assert app.backend.device is None and app.backend.acquisition is None
        assert not api_calls, api_calls

    def capture(name):
        settle()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        path = output / f"{name}.png"
        ImageGrab.grab(window=hwnd).save(path)
        report["screenshots"].append(str(path.relative_to(PROJECT)))

    def geometry_issues():
        issues = []

        def walk(widget):
            if not widget.winfo_ismapped():
                return
            for child in widget.winfo_children():
                if not child.winfo_ismapped():
                    continue
                x, y = child.winfo_x(), child.winfo_y()
                width, height = child.winfo_width(), child.winfo_height()
                if x < -2 or y < -2 or x + width > widget.winfo_width() + 2 or y + height > widget.winfo_height() + 2:
                    issues.append({"widget": str(child), "class": child.winfo_class(), "bounds": [x, y, width, height], "parent": [widget.winfo_width(), widget.winfo_height()]})
                walk(child)

        walk(root)
        return issues

    def validate():
        try:
            settle()
            assert str(app.acquire_button["state"]) == "disabled"
            assert str(app.apply_button["state"]) == "disabled"
            assert str(app.stop_button["state"]) == "disabled"
            assert "disconnected" in app.header_var.get().lower()
            assert "Data: None" in app.header_var.get()
            assert str(app.ip_entry["state"]) == "readonly"
            for size in ("1300x820", "1100x700", "1600x1000"):
                root.geometry(size + "+20+20")
                for tab in app.setup_notebook.tabs():
                    app.setup_notebook.select(tab)
                    settle()
                    report["layouts"].append({"size": size, "setup": app.setup_notebook.tab(tab, "text"), "issues": geometry_issues()})
                for name, panel in app.display_panels.items():
                    app.workspace.select(panel)
                    settle()
                    report["layouts"].append({"size": size, "display": name, "issues": geometry_issues()})
            root.geometry("1300x820+20+20")
            app.setup_notebook.select(app.setup_notebook.tabs()[0])
            app.workspace.select(app.display_panels["A-scan"])
            capture("device_ascan")
            app.setup_notebook.select(app.setup_notebook.tabs()[1])
            app.workspace.select(app.display_panels["FMC"])
            capture("probe_fmc")
            app.setup_notebook.select(app.setup_notebook.tabs()[2])
            app.workspace.select(app.display_panels["B-scan"])
            capture("acquisition_bscan")
            app.setup_notebook.select(app.setup_notebook.tabs()[3])
            app.mode_selector.set("Phased Array")
            app.mode_selector.event_generate("<<ComboboxSelected>>")
            app.workspace.select(app.display_panels["Phased Array"])
            app.pa_vars["pitch"].set("0.6")
            app.pa_vars["velocity"].set("5900")
            app.pa_vars["angle"].set("30")
            app.preview_button.invoke()
            settle()
            assert app.pa_law is not None
            assert len(app.pa_law.tx_delays_us) == 16
            assert len(app.plots["Phased Array"][1].lines) == 2
            assert str(app.acquire_button["state"]) == "disabled"
            capture("pa_preview")
            root.geometry("1100x700+20+20")
            capture("pa_preview_minimum")
            report["layouts"].append({"size": "1100x700", "display": "PA calculated", "issues": geometry_issues()})
            app.workspace.select(app.display_panels["TFM"])
            settle()
            assert any("Offline TFM" in str(child.cget("text")) for child in app.display_panels["TFM"].winfo_children() if hasattr(child, "cget"))
            capture("tfm_minimum")
            report["offline_preview"] = "16 logical elements, assumed 0.6 mm / 5900 m/s, 30 degrees; physical mapping/steering unverified"
            report["hardware_api_calls"] = api_calls
            app.on_close()
        except Exception:
            report["errors"].append(traceback.format_exc())
            app.on_close()

    root.after(750, validate)
    root.after(20000, root.quit)
    root.mainloop()
    report["clean_close"] = app._destroyed and app.state.shutdown_complete and not app.controller.active
    report["hardware_api_calls"] = api_calls
    report_path = output / "validation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "clean_close": report["clean_close"], "errors": report["errors"], "layout_issues": sum(len(item["issues"]) for item in report["layouts"]), "hardware_api_calls": api_calls}, indent=2))
    return 0 if report["clean_close"] and not report["errors"] and not api_calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
