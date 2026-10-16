"""Opt-in real-device Stage 1: production GUI connect/readback/disconnect only.

Requires separately authorized hardware acceptance. Never applies configuration
or enables acquisition. The existing acquisition-OFF safety path is preserved.
"""

import ctypes
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
import traceback

from PIL import ImageGrab


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    from oempa import api

    output = PROJECT / "artifacts" / "phase5_stage1"
    output.mkdir(parents=True, exist_ok=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "endpoint": "192.168.1.11:5001", "api_calls": [], "errors": [], "observations": [], "screenshots": []}
    allowed = {"create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition", "get_cycle_count", "get_multichannel_state"}
    main_thread = threading.get_ident()

    def guarded(name, function):
        def call(*args, **kwargs):
            entry = {"name": name, "worker_thread": threading.get_ident() != main_thread}
            report["api_calls"].append(entry)
            if name not in allowed:
                entry["blocked"] = True
                raise AssertionError(f"Stage 1 forbids device API: {name}")
            if name == "connect":
                assert args[1:] == ("192.168.1.11", 5001), "Unexpected endpoint"
            try:
                value = function(*args, **kwargs)
                entry["success"] = True
                if name in {"get_cycle_count", "get_multichannel_state"}:
                    entry["value"] = value
                return value
            except Exception as exc:
                entry["error"] = str(exc)
                raise
        return call

    for name, function in inspect.getmembers(api, inspect.isfunction):
        if function.__module__ == api.__name__:
            setattr(api, name, guarded(name, function))

    from gui import OEMPAGUI
    from ui.state import ConnectionState

    def checksums():
        return {str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest() for folder in ("configs", "data") for path in (PROJECT / folder).rglob("*") if path.is_file()}

    before = checksums()
    root = tk.Tk()
    root.geometry("1300x820+20+20")
    app = OEMPAGUI(root)
    phase = "initial"
    deadline = time.monotonic() + 30
    last_tick = time.monotonic()
    intervals = []
    hold_until = 0

    def capture(name):
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        path = output / f"{name}.png"
        ImageGrab.grab(window=hwnd).save(path)
        report["screenshots"].append(str(path.relative_to(PROJECT)))

    def observe(label):
        assert not app.state.acquisition_ready
        assert str(app.acquire_button["state"]) == "disabled"
        assert str(app.stop_button["state"]) == "disabled"
        report["observations"].append({"stage": label, "connection": app.state.connection.value, "operation": app.state.operation.value, "header": app.header_var.get(), "connection_label": app.connection_status_var.get(), "cycles_label": app.cycle_status_var.get(), "multichannel_label": app.multichannel_status_var.get(), "acquire": str(app.acquire_button["state"]), "applied_snapshot": app.backend.applied_snapshot is not None})

    def fail(message):
        nonlocal phase
        report["errors"].append(message)
        print(message, flush=True)
        phase = "closing"
        # Avoid the busy-close dialog; retain the real serialized cleanup/pump.
        app.controller.request_shutdown(app.backend.close)

    def callback_error(kind, value, trace):
        fail("".join(traceback.format_exception(kind, value, trace)))

    root.report_callback_exception = callback_error

    def tick():
        nonlocal phase, deadline, last_tick, hold_until
        now = time.monotonic()
        intervals.append(now - last_tick)
        last_tick = now
        try:
            if phase != "closing" and now > deadline:
                raise TimeoutError(f"Stage 1 timed out during {phase}; cancelling and waiting for cleanup")
            if phase not in {"initial", "closing"} and app.state.error:
                raise RuntimeError(app.state.error)
            if phase == "initial":
                assert app.state.connection == ConnectionState.DISCONNECTED
                assert app.backend.device is None
                observe("initial_disconnected")
                capture("disconnected")
                # Prevent accidental configuration/acquisition actions in this run.
                app.apply_button.configure(command=lambda: fail("Stage 1 forbids Apply"))
                app.acquire_button.configure(command=lambda: fail("Stage 1 forbids Acquire"))
                phase = "connecting"
                print("Invoking production GUI Connect", flush=True)
                app.connect_button.invoke()
            elif phase == "connecting" and not app.controller.active:
                assert app.state.connection == ConnectionState.CONNECTED
                report["device_status"] = app.backend.device.get_status()
                assert app.cycle_status_var.get() == str(report["device_status"]["cycle_count"])
                assert not app.backend.acquisition._callback_registered
                observe("connected")
                capture("connected")
                print(json.dumps(report["device_status"]), flush=True)
                phase = "connected_hold"
                hold_until = now + 2
            elif phase == "connected_hold" and now >= hold_until:
                phase = "disconnecting"
                deadline = now + 30
                print("Invoking production GUI Disconnect", flush=True)
                app.disconnect_button.invoke()
            elif phase == "disconnecting" and not app.controller.active:
                assert app.state.connection == ConnectionState.DISCONNECTED
                assert app.backend.device is None and app.backend.acquisition is None
                observe("disconnected_after_connect")
                capture("disconnected_after")
                phase = "closing"
                app.on_close()
        except Exception:
            fail(traceback.format_exc())
        if root.winfo_exists():
            root.after(50, tick)

    root.after(500, tick)
    root.mainloop()
    report["clean_close"] = app.state.shutdown_complete and not app.controller.active and app.backend.device is None
    report["protected_files_unchanged"] = before == checksums()
    report["heartbeat_count"] = len(intervals)
    report["maximum_tick_interval_s"] = max(intervals, default=0)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = not report["errors"] and report["clean_close"] and report["protected_files_unchanged"] and len(report["observations"]) == 3 and all(entry.get("worker_thread") and entry.get("success") for entry in report["api_calls"])
    (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
