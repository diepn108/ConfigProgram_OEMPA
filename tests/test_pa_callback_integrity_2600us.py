from pathlib import Path
import math
import time

import numpy as np

from oempa.api import (
    clear_multiascan,
    connect,
    copy_ascan,
    copy_multiascan,
    create_handle,
    destroy_handle,
    disable_acquisition,
    disconnect,
    enable_acquisition,
    get_ascan_callback_diagnostic,
    get_cycle_count,
    get_cycle_snapshot,
    get_multichannel_state,
    get_pa_delay_snapshot,
    get_pa_receive_snapshot,
    has_multiascan_cycle,
    load_configuration,
    prepare_ascan_callback_buffers,
    register_ascan_callback,
    set_multiascan_cycle_count,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_estimate.txt"
OUTPUT_PATH = PROJECT_DIR / "data" / "pa_0deg_callback_buffers.npy"
IP_ADDRESS = "192.168.1.11"
PORT = 5001
TIMEOUT_S = 3.0
EXPECTED_ELEMENTS = list(range(16))
MAX_BYTES_PER_SAMPLE = 2


def require_close(name, actual, expected, tolerance):
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(f"{name} mismatch: {actual} != {expected}")


def verify_configuration(
    handle,
    expected_compression_type=None,
    expected_point_count=None,
    expected_point_factor=None,
    expected_rx_elements=None,
):
    cycle_count = get_cycle_count(handle)
    multichannel = get_multichannel_state(handle)
    snapshot = get_cycle_snapshot(handle, 0)
    delays = get_pa_delay_snapshot(handle, 0)
    receive = get_pa_receive_snapshot(handle, 0)

    if expected_rx_elements is None:
        expected_rx_elements = EXPECTED_ELEMENTS

    tx = [index for index, enabled in enumerate(snapshot["tx_enabled"]) if enabled]
    rx = [index for index, enabled in enumerate(snapshot["rx_enabled"]) if enabled]

    print("\nHardware readback")
    print("-----------------")
    print(f"CycleCount: {cycle_count}")
    print(f"MultiChannel enabled: {multichannel['enabled']}")
    print(f"TX aperture: {tx}")
    print(f"RX aperture: {rx}")
    print(f"CompressionType enum: {snapshot['compression_type']}")
    print(f"TimeSlot: {snapshot['time_slot_s'] * 1e6:.3f} us")
    print(f"Analog gain: {snapshot['gain_analog_db']:.3f} dB")
    print(f"Digital gain: {snapshot['gain_digital_db']:.3f} dB")
    print(f"Start: {snapshot['start_s'] * 1e6:.3f} us")
    print(f"Range: {snapshot['range_s'] * 1e6:.3f} us")
    print(f"PointCount: {snapshot['point_count']}")
    print(f"PointFactor: {snapshot['point_factor']}")
    print(f"Sampling: {snapshot['sampling_hz'] / 1e6:.3f} MHz")
    print(f"Filter: {snapshot['filter_index']}")
    print(f"Rectification enum: {snapshot['rectification']}")
    print(f"Bit-size enum: {snapshot['bit_size']}")
    print(f"TX delays (us): {[value * 1e6 for value in delays['tx_delays_s']]}")
    print(f"RX delays (us): {[value * 1e6 for value in delays['rx_delays_s']]}")
    print(f"RX focusing enum: {delays['rx_focusing']}")
    print(f"DDF enabled: {receive['ddf_enabled']}")
    print(f"RX focal count: {receive['focal_count']}")

    if cycle_count != 1:
        raise RuntimeError(f"Expected CycleCount=1, got {cycle_count}.")
    if multichannel["enabled"]:
        raise RuntimeError("MultiChannel must be disabled.")
    if tx != EXPECTED_ELEMENTS or rx != expected_rx_elements:
        raise RuntimeError(
            f"Aperture mismatch: TX={tx}, RX={rx}; expected TX={EXPECTED_ELEMENTS}, "
            f"RX={expected_rx_elements}"
        )
    if delays["tx_element_count"] != 16 or delays["rx_element_count"] != len(expected_rx_elements):
        raise RuntimeError(
            f"Delay element counts mismatch: TX={delays['tx_element_count']}, "
            f"RX={delays['rx_element_count']}"
        )
    if receive["element_count"] != len(expected_rx_elements):
        raise RuntimeError(
            f"RX gain count {receive['element_count']} != {len(expected_rx_elements)}"
        )
    if any(abs(value) > 0.01 for value in receive["gains_db"]):
        raise RuntimeError(f"RX gain is not zero: {receive['gains_db']}")
    if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
        raise RuntimeError("TX delays are not all zero.")
    if any(abs(value) > 1e-9 for value in delays["rx_delays_s"]):
        raise RuntimeError("RX delays are not all zero.")
    if delays["rx_focusing"] != 0:
        raise RuntimeError("Expected Standard RX focusing.")
    if receive["ddf_enabled"]:
        raise RuntimeError("DDF must be disabled.")
    if receive["focal_count"] != 1:
        raise RuntimeError("Expected one reception focal law.")
    if any(abs(value) > 1e-12 for value in receive["focal_tof_s"]):
        raise RuntimeError("Reception focal TOF is not zero.")
    if abs(receive["emission_wedge_delay_s"]) > 1e-12:
        raise RuntimeError("Emission wedge delay is not zero.")
    if abs(receive["reception_wedge_delay_s"]) > 1e-12:
        raise RuntimeError("Reception wedge delay is not zero.")

    require_close("TimeSlot (us)", snapshot["time_slot_s"] * 1e6, 2600.0, 0.01)
    require_close("Analog gain (dB)", snapshot["gain_analog_db"], 20.0, 0.01)
    require_close("Digital gain (dB)", snapshot["gain_digital_db"], 0.0, 0.01)
    require_close("Start (us)", snapshot["start_s"] * 1e6, 0.0, 0.001)
    require_close("Range (us)", snapshot["range_s"] * 1e6, 30.0, 0.01)
    if snapshot["point_count"] <= 0:
        raise RuntimeError("Hardware readback returned no A-scan points.")
    if expected_compression_type is not None and snapshot["compression_type"] != expected_compression_type:
        raise RuntimeError(
            f"CompressionType mismatch: {snapshot['compression_type']} != "
            f"{expected_compression_type}."
        )
    if expected_point_count is not None and snapshot["point_count"] != expected_point_count:
        raise RuntimeError(
            f"PointCount mismatch: {snapshot['point_count']} != {expected_point_count}."
        )
    if expected_point_factor is not None and snapshot["point_factor"] != expected_point_factor:
        raise RuntimeError(
            f"PointFactor mismatch: {snapshot['point_factor']} != {expected_point_factor}."
        )
    require_close("Sampling (MHz)", snapshot["sampling_hz"] / 1e6, 100.0, 0.01)
    if snapshot["rectification"] != 0:
        raise RuntimeError("Expected Signed rectification.")
    if snapshot["bit_size"] != 0:
        raise RuntimeError("Expected 8-bit A-scan format.")
    if snapshot["filter_index"] != 1:
        raise RuntimeError(f"Expected filter index 1, got {snapshot['filter_index']}.")

    print("[OK] Required 2600-us PA configuration readback verified")
    return snapshot


def decode_samples(raw, info):
    if info["data_size"] == 1:
        dtype = np.int8 if info["signed"] else np.uint8
    elif info["data_size"] == 2:
        dtype = np.int16 if info["signed"] else np.uint16
    else:
        raise RuntimeError(
            f"Unsupported callback data size: {info['data_size']} bytes/sample."
        )

    samples = np.frombuffer(raw, dtype=dtype).copy()
    if samples.size != info["point_count"]:
        raise RuntimeError(
            f"Expected {info['point_count']} samples, got {samples.size}."
        )
    return samples


def sample_metrics(samples):
    nonzero = np.flatnonzero(samples)
    first = int(nonzero[0]) if nonzero.size else -1
    last = int(nonzero[-1]) if nonzero.size else -1
    suffix_start = last + 1 if last >= 0 else 0
    return {
        "first_nonzero_index": first,
        "last_nonzero_index": last,
        "nonzero_sample_count": int(nonzero.size),
        "all_samples_after_last_nonzero_zero": bool(
            np.all(samples[suffix_start:] == 0)
        ),
    }


def compare_metrics(label, callback, samples):
    actual = sample_metrics(samples)
    keys = (
        "first_nonzero_index",
        "last_nonzero_index",
        "nonzero_sample_count",
        "all_samples_after_last_nonzero_zero",
    )
    matches = all(actual[key] == callback[key] for key in keys)
    print(
        f"{label}: first={actual['first_nonzero_index']}, "
        f"last={actual['last_nonzero_index']}, "
        f"nonzero={actual['nonzero_sample_count']}, "
        f"zero_after_last={actual['all_samples_after_last_nonzero_zero']}, "
        f"matches_callback={matches}"
    )
    return actual, matches


def decode_buffer_window(buffer, diagnostic, window):
    if not buffer["analyzed"] or not window["sample_count"]:
        return None

    data_size = diagnostic["data_size"]
    raw = window["bytes"]

    if data_size not in (1, 2) or len(raw) != window["sample_count"] * data_size:
        return None

    if buffer["name"] == "SAT":
        return [raw[index * data_size] & 0x01 for index in range(window["sample_count"])]

    if data_size == 1:
        dtype = np.int8 if diagnostic["signed"] else np.uint8
    else:
        dtype = np.int16 if diagnostic["signed"] else np.uint16

    return np.frombuffer(raw, dtype=dtype).tolist()


def print_buffer_diagnostic(buffer, diagnostic):
    name = buffer["name"]
    print(
        f"{name}: flag_valid={buffer['validity_flag']} "
        f"pointer_nonnull={buffer['pointer_nonnull']} "
        f"analyzed={buffer['analyzed']}"
    )

    if not buffer["analyzed"]:
        return

    print(
        f"  first/last nonzero={buffer['first_nonzero_index']}/"
        f"{buffer['last_nonzero_index']}; "
        f"nonzero={buffer['nonzero_sample_count']}; "
        f"exact_zero={buffer['exact_zero_sample_count']}; "
        f"terminal_zero={buffer['terminal_zero_sample_count']}; "
        f"samples 193..end all zero={buffer['sample_193_to_end_all_zero']}"
    )

    if buffer["min_max_valid"]:
        print(
            f"  interpreted sample min/max="
            f"{buffer['minimum_value']}/{buffer['maximum_value']}"
        )
    elif name == "SAT":
        print(
            f"  SAT LSB-set samples={buffer['saturation_lsb_set_count']} "
            "(status bits, not RF amplitude)"
        )
    else:
        print("  interpreted sample min/max unavailable for this data size")

    for window_index, window in enumerate(buffer["windows"]):
        start = window["start_index"]
        count = window["sample_count"]
        label = f"{start}..{start + count - 1}" if count else f"{start}..(no samples)"
        values = decode_buffer_window(buffer, diagnostic, window)
        nonzero_count = 0
        exact_zero_count = 0

        if count:
            sample_size = diagnostic["data_size"]
            raw = window["bytes"]
            for sample_index in range(count):
                sample_bytes = raw[sample_index * sample_size:(sample_index + 1) * sample_size]
                if any(sample_bytes):
                    nonzero_count += 1
                else:
                    exact_zero_count += 1

        if window_index == 0:
            print(
                f"  window {label}: values={values}; "
                f"raw_bytes={window['bytes'].hex(' ')}"
            )
        elif name == "SAT":
            set_count = sum(values) if values is not None else "unavailable"
            print(
                f"  window {label}: raw_nonzero={nonzero_count}, "
                f"raw_zero={exact_zero_count}, SAT_LSB_set={set_count}, "
                f"bytes={window['byte_count']}, truncated={window['truncated']}"
            )
        elif values is not None and values:
            print(
                f"  window {label}: raw_nonzero={nonzero_count}, "
                f"raw_zero={exact_zero_count}, min={min(values)}, max={max(values)}, "
                f"truncated={window['truncated']}"
            )
        else:
            print(
                f"  window {label}: raw_nonzero={nonzero_count}, "
                f"raw_zero={exact_zero_count}, decoded values unavailable, "
                f"truncated={window['truncated']}"
            )


def main(
    config_path=CONFIG_PATH,
    output_path=OUTPUT_PATH,
    expected_compression_type=None,
    expected_point_count=None,
    expected_point_factor=None,
    expected_rx_elements=None,
):
    print("OEM-PA 0-Degree PA Callback Integrity Diagnostic")
    print("------------------------------------------------")
    print(f"Configuration: {config_path}")
    print(f"Output: {output_path}")
    print("[SAFE] No PA parameters will be changed.")
    print("[INFO] Polling is asynchronous; physical pulse count is unknown.")

    if not config_path.exists():
        raise FileNotFoundError(config_path)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {output_path}")

    handle = None
    connected = False
    acquisition_on = False
    result_code = 0

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF")

        load_configuration(handle, config_path)
        disable_acquisition(handle)
        print("[OK] Configuration loaded; acquisition OFF")

        snapshot = verify_configuration(
            handle,
            expected_compression_type=expected_compression_type,
            expected_point_count=expected_point_count,
            expected_point_factor=expected_point_factor,
            expected_rx_elements=expected_rx_elements,
        )

        set_multiascan_cycle_count(handle, 1)
        clear_multiascan(handle)
        register_ascan_callback(handle)
        buffer_capacity_bytes = snapshot["point_count"] * MAX_BYTES_PER_SAMPLE
        prepare_ascan_callback_buffers(handle, buffer_capacity_bytes)
        print(
            "[OK] One callback slot prepared; preallocated "
            f"{buffer_capacity_bytes} bytes per bridge buffer while OFF"
        )

        print("[INFO] Enabling acquisition until cycle 0 callback is observed")
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

        print("[OK] Callback observed; requesting acquisition OFF immediately")
        disable_acquisition(handle)
        acquisition_on = False
        print("[OK] Acquisition OFF")

        diagnostic = get_ascan_callback_diagnostic(handle)
        print("\nCallback-time A-scan buffer diagnostic")
        print("--------------------------------------")
        print(f"Cycle: {diagnostic['cycle']}")
        print(f"Header dataCount: {diagnostic['data_count']}")
        print(f"Header dataSize: {diagnostic['data_size']} byte(s)/sample")
        print(f"Header signed: {diagnostic['signed']}")
        print(f"Header bitSize: {diagnostic['bit_size']}")
        print(f"Expected byte count: {diagnostic['expected_byte_count']}")
        print(
            "Validity flags MAX/MIN/SAT: "
            f"{diagnostic['max_flag']}/{diagnostic['min_flag']}/{diagnostic['sat_flag']}"
        )
        print(
            "Pointers non-null MAX/MIN/SAT: "
            f"{diagnostic['max_pointer_nonnull']}/"
            f"{diagnostic['min_pointer_nonnull']}/"
            f"{diagnostic['sat_pointer_nonnull']}"
        )
        for buffer in diagnostic["buffers"]:
            print_buffer_diagnostic(buffer, diagnostic)

        print("\nMAX bridge-copy summary")
        print("------------------------")
        print(f"First nonzero index: {diagnostic['first_nonzero_index']}")
        print(f"Last nonzero index: {diagnostic['last_nonzero_index']}")
        print(f"Nonzero samples: {diagnostic['nonzero_sample_count']}")
        print(
            "Every raw sample after last nonzero is zero: "
            f"{diagnostic['all_samples_after_last_nonzero_zero']}"
        )
        print(f"Terminal zero samples: {diagnostic['terminal_zero_sample_count']}")
        print(f"Bridge copy capacity sufficient: {diagnostic['bridge_copy_capacity_ok']}")
        print(
            f"Raw window indices {diagnostic['window_start_index']}.."
            f"{diagnostic['window_start_index'] + diagnostic['window_sample_count'] - 1}: "
            f"{decode_buffer_window(diagnostic['buffers'][0], diagnostic, diagnostic['buffers'][0]['windows'][0])}"
        )
        print(f"Raw window bytes (hex): {diagnostic['window_bytes'].hex(' ')}")

        if diagnostic["cycle"] != 0:
            raise RuntimeError(f"Expected callback cycle 0, got {diagnostic['cycle']}.")
        if diagnostic["data_count"] != snapshot["point_count"]:
            print("[STOP] Callback dataCount differs from the verified PointCount.")
            return 1
        if (
            diagnostic["data_size"] != 1
            or not diagnostic["signed"]
            or diagnostic["bit_size"] != 0
        ):
            print("[STOP] Callback encoding differs from signed 8-bit readback.")
            return 1
        if any(
            window["truncated"]
            for buffer in diagnostic["buffers"]
            for window in buffer["windows"]
            if buffer["analyzed"]
        ):
            raise RuntimeError("A callback diagnostic window exceeded its fixed capacity.")
        validity_mismatch = any(
            buffer["validity_flag"] != buffer["pointer_nonnull"]
            for buffer in diagnostic["buffers"]
        )
        if validity_mismatch:
            print("[STOP] SDK buffer validity flag and pointer presence disagree.")
            return 1
        if not diagnostic["max_flag"] or not diagnostic["max_pointer_nonnull"]:
            print("[STOP] MAX buffer unavailable; no bridge-copy comparison will be attempted.")
            return 1
        if not diagnostic["bridge_copy_capacity_ok"]:
            print("[STOP] Callback data exceeded preallocated bridge storage.")
            return 1

        single_raw, single_info = copy_ascan(handle)
        multi_raw, multi_info = copy_multiascan(handle, 0)
        expected_bytes = diagnostic["expected_byte_count"]
        print("\nBridge copy comparison")
        print("-----------------------")
        print(f"Callback expected bytes: {expected_bytes}")
        print(f"Single A-scan bridge bytes: {len(single_raw)}")
        print(f"Multi-A-scan bridge bytes: {len(multi_raw)}")
        print(f"Single and multi bridge buffers byte-identical: {single_raw == multi_raw}")
        print(
            "Callback raw window equals single bridge window: "
            f"{diagnostic['window_bytes'] == single_raw[diagnostic['window_start_index'] * diagnostic['data_size']:diagnostic['window_start_index'] * diagnostic['data_size'] + diagnostic['window_byte_count']]}"
        )

        metadata_matches = (
            single_info["cycle"] == diagnostic["cycle"]
            and single_info["point_count"] == diagnostic["data_count"]
            and single_info["data_size"] == diagnostic["data_size"]
            and single_info["signed"] == diagnostic["signed"]
            and single_info["bit_size"] == diagnostic["bit_size"]
            and multi_info["point_count"] == diagnostic["data_count"]
            and multi_info["data_size"] == diagnostic["data_size"]
            and multi_info["signed"] == diagnostic["signed"]
            and multi_info["bit_size"] == diagnostic["bit_size"]
        )
        print(f"Callback and bridge metadata match: {metadata_matches}")

        if len(single_raw) != expected_bytes or len(multi_raw) != expected_bytes:
            raise RuntimeError("Bridge copy byte count does not match callback header.")

        samples = decode_samples(multi_raw, multi_info)
        _, single_matches = compare_metrics("Single bridge copy", diagnostic, decode_samples(single_raw, single_info))
        _, multi_matches = compare_metrics("Multi bridge copy", diagnostic, samples)
        numpy_raw = samples.tobytes()
        nonzero_indices = np.flatnonzero(samples)
        first_nonzero = int(nonzero_indices[0]) if nonzero_indices.size else None
        last_nonzero = int(nonzero_indices[-1]) if nonzero_indices.size else None
        exact_zero_count = int(np.count_nonzero(samples == 0))
        terminal_zero_count = (
            samples.size - last_nonzero - 1
            if last_nonzero is not None else samples.size
        )
        sample_interval_us = 1e6 / snapshot["sampling_hz"]
        record_duration_us = (samples.size - 1) / snapshot["sampling_hz"] * 1e6

        print("\nDecimation callback waveform")
        print("----------------------------")
        print(f"NumPy shape: {samples.shape}")
        print(f"NumPy dtype: {samples.dtype}")
        print(f"Data size: {multi_info['data_size']} byte(s)/sample")
        print(f"Signed: {multi_info['signed']}")
        print(f"Bit-size enum: {multi_info['bit_size']}")
        print(f"First/last nonzero: {first_nonzero}/{last_nonzero}")
        print(f"Nonzero samples: {int(nonzero_indices.size)}")
        print(f"Exact-zero samples: {exact_zero_count}/{samples.size} ({exact_zero_count / samples.size:.6%})")
        print(f"Terminal zero samples: {terminal_zero_count}")
        print(f"Min/max: {int(samples.min())}/{int(samples.max())}")
        print(f"Sampling frequency: {snapshot['sampling_hz']:.3f} Hz")
        print(f"Sample interval: {sample_interval_us:.6f} us")
        print(f"Record duration: {record_duration_us:.3f} us")
        print(f"Samples 193..end exactly zero: {bool(np.all(samples[193:] == 0))}")
        rms_windows = (
            ("0-1 us", 0, 100),
            ("1-2 us", 100, 200),
            ("2-5 us", 200, 500),
            ("5-10 us", 500, 1000),
            ("10-20 us", 1000, 2000),
            ("20-30 us", 2000, 3001),
        )
        for label, start, stop in rms_windows:
            window = samples[start:min(stop, samples.size)]
            rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2))) if window.size else 0.0
            print(
                f"RMS {label}: {rms:.4f}; "
                f"nonzero={int(np.count_nonzero(window))}/{window.size}"
            )
        _, numpy_matches = compare_metrics("NumPy array", diagnostic, samples)
        print(f"NumPy bytes equal multi bridge bytes: {numpy_raw == multi_raw}")

        np.save(output_path, samples)
        saved = np.load(output_path, allow_pickle=False)
        _, saved_matches = compare_metrics("Saved .npy", diagnostic, saved)
        print(f"Saved file array exactly equals NumPy array: {np.array_equal(saved, samples)}")
        print(f"Saved: {output_path}")

        if not all((metadata_matches, single_matches, multi_matches, numpy_matches, saved_matches)):
            print("[MISMATCH] Data changed between callback and a later storage stage.")
            result_code = 1
        else:
            print("[OK] Callback, bridge copies, NumPy array, and saved file agree.")

        print("[INFO] Acquisition was enabled briefly until callback observation; physical pulse count is unknown.")
        return result_code

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