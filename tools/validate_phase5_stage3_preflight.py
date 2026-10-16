"""Opt-in real-device Stage 3 preflight: production GUI verified FMC file apply/readback/disconnect only.

Requires separately authorized hardware acceptance. Applies only the approved
unchanged FMC file; never enables acquisition. Existing OFF cleanup is preserved.
"""

import ctypes
from dataclasses import asdict
import os
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

    output = PROJECT / "artifacts" / "phase5_stage3c_final"
    output.mkdir(parents=True, exist_ok=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "endpoint": "192.168.1.11:5001", "api_calls": [], "errors": [], "observations": [], "screenshots": []}
    allowed = {"create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition", "get_cycle_count", "get_multichannel_state", "load_configuration", "get_cycle_snapshot", "get_extended_cycle_snapshot", "get_pa_delay_snapshot", "get_pa_receive_snapshot", "get_configuration_diagnostic", "get_pulser_power_snapshot", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers", "get_multiascan_count"}
    main_thread = threading.get_ident()
    candidate = PROJECT / "configs/fmc16_full.txt"
    from oempa.verified_fmc import APPROVED_FMC_SHA256 as APPROVED_SHA256, inspect_approved_fmc
    report["requested"] = asdict(inspect_approved_fmc(candidate))
    report["source_sha256"] = APPROVED_SHA256
    load_count = 0

    def guarded(name, function):
        def call(*args, **kwargs):
            nonlocal load_count
            entry = {"name": name, "arguments": list(args[1:]) if name in {"set_multiascan_cycle_count", "prepare_ascan_callback_buffers"} else [], "worker_thread": threading.get_ident() != main_thread}
            report["api_calls"].append(entry)
            if name not in allowed:
                entry["blocked"] = True
                raise AssertionError(f"Stage 3 preflight forbids device API: {name}")
            if name == "connect":
                assert args[1:] == ("192.168.1.11", 5001), "Unexpected endpoint"
            if name == "load_configuration":
                assert Path(args[1]).resolve() == candidate.resolve()
                assert hashlib.sha256(candidate.read_bytes()).hexdigest() == APPROVED_SHA256
                load_count += 1
                assert load_count == 1, "Only one configuration write is authorized"
            try:
                value = function(*args, **kwargs)
                entry["success"] = True
                if name in {"get_cycle_count", "get_multichannel_state", "load_configuration", "get_cycle_snapshot", "get_extended_cycle_snapshot", "get_pa_delay_snapshot", "get_pa_receive_snapshot", "get_configuration_diagnostic", "get_pulser_power_snapshot", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers"}:
                    entry["value"] = value
                if name == "load_configuration":
                    report["load_diagnostic"] = api.get_configuration_diagnostic()
                return value
            except Exception as exc:
                entry["error"] = str(exc)
                if name == "load_configuration":
                    report["load_diagnostic"] = api.get_configuration_diagnostic()
                raise
        return call

    for name, function in inspect.getmembers(api, inspect.isfunction):
        if function.__module__ == api.__name__:
            setattr(api, name, guarded(name, function))

    from gui import OEMPAGUI
    from ui.state import ConnectionState, ConfigurationState

    def checksums():
        return {str(path.relative_to(PROJECT)): hashlib.sha256(path.read_bytes()).hexdigest() for folder in ("configs", "data") for path in (PROJECT / folder).rglob("*") if path.is_file()}

    before = checksums()
    root = tk.Tk()
    root.geometry("1300x820+20+20")
    app = OEMPAGUI(root)
    original_apply = app.backend.apply_approved_fmc_file

    def apply_and_observe(context, path):
        result = original_apply(context, path)
        report["pulser_power"] = api.get_pulser_power_snapshot(app.backend.device.handle)
        report["received_records_while_off"] = api.get_multiascan_count(app.backend.device.handle)
        assert report["received_records_while_off"] == 0
        return result

    app.backend.apply_approved_fmc_file = apply_and_observe
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
        ready = label == "applied_verified_fmc_ready_off"
        assert app.state.acquisition_ready == ready
        assert str(app.acquire_button["state"]) == ("normal" if ready else "disabled")
        assert str(app.stop_button["state"]) == "disabled"
        report["observations"].append({"stage": label, "connection": app.state.connection.value, "operation": app.state.operation.value, "header": app.header_var.get(), "connection_label": app.connection_status_var.get(), "cycles_label": app.cycle_status_var.get(), "multichannel_label": app.multichannel_status_var.get(), "acquire": str(app.acquire_button["state"]), "applied_snapshot": app.backend.applied_snapshot is not None, "configuration_label": app.state.configuration_label, "readback_verified": app.state.readback_verified})

    def fail(message):
        nonlocal phase
        report["errors"].append(message)
        if app.state.actual_snapshot is not None:
            report["hardware_snapshot"] = asdict(app.state.actual_snapshot)
        report["verification_mismatches"] = list(app.state.verification_mismatches)
        report["field_verification"] = [asdict(item) for item in app.state.field_verification]
        report["failure_requested_state"] = app.state.requested_configuration
        print(message, flush=True)
        phase = "closing"
        # Avoid the busy-close dialog; retain the real serialized cleanup/pump.
        app.controller.request_shutdown(app.backend.close)

    def callback_error(kind, value, trace):
        fail("".join(traceback.format_exception(kind, value, trace)))

    root.report_callback_exception = callback_error

    def vendor_dialogs():
        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.EnumWindows.argtypes = [callback_type, ctypes.c_void_p]
        user32.EnumChildWindows.argtypes = [ctypes.c_void_p, callback_type, ctypes.c_void_p]
        dialogs = []

        def visit(hwnd, parameter):
            process = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process))
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, len(name))
            if process.value == os.getpid() and name.value == "#32770":
                text = []

                def read_text(child, ignored):
                    buffer = ctypes.create_unicode_buffer(8192)
                    user32.GetWindowTextW(child, buffer, len(buffer))
                    if buffer.value:
                        text.append(buffer.value)
                    return True

                read_text(hwnd, None)
                user32.EnumChildWindows(hwnd, callback_type(read_text), None)
                dialogs.append(text)
            return True

        user32.EnumWindows(callback_type(visit), None)
        return dialogs

    def tick():
        nonlocal phase, deadline, last_tick, hold_until
        now = time.monotonic()
        intervals.append(now - last_tick)
        last_tick = now
        try:
            if phase != "closing":
                dialogs = vendor_dialogs()
                if dialogs:
                    report["vendor_dialogs"] = dialogs
                    raise RuntimeError("AOS/SDK dialog observed: " + repr(dialogs))
            if phase != "closing" and now > deadline:
                raise TimeoutError(f"Stage 3 preflight timed out during {phase}; cancelling and waiting for cleanup")
            if phase not in {"initial", "closing"} and app.state.error:
                raise RuntimeError(app.state.error)
            if phase == "initial":
                assert app.state.connection == ConnectionState.DISCONNECTED
                assert app.backend.device is None
                observe("initial_disconnected")
                capture("disconnected")
                # Prevent accidental configuration/acquisition actions in this run.
                app.apply_button.configure(command=lambda: fail("Stage 3 preflight forbids Apply"))
                app.acquire_button.configure(command=lambda: fail("Stage 3 preflight forbids Acquire"))
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
                phase = "applying"
                deadline = now + 120
                print("Applying unchanged verified FMC file through production adapter", flush=True)
                app.apply_approved_fmc_file(candidate)
            elif phase == "applying" and not app.controller.active:
                assert app.state.configuration == ConfigurationState.APPLIED
                assert app.state.configuration_verified and not app.state.verification_mismatches
                assert not app.state.readback_verified
                assert "classification" in app.state.verification_scope
                assert app.state.applied_mode == app.state.mode == "FMC"
                assert app.state.applied_revision == app.state.draft_revision
                assert app.state.actual_snapshot is app.backend.applied_snapshot
                assert app.state.actual_snapshot.mode == "FMC"
                report["hardware_snapshot"] = asdict(app.state.actual_snapshot)
                report["requested_state"] = dict(app.state.requested_configuration)
                report["configuration_revision"] = app.state.applied_revision
                report["readback_text"] = app.readback_var.get()
                report["field_verification"] = [asdict(item) for item in app.state.field_verification]
                report["verification_scope"] = app.state.verification_scope
                assert "100 MHz" in report["readback_text"]
                assert "3001" in report["readback_text"] and "2000" in report["readback_text"]
                observe("applied_verified_fmc_ready_off")
                report["buffer_prepared"] = any(entry["name"] == "prepare_ascan_callback_buffers" and entry.get("success") for entry in report["api_calls"])
                assert report["buffer_prepared"]
                assert app.backend.acquisition._callback_registered
                assert not app.backend.acquisition._acquisition_enabled
                first = app.state.actual_snapshot.cycles[0]
                report["checkpoint"] = {
                    "acquisition_off": True, "cycle_count": 256,
                    "classification_source": "applied_configuration", "classification_hardware_readback": "unavailable",
                    "source_sha256": app.state.actual_snapshot.applied_configuration.source_sha256,
                    "gain_analog_db": first.gain_analog_db, "gain_digital_db": first.gain_digital_db,
                    "start_s": first.start_s, "range_s": first.range_s, "time_slot_s": first.time_slot_s,
                    "point_count": first.point_count, "sampling_hz": first.sampling_hz, "point_factor": first.point_factor,
                    "compression_type": first.compression_type, "signed": first.signed, "bit_size": first.bit_size,
                    "filter_index": first.filter_index, "widths_s": first.widths_s, "tx_delays_s": first.tx_delays_s,
                    "tx_width_source": "applied_configuration", "tx_width_s": [0.5e-6],
                    "tx_delay_source": "applied_configuration", "tx_delay_s": [0.0],
                    "expected_raw_shape": [256, first.point_count], "expected_fmc_shape": [16, 16, first.point_count],
                    "callback_record_count": 256, "callback_bytes_per_record": first.point_count,
                    "callback_cycle_buffer_bytes": 256 * first.point_count, "callback_single_buffer_bytes": first.point_count,
                    "cycle_mapping": "cycle = tx * 16 + rx; tx = cycle // 16; rx = cycle % 16",
                    "unavailable_hardware_fields": "HWAcq/replay classification on all cycles; TX width/delay on all sixteen base cycles (applied configuration source only)",
                    "not_applicable": "PA receive focusing, DDF, receive delays/gains/focal TOF/wedge fields; replay emission fields",
                    "other_unverified": "hardware identity/firmware not newly read; physical probe/channel mapping, physical geometry and required pulser power",
                    "readable_mismatches": list(app.state.verification_mismatches),
                    "enable_fmc_used": False, "unlock_enable_shot_used": False,
                    "callback_device_access": False, "storage_preallocated_off": report["buffer_prepared"],
                }
                snapshot = app.state.actual_snapshot
                assert all(cycle.hw_acquisition is None for cycle in snapshot.cycles)
                assert all(cycle.widths_s is None and cycle.tx_delays_s is None for cycle in snapshot.cycles[::16])
                applied = [item for item in app.state.field_verification if item.source == "applied_configuration"]
                assert len(applied) == 256 + 16 * 2
                report["configuration_provenance_fields"] = [asdict(item) for item in applied]
                report["remaining_unavailable_fields"] = [item.field for item in app.state.field_verification if item.source == "unavailable"]
                app.setup_notebook.select(2)
                capture("verified_readback")
                app.setup_notebook.select(0)
                capture("verified_device")
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
    report.setdefault("vendor_dialogs", [])
    report["passed"] = not report["errors"] and report["clean_close"] and report["protected_files_unchanged"] and len(report["observations"]) == 4 and load_count == 1 and all(entry.get("worker_thread") and entry.get("success") for entry in report["api_calls"])
    (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"api_calls", "hardware_snapshot", "field_verification", "configuration_provenance_fields", "remaining_unavailable_fields"}}, indent=2), flush=True)
    print(f"API calls: {len(report['api_calls'])}; all results retained in validation.json", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
