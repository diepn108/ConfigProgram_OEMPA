"""Opt-in explicitly approved Stage 3D: one production GUI FMC start, no retry.

Requires separately authorized hardware acceptance. Applies only the approved
unchanged FMC file; enables once only after verified OFF preparation.
"""

import ctypes
import argparse
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
import numpy as np
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


from oempa.fmc_acceptance import require_records, require_first_frame


def main():
    from oempa import api

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-name", default="phase5_stage3d")
    options = parser.parse_args()
    name = options.artifact_name
    if name != "phase5_stage3d" and (not name.startswith("phase5_stage3d_retry_") or not all(char.isalnum() or char == "_" for char in name)):
        raise ValueError("Use a distinct phase5_stage3d_retry_ artifact name after separate hardware authorization.")
    output = PROJECT / "artifacts" / name
    output.mkdir(parents=True, exist_ok=True)
    if (output / "validation.json").exists():
        raise RuntimeError("Stage 3D already has a recorded attempt; refusing an automatic retry.")
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "endpoint": "192.168.1.11:5001", "api_calls": [], "errors": [], "observations": [], "screenshots": []}
    allowed = {"create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition", "get_cycle_count", "get_multichannel_state", "load_configuration", "get_cycle_snapshot", "get_extended_cycle_snapshot", "get_pa_delay_snapshot", "get_pa_receive_snapshot", "get_configuration_diagnostic", "get_pulser_power_snapshot", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers", "get_multiascan_count"}
    allowed.update({"enable_acquisition", "has_multiascan_cycle", "copy_multiascan", "get_multiascan_info", "get_callback_record_stats"})
    allowed.update({"begin_callback_order", "get_callback_order"})
    allowed.update({"begin_fmc_first_frame", "get_fmc_first_frame", "wait_fmc_first_frame"})
    main_thread = threading.get_ident()
    candidate = PROJECT / "configs/fmc16_full.txt"
    from oempa.verified_fmc import APPROVED_FMC_SHA256 as APPROVED_SHA256, inspect_approved_fmc
    report["requested"] = asdict(inspect_approved_fmc(candidate))
    report["source_sha256"] = APPROVED_SHA256
    load_count = 0
    enable_count = 0
    acquisition_on = False
    seen_metadata = set()

    def guarded(name, function):
        def call(*args, **kwargs):
            nonlocal load_count, enable_count, acquisition_on
            entry = {"name": name, "arguments": list(args[1:]) if name in {"set_multiascan_cycle_count", "prepare_ascan_callback_buffers"} else [], "worker_thread": threading.get_ident() != main_thread}
            report["api_calls"].append(entry)
            if name not in allowed:
                entry["blocked"] = True
                raise AssertionError(f"Stage 3 preflight forbids device API: {name}")
            if name in {"load_configuration", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers", "begin_callback_order", "begin_fmc_first_frame"}:
                assert not acquisition_on, "Configuration/storage mutation while acquisition active"
            if name == "enable_acquisition":
                enable_count += 1
                assert enable_count == 1 and phase == "acquiring" and report.get("buffer_prepared"), "Only one verified acquisition start is allowed"
                assert app.state.configuration_verified and app.state.operation.value == "acquiring"
                # Local diagnostics only, after production OFF/preallocation/readback.
                if not report.get("callback_order_armed"):
                    api.begin_callback_order(args[0], 256, 3001, 1, True, 0)
                report["callback_order_armed"] = True
                report["enable_requested_utc"] = datetime.now(timezone.utc).isoformat()
                acquisition_on = True
            if name == "connect":
                assert args[1:] == ("192.168.1.11", 5001), "Unexpected endpoint"
            if name == "load_configuration":
                assert Path(args[1]).resolve() == candidate.resolve()
                assert hashlib.sha256(candidate.read_bytes()).hexdigest() == APPROVED_SHA256
                load_count += 1
                assert load_count == 1, "Only one configuration write is authorized"
            try:
                if name == "destroy_handle" and report.get("callback_order_armed"):
                    # Preserve final local evidence after OFF/disconnect, before storage release.
                    try:
                        report["callback_order"] = api.get_callback_order(args[0])
                    except Exception as diagnostic_error:
                        report["errors"].append(f"Final order snapshot failed: {diagnostic_error}")
                value = function(*args, **kwargs)
                if name == "begin_callback_order":
                    report["callback_order_armed"] = True
                if name == "disable_acquisition":
                    acquisition_on = False
                    if enable_count:
                        report["last_off_utc"] = datetime.now(timezone.utc).isoformat()
                entry["success"] = True
                if name in {"get_cycle_count", "get_multichannel_state", "load_configuration", "get_cycle_snapshot", "get_extended_cycle_snapshot", "get_pa_delay_snapshot", "get_pa_receive_snapshot", "get_configuration_diagnostic", "get_pulser_power_snapshot", "set_multiascan_cycle_count", "register_ascan_callback", "clear_multiascan", "prepare_ascan_callback_buffers"}:
                    entry["value"] = value
                if name == "load_configuration":
                    report["load_diagnostic"] = api.get_configuration_diagnostic()
                if name == "get_multiascan_count" and acquisition_on:
                    stats = api.get_callback_record_stats(args[0], 256)
                    report["callback_stats"] = stats
                    report['first_frame'] = api.get_fmc_first_frame(args[0])
                    require_first_frame(report['first_frame'])
                    # Header reads are local bridge storage reads on the worker, not SDK calls.
                    for cycle, count in enumerate(stats["cycle_counts"]):
                        if count and cycle not in seen_metadata:
                            info = api.get_multiascan_info(args[0], cycle)
                            if info != {"point_count": 3001, "data_size": 1, "signed": True, "bit_size": 0}:
                                raise RuntimeError(f"Malformed callback cycle {cycle}: {info}")
                            seen_metadata.add(cycle)
                    report.setdefault("poll_progress", []).append({"received": value, "utc": datetime.now(timezone.utc).isoformat()})
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
    dataset_prefix = "fmc_stage3d_retry_acceptance_" if name.startswith("phase5_stage3d_retry_") else "fmc_stage3d_acceptance_"
    dataset_path = PROJECT / "data" / (dataset_prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".npy")
    assert not dataset_path.exists() and not Path(str(dataset_path) + ".json").exists()
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
    original_acquire = app.backend.acquire

    def acquire_and_observe(context, configuration, probe=None):
        acquisition = app.backend.acquisition
        original_read = acquisition.read_cycles
        def read_and_check(count):
            result = original_read(count)
            assert result.shape == (256, 3001) and result.scans.dtype == np.int8
            assert (result.point_count, result.data_size, result.signed, result.bit_size) == (3001, 1, True, 0)
            report["raw"] = {"shape": list(result.shape), "dtype": str(result.scans.dtype), "point_count": result.point_count, "data_size": result.data_size, "signed": result.signed, "bit_size": result.bit_size, "sha256": hashlib.sha256(result.scans.tobytes()).hexdigest()}
            return result
        acquisition.read_cycles = read_and_check
        try:
            result = original_acquire(context, configuration, probe)
            stats = api.get_callback_record_stats(app.backend.device.handle, 256)
            report["callback_stats"] = stats
            report['first_frame'] = api.get_fmc_first_frame(app.backend.device.handle)
            require_first_frame(report['first_frame'], complete=True)
            assert not acquisition._acquisition_enabled and not acquisition_on
            report["missing_cycles"] = []
            report["duplicate_cycles"] = [i for i, count in enumerate(stats['cycle_counts']) if count > 1]
            return result
        finally:
            acquisition.read_cycles = original_read
            report["callback_stats"] = api.get_callback_record_stats(app.backend.device.handle, 256)
            if report.get("callback_order_armed"):
                report["callback_order"] = api.get_callback_order(app.backend.device.handle)
                if report["callback_order"]["overflow"]:
                    report.setdefault('warnings', []).append('Post-frame chronology overflow; native first-frame proof and post-frame totals retained')

    app.backend.acquire = acquire_and_observe
    original_event = app._handle_controller_event
    def event_and_observe(event):
        if event.operation.value == "acquiring":
            report.setdefault("acquisition_events", []).append({"kind": event.kind, "payload": event.payload if event.kind == "progress" else str(event.payload) if event.kind == "error" else None})
        original_event(event)
    app._handle_controller_event = event_and_observe
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
        ready = label in {"applied_verified_fmc_ready_off", "acquired_complete_idle_off"}
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
                app.acquire_button.configure(command=lambda: fail("Acquire is guarded until repeated preflight passes"))
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
                assert app.state.acquisition_ready and app.state.configuration_label == "Verified (mixed sources)"
                phase = "acquiring"
                deadline = now + 120
                app.acquire_button.configure(command=app.acquire_fmc)
                print("Repeated Stage 3C passed; invoking exactly one production GUI Acquire FMC", flush=True)
                app.acquire_button.invoke()
                app.acquire_button.configure(command=lambda: fail("A second acquisition is forbidden"))
            elif phase == "acquiring":
                report.setdefault("acquisition_ui_ticks", []).append({"operation": app.state.operation.value, "progress": app.progress_text_var.get(), "interval_s": intervals[-1]})
                if app.controller.active:
                    assert app.state.operation.value == "acquiring"
                    assert str(app.stop_button["state"]) == "normal"
                else:
                    assert app.fmc_data is not None and not acquisition_on
                    require_first_frame(report['first_frame'], complete=True)
                    fmc = app.fmc_data
                    assert fmc.shape == (16, 16, 3001) and fmc.data.dtype == np.int8
                    assert hashlib.sha256(fmc.data.reshape(256, 3001).tobytes()).hexdigest() == report["raw"]["sha256"]
                    metadata = fmc.metadata
                    assert metadata.complete and metadata.configuration_revision == report["configuration_revision"]
                    assert metadata.timing.start_s == 0 and metadata.timing.range_s == 30e-6 and metadata.timing.sampling_hz == 100e6
                    assert not metadata.probe.mapping_verified
                    assert metadata.cycle_mapping == "cycle = tx * 16 + rx"
                    assert metadata.probe.physical_wiring_validation == 'Not independently tested'
                    assert metadata.hardware.applied_configuration.source_sha256 == APPROVED_SHA256
                    sources = [item for item in metadata.hardware.field_verification if item.source == "applied_configuration"]
                    assert len(sources) == 288 and all(item.actual is None for item in sources)
                    report["dataset_metadata"] = asdict(metadata)
                    assert app.progress_text_var.get() == "256 / 256"
                    observe("acquired_complete_idle_off")
                    app.workspace.select(1)
                    app.change_display()
                    report["selector_checks"] = []
                    for tx, rx in ((0, 0), (0, 15), (7, 8), (15, 0), (15, 15)):
                        app.tx_view_var.set(str(tx))
                        app.rx_view_var.set(str(rx))
                        app.update_data_view()
                        line = app.axes.lines[0]
                        assert np.array_equal(line.get_ydata(), fmc.data[tx, rx])
                        assert np.array_equal(line.get_xdata(), metadata.time_us)
                        report["selector_checks"].append([tx, rx])
                    assert "Applied configuration verified" in app.warning_var.get()
                    capture("acquired_fmc")
                    from oempa.dataset import load_dataset
                    with patch("gui.filedialog.asksaveasfilename", return_value=str(dataset_path)):
                        app.save_button.invoke()
                    assert dataset_path.exists() and Path(str(dataset_path) + ".json").exists()
                    reloaded = load_dataset(dataset_path)
                    assert np.array_equal(reloaded.data, fmc.data) and reloaded.metadata == metadata
                    report["saved_dataset"] = str(dataset_path.relative_to(PROJECT))
                    report["offline_reload_equal"] = True
                    report["array_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
                    phase = "finished_off"
            elif phase == "finished_off":
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
    after = checksums()
    report["protected_files_unchanged"] = all(after.get(path) == digest for path, digest in before.items())
    report["heartbeat_count"] = len(intervals)
    report["maximum_tick_interval_s"] = max(intervals, default=0)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report.setdefault("vendor_dialogs", [])
    report["enable_count"] = enable_count
    report["acquisition_off_at_close"] = not acquisition_on
    stats = report.get("callback_stats", {})
    report.setdefault("missing_cycles", [i for i, count in enumerate(stats.get("cycle_counts", ())) if count == 0])
    report.setdefault("duplicate_cycles", [i for i, count in enumerate(stats.get("cycle_counts", ())) if count > 1])
    report["passed"] = not report["errors"] and report["clean_close"] and report["protected_files_unchanged"] and len(report["observations"]) == 5 and load_count == enable_count == 1 and report.get("offline_reload_equal") and all(entry.get("worker_thread") and entry.get("success") for entry in report["api_calls"])
    (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"api_calls", "hardware_snapshot", "dataset_metadata", "field_verification", "configuration_provenance_fields", "remaining_unavailable_fields", "acquisition_ui_ticks", "callback_order"}}, indent=2), flush=True)
    print(f"API calls: {len(report['api_calls'])}; all results retained in validation.json", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
