"""Opt-in real-device getter diagnostic: no config load, callbacks or acquisition."""

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
    allowed = {"create_handle", "destroy_handle", "connect", "disconnect", "disable_acquisition", "get_cycle_count", "get_multichannel_state", "get_emission_getter_diagnostic"}

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
        if device.cycle_count != 256 or report["multichannel"] != {"supported": True, "enabled": True}:
            raise RuntimeError("Existing hardware state is not the expected FMC state; no write attempted.")
        for cycle in (0, 16, 32, 240, 1, 17, 241):
            for getter, name in enumerate(("aperture", "width", "delay")):
                settings = ((16, 0, 0), (16, 0, 1)) if getter == 0 else ((16, 0, 0), (16, 1, 1), (16, 16, 0), (64, 0, 1))
                for capacity, count_seed, variant in settings:
                    result = api.get_emission_getter_diagnostic(device.handle, cycle, getter, capacity, count_seed, variant)
                    row = {"cycle": cycle, "config_expected_hw_acquisition": parser.getboolean(f"Cycle:{cycle}", "HWAcquisition"), "getter": name, **result}
                    report["rows"].append(row)
                    if not result["getter_success"] or not result["unlock_success"]:
                        raise RuntimeError(f"Cycle {cycle} {name}: getter/unlock failed; stopping.")
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
        output = PROJECT / "artifacts/phase5_fmc_emission_readback"
        output.mkdir(parents=True, exist_ok=True)
        (output / "diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key not in ("rows", "api_calls")}, indent=2))
        for row in report["rows"]:
            print(row["cycle"], row["getter"], "success", row["getter_success"], "capacity", row["capacity_before"], "count", (row["count_before"], row["count_after_call"], row["count_after_unlock"]), "unchanged", row["output_before"] == row["output_after_unlock"], "first outputs", row["output_after_unlock"][:4])
    return int("error" in report or "cleanup_error" in report)


if __name__ == "__main__":
    raise SystemExit(main())
