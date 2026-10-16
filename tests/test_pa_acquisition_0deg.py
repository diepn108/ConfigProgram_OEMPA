from pathlib import Path
import time
import numpy as np

from oempa.api import (
    create_handle,
    destroy_handle,
    connect,
    disconnect,
    disable_acquisition,
    enable_acquisition,
    load_configuration,
    get_cycle_count,
    get_multichannel_state,
    get_cycle_snapshot,
    get_pa_delay_snapshot,
    register_ascan_callback,
    set_multiascan_cycle_count,
    clear_multiascan,
    has_multiascan_cycle,
    copy_multiascan,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_PATH = DATA_DIR / "pa_0deg_ascan.npy"

IP_ADDRESS = "192.168.1.11"
PORT = 5001
TIMEOUT_S = 3.0

def decode_ascan(raw, info):
    if info["data_size"] == 1:
        dtype = np.int8 if info["signed"] else np.uint8
    elif info["data_size"] == 2:
        dtype = np.int16 if info["signed"] else np.uint16
    else:
        raise RuntimeError(
            f"Unsupported A-scan data size: {info['data_size']} bytes."
        )

    data = np.frombuffer(raw, dtype=dtype).copy()

    if data.size != info["point_count"]:
        raise RuntimeError(
            f"Expected {info['point_count']} samples, got {data.size}."
        )

    return data

def main():
    print("OEM-PA 0-Degree PA Acquisition Test")
    print("------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print()
    print("This test WILL enable acquisition briefly.")
    print("The 16-element 0-degree PA aperture will transmit.")

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    handle = None
    connected = False
    acquisition_on = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF")

        load_configuration(handle, CONFIG_PATH)
        disable_acquisition(handle)
        print("[OK] 0-degree PA configuration loaded")

        if get_cycle_count(handle) != 1:
            raise RuntimeError("Expected exactly one PA cycle.")

        multi = get_multichannel_state(handle)
        if multi["enabled"]:
            raise RuntimeError("Multi-Channel must be OFF for this PA test.")

        snapshot = get_cycle_snapshot(handle, 0)
        tx = [i for i, enabled in enumerate(snapshot["tx_enabled"]) if enabled]
        rx = [i for i, enabled in enumerate(snapshot["rx_enabled"]) if enabled]

        if tx != list(range(16)) or rx != list(range(16)):
            raise RuntimeError(
                f"PA aperture mismatch. TX={tx}, RX={rx}"
            )

        delays = get_pa_delay_snapshot(handle, 0)
        if delays["tx_element_count"] != 16 or delays["rx_element_count"] != 16:
            raise RuntimeError("PA delay readback element count mismatch.")

        if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
            raise RuntimeError("TX delays are not all zero.")

        if any(abs(value) > 1e-9 for value in delays["rx_delays_s"]):
            raise RuntimeError("RX delays are not all zero.")

        print("[OK] 16-element TX/RX aperture verified")
        print("[OK] 0-degree TX/RX delays verified")
        print(
            f"[OK] {snapshot['point_count']} points at "
            f"{snapshot['sampling_hz'] / 1e6:.3f} MHz"
        )

        set_multiascan_cycle_count(handle, 1)
        clear_multiascan(handle)
        register_ascan_callback(handle)
        print("[OK] A-scan callback ready")

        print()
        print("Enabling acquisition...")
        enable_acquisition(handle)
        acquisition_on = True

        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            if has_multiascan_cycle(handle, 0):
                break
            time.sleep(0.01)
        else:
            raise TimeoutError(
                "No cycle-0 PA A-scan was received within "
                f"{TIMEOUT_S:.1f} s."
            )

        disable_acquisition(handle)
        acquisition_on = False
        print("[OK] A-scan received; acquisition OFF")

        raw, info = copy_multiascan(handle, 0)
        data = decode_ascan(raw, info)

        np.save(OUTPUT_PATH, data)

        sample_interval_us = 1e6 / snapshot["sampling_hz"]
        duration_us = (
            (data.size - 1) / snapshot["sampling_hz"] * 1e6
            if data.size > 1 else 0.0
        )

        print()
        print("PA A-scan")
        print("----------")
        print(f"Shape: {data.shape}")
        print(f"Data size: {info['data_size']} byte")
        print(f"Signed: {info['signed']}")
        print(f"Bit size enum: {info['bit_size']}")
        print(f"Minimum: {int(data.min())}")
        print(f"Maximum: {int(data.max())}")
        print(f"Sample interval: {sample_interval_us:.6f} us")
        print(f"Record duration: {duration_us:.3f} us")
        print(f"Saved: {OUTPUT_PATH}")

        print()
        print("[OK] FIRST 0-DEGREE PA A-SCAN ACQUISITION PASSED")

    finally:
        if handle is not None:
            if connected:
                if acquisition_on:
                    try:
                        disable_acquisition(handle)
                    except Exception:
                        pass

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
