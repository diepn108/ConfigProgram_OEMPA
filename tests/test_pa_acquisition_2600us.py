from pathlib import Path
import math
import time

import numpy as np

from oempa.api import (
    clear_multiascan,
    connect,
    copy_multiascan,
    create_handle,
    destroy_handle,
    disable_acquisition,
    disconnect,
    enable_acquisition,
    get_cycle_count,
    get_cycle_snapshot,
    get_multichannel_state,
    get_pa_delay_snapshot,
    has_multiascan_cycle,
    load_configuration,
    register_ascan_callback,
    set_multiascan_cycle_count,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_estimate.txt"
OUTPUT_PATH = PROJECT_DIR / "data" / "pa_0deg_2600us_ascan.npy"
IP_ADDRESS = "192.168.1.11"
PORT = 5001
TIMEOUT_S = 3.0
EXPECTED_ELEMENTS = list(range(16))


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


def close_to(name, actual, expected, tolerance):
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(f"{name} mismatch: {actual} != {expected}")


def verify_configuration(handle):
    cycle_count = get_cycle_count(handle)
    multichannel = get_multichannel_state(handle)
    snapshot = get_cycle_snapshot(handle, 0)
    delays = get_pa_delay_snapshot(handle, 0)

    tx = [index for index, enabled in enumerate(snapshot["tx_enabled"]) if enabled]
    rx = [index for index, enabled in enumerate(snapshot["rx_enabled"]) if enabled]

    print("\nHardware readback")
    print("-----------------")
    print(f"CycleCount: {cycle_count}")
    print(f"MultiChannel enabled: {multichannel['enabled']}")
    print(f"TX aperture: {tx}")
    print(f"RX aperture: {rx}")
    print(f"TimeSlot: {snapshot['time_slot_s'] * 1e6:.3f} us")
    print(f"TX delays (us): {[value * 1e6 for value in delays['tx_delays_s']]}")
    print(f"RX delays (us): {[value * 1e6 for value in delays['rx_delays_s']]}")
    print(f"Analog gain: {snapshot['gain_analog_db']:.3f} dB")
    print(f"Digital gain: {snapshot['gain_digital_db']:.3f} dB")
    print(f"Start: {snapshot['start_s'] * 1e6:.3f} us")
    print(f"Range: {snapshot['range_s'] * 1e6:.3f} us")
    print(f"PointCount: {snapshot['point_count']}")
    print(f"Sampling: {snapshot['sampling_hz'] / 1e6:.3f} MHz")
    print(f"Filter: {snapshot['filter_index']}")

    if cycle_count != 1:
        raise RuntimeError(f"Expected CycleCount=1, got {cycle_count}.")
    if multichannel["enabled"]:
        raise RuntimeError("MultiChannel must be disabled.")
    if tx != EXPECTED_ELEMENTS or rx != EXPECTED_ELEMENTS:
        raise RuntimeError(f"Aperture mismatch: TX={tx}, RX={rx}")
    if delays["tx_element_count"] != 16 or delays["rx_element_count"] != 16:
        raise RuntimeError("Expected 16 TX and 16 RX delay elements.")
    if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
        raise RuntimeError("TX delays are not all zero.")
    if any(abs(value) > 1e-9 for value in delays["rx_delays_s"]):
        raise RuntimeError("RX delays are not all zero.")

    close_to("TimeSlot (us)", snapshot["time_slot_s"] * 1e6, 2600.0, 0.01)
    close_to("Analog gain (dB)", snapshot["gain_analog_db"], 20.0, 0.01)
    close_to("Digital gain (dB)", snapshot["gain_digital_db"], 0.0, 0.01)
    close_to("Start (us)", snapshot["start_s"] * 1e6, 0.0, 0.001)
    close_to("Range (us)", snapshot["range_s"] * 1e6, 30.0, 0.01)
    if snapshot["point_count"] != 3001:
        raise RuntimeError(f"Expected PointCount=3001, got {snapshot['point_count']}.")
    close_to("Sampling (MHz)", snapshot["sampling_hz"] / 1e6, 100.0, 0.01)
    if snapshot["filter_index"] != 1:
        raise RuntimeError(f"Expected filter index 1, got {snapshot['filter_index']}.")

    print("[OK] Required 2600-us PA configuration readback verified")
    return snapshot


def analyze_and_save(raw, info, sampling_hz):
    data = decode_ascan(raw, info)

    if OUTPUT_PATH.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {OUTPUT_PATH}")
    np.save(OUTPUT_PATH, data)

    limits = np.iinfo(data.dtype)
    at_min = int(np.count_nonzero(data == limits.min))
    at_max = int(np.count_nonzero(data == limits.max))
    at_limits = at_min + at_max
    sample_interval_us = 1e6 / sampling_hz
    duration_us = (data.size - 1) / sampling_hz * 1e6 if data.size > 1 else 0.0
    nonzero = np.flatnonzero(data)
    last_nonzero_index = int(nonzero[-1]) if nonzero.size else None
    last_nonzero_time_us = (
        last_nonzero_index / sampling_hz * 1e6
        if last_nonzero_index is not None else None
    )
    tail_start_index = math.ceil(1.94e-6 * sampling_hz)
    zero_from_1_94_us = bool(np.all(data[tail_start_index:] == 0))

    print("\nPA A-scan")
    print("----------")
    print("Callback received: True (cycle 0)")
    print(f"NumPy shape: {data.shape}")
    print(f"NumPy dtype: {data.dtype}")
    print(f"Data size: {info['data_size']} byte(s) per sample")
    print(f"Signed: {info['signed']}")
    print(f"Bit size enum: {info['bit_size']}")
    print(f"Minimum: {int(data.min())}")
    print(f"Maximum: {int(data.max())}")
    print(f"Sampling frequency: {sampling_hz:.3f} Hz")
    print(f"Sample interval: {sample_interval_us:.6f} us")
    print(f"Record duration: {duration_us:.3f} us")
    print(f"Samples at ADC minimum {limits.min}: {at_min}")
    print(f"Samples at ADC maximum {limits.max}: {at_max}")
    print(f"Samples at ADC limits: {at_limits}/{data.size} ({at_limits / data.size:.6%})")
    if last_nonzero_index is None:
        print("Last nonzero sample: none")
    else:
        print(
            f"Last nonzero sample: index {last_nonzero_index} "
            f"at {last_nonzero_time_us:.6f} us"
        )
    print(f"All samples from ~1.94 us onward exactly zero: {zero_from_1_94_us}")
    print(f"Saved: {OUTPUT_PATH}")


def main():
    print("OEM-PA 0-Degree PA A-scan at 2600-us TimeSlot")
    print("----------------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print(f"Output: {OUTPUT_PATH}")
    print("[SAFE] Acquisition will remain OFF except while waiting for cycle 0 callback.")
    print("[INFO] Polling is asynchronous; this does not establish the number of physical pulses.")

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {OUTPUT_PATH}")

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
        print("[OK] 2600-us configuration loaded; acquisition OFF")

        snapshot = verify_configuration(handle)

        set_multiascan_cycle_count(handle, 1)
        clear_multiascan(handle)
        register_ascan_callback(handle)
        print("[OK] Exactly one A-scan callback slot prepared")

        print("[INFO] Enabling acquisition until cycle 0 callback is received")
        enable_acquisition(handle)
        acquisition_on = True

        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            if has_multiascan_cycle(handle, 0):
                break
            time.sleep(0.01)
        else:
            disable_acquisition(handle)
            acquisition_on = False
            print("[TIMEOUT] Callback not received; acquisition OFF")
            return 1

        print("[OK] Cycle 0 callback received; requesting acquisition OFF")
        disable_acquisition(handle)
        acquisition_on = False
        print("[OK] Acquisition OFF")

        raw, info = copy_multiascan(handle, 0)
        analyze_and_save(raw, info, snapshot["sampling_hz"])
        print("[INFO] Acquisition was enabled briefly until callback receipt; physical pulse count is unknown.")
        return 0

    finally:
        if handle is not None:
            try:
                if connected:
                    if acquisition_on:
                        disable_acquisition(handle)
                        acquisition_on = False
                    disable_acquisition(handle)
                    print("[SAFE] Acquisition OFF before disconnect")
            finally:
                try:
                    if connected:
                        disconnect(handle)
                        print("[OK] Disconnected")
                finally:
                    destroy_handle(handle)


if __name__ == "__main__":
    raise SystemExit(main())