"""Opt-in read-only real-device diagnostic; no load, callback preparation or acquisition."""

import configparser
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    from oempa import api
    from oempa.driver import OEMPADevice
    from oempa.verified_fmc import inspect_approved_fmc

    candidate = PROJECT / "configs/fmc16_full.txt"
    inspect_approved_fmc(candidate)
    parser = configparser.ConfigParser()
    parser.read(candidate)
    protected = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for folder in ("configs", "data") for path in (PROJECT / folder).rglob("*") if path.is_file()}
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "rows": [], "api_calls": []}
    allowed = {"create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition", "get_cycle_count", "get_multichannel_state", "get_multihw_cycle_diagnostic"}

    def guard(name, function):
        def call(*args, **kwargs):
            if name not in allowed:
                raise AssertionError(f"Read-only diagnostic forbids {name}")
            report["api_calls"].append(name)
            return function(*args, **kwargs)
        return call

    for name, function in inspect.getmembers(api, inspect.isfunction):
        if function.__module__ == api.__name__:
            setattr(api, name, guard(name, function))
    device = OEMPADevice()
    try:
        device.connect()
        report["cycle_count"] = device.cycle_count
        report["multichannel"] = api.get_multichannel_state(device.handle)
        for cycle in (0, 1, 15, 16, 17, 31, 32, 240, 241, 255):
            row = {"cycle": cycle, "config_expected": parser.getboolean(f"Cycle:{cycle}", "HWAcquisition"), "reads": []}
            report["rows"].append(row)
            for seed in (False, True):
                result = api.get_multihw_cycle_diagnostic(device.handle, cycle, seed)
                row["reads"].append({"initial_state": seed, **result})
                if not result["getter_success"] or not result["unlock_success"]:
                    raise RuntimeError(f"Cycle {cycle}: SDK getter/unlock failure: {result}")
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        try:
            device.close()
            report["clean_close"] = device._handle is None and not device.is_connected
        except Exception as exc:
            report["cleanup_error"] = str(exc)
        report["protected_files_unchanged"] = all(Path(path).exists() and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in protected.items())
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        output = PROJECT / "artifacts/phase5_multihw_readback"
        output.mkdir(parents=True, exist_ok=True)
        (output / "diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return int("error" in report or "cleanup_error" in report)


if __name__ == "__main__":
    raise SystemExit(main())
