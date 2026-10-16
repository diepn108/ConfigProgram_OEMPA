from pathlib import Path

from oempa.api import (
    create_handle,
    destroy_handle,
    connect,
    disconnect,
    disable_acquisition,
    load_configuration,
    get_cycle_snapshot,
    get_ascan_config_snapshot,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
PA_CONFIG = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
FMC_CONFIG = PROJECT_DIR / "configs" / "fmc16_full.txt"

IP_ADDRESS = "192.168.1.11"
PORT = 5001

def read_one(handle, path, label):
    if not path.exists():
        raise FileNotFoundError(path)

    disable_acquisition(handle)
    load_configuration(handle, path)
    disable_acquisition(handle)

    cycle = get_cycle_snapshot(handle, 0)
    acq = get_ascan_config_snapshot(handle, 0)

    print()
    print(label)
    print("-" * len(label))
    print(f"Configuration: {path.name}")
    print(f"A-scan enabled: {acq['ascan_enabled']}")
    print(
        f"A-scan request: {acq['ascan_request_name']} "
        f"(enum {acq['ascan_request']})"
    )
    print(
        "A-scan request frequency: "
        f"{acq['ascan_request_frequency_hz']:.6f} Hz"
    )
    print(f"Maximum buffer: {acq['maximum_enabled']}")
    print(f"Minimum buffer: {acq['minimum_enabled']}")
    print(f"Saturation buffer: {acq['saturation_enabled']}")
    print(f"Trigger mode enum: {acq['trigger_mode']}")
    print(f"Start: {cycle['start_s'] * 1e6:.3f} us")
    print(f"Range: {cycle['range_s'] * 1e6:.3f} us")
    print(f"Point count: {cycle['point_count']}")
    print(f"Point factor: {cycle['point_factor']}")
    print(f"Sampling rate: {cycle['sampling_hz'] / 1e6:.3f} MHz")
    print(f"Compression enum: {cycle['compression_type']}")
    print(f"Rectification enum: {cycle['rectification']}")
    print(f"Bit size enum: {cycle['bit_size']}")
    print(f"Filter index: {cycle['filter_index']}")

    return {**cycle, **acq}

def main():
    print("OEM-PA A-scan Configuration Diagnostic")
    print("---------------------------------------")
    print("[SAFE] Acquisition remains OFF.")
    print("[SAFE] No A-scan callback is started.")
    print("[SAFE] No ultrasound acquisition is enabled.")

    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        pa = read_one(
            handle,
            PA_CONFIG,
            "0-degree PA configuration",
        )

        fmc = read_one(
            handle,
            FMC_CONFIG,
            "Known-good FMC configuration",
        )

        print()
        print("Comparison")
        print("----------")

        fields = [
            ("ascan_enabled", "A-scan enabled"),
            ("ascan_request", "A-scan request"),
            ("ascan_request_frequency_hz", "Request frequency"),
            ("maximum_enabled", "Maximum buffer"),
            ("minimum_enabled", "Minimum buffer"),
            ("saturation_enabled", "Saturation buffer"),
            ("trigger_mode", "Trigger mode"),
            ("start_s", "Start"),
            ("range_s", "Range"),
            ("point_count", "Point count"),
            ("point_factor", "Point factor"),
            ("sampling_hz", "Sampling rate"),
            ("compression_type", "Compression"),
            ("rectification", "Rectification"),
            ("bit_size", "Bit size"),
            ("filter_index", "Filter"),
        ]

        differences = []

        for key, name in fields:
            same = pa[key] == fmc[key]
            status = "SAME" if same else "DIFFERENT"
            print(
                f"{name}: {status} "
                f"(PA={pa[key]!r}, FMC={fmc[key]!r})"
            )
            if not same:
                differences.append(name)

        print()
        if differences:
            print(
                "[INFO] Differences found: "
                + ", ".join(differences)
            )
        else:
            print(
                "[INFO] No differences found in the checked "
                "A-scan controls."
            )

        print("[OK] A-SCAN CONFIGURATION DIAGNOSTIC PASSED")

    finally:
        if handle is not None:
            if connected:
                try:
                    disable_acquisition(handle)
                except Exception:
                    pass
                try:
                    disconnect(handle)
                    print("[OK] Disconnected")
                except Exception:
                    pass

            destroy_handle(handle)

        print("[SAFE] Acquisition is OFF.")

if __name__ == "__main__":
    main()
