from pathlib import Path
import math

from oempa.api import (
    connect,
    create_handle,
    destroy_handle,
    disable_acquisition,
    disconnect,
    get_configuration_diagnostic,
    get_cycle_count,
    get_cycle_snapshot,
    get_multichannel_state,
    get_pa_delay_snapshot,
    get_pa_receive_snapshot,
    get_pulser_power_snapshot,
    load_configuration,
    parse_configuration,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
REFERENCE_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_estimate.txt"
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_single_rx7_stage1.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001
EXPECTED_TX = list(range(16))
EXPECTED_RX = [7]
EXPECTED_CONFIG_DIFFS = [
    ("Element.count=16", "Element.count=1"),
    ("Element=0;1;2;3;4;5;6;7;8;9;10;11;12;13;14;15", "Element=7"),
    ("Delay.count=16;1", "Delay.count=1;1"),
    (
        "Delay=0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us;0.000000 us",
        "Delay=0.000000 us",
    ),
    ("Gain.count=16", "Gain.count=1"),
    (
        "Gain=0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB;0.000000 dB",
        "Gain=0.000000 dB",
    ),
]


def require_close(name, actual, expected, tolerance, mismatches):
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        mismatches.append(f"{name}: actual={actual}, expected={expected}")


def validate_offline_candidate():
    if not REFERENCE_PATH.exists():
        raise FileNotFoundError(REFERENCE_PATH)
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    reference_lines = REFERENCE_PATH.read_text(encoding="utf-8-sig").splitlines()
    candidate_lines = CONFIG_PATH.read_text(encoding="utf-8-sig").splitlines()
    if len(reference_lines) != len(candidate_lines):
        raise RuntimeError("Candidate and reference have different line counts.")

    differences = [
        (line_number, old, new)
        for line_number, (old, new) in enumerate(
            zip(reference_lines, candidate_lines),
            start=1,
        )
        if old != new
    ]
    actual_pairs = [(old, new) for _, old, new in differences]
    if actual_pairs != EXPECTED_CONFIG_DIFFS:
        raise RuntimeError(f"Unexpected candidate config differences: {differences}")

    parsed = parse_configuration(CONFIG_PATH)
    if parsed["cycle_count"] != 1 or parsed["multi_channel_enabled"]:
        raise RuntimeError(f"Unexpected offline parser result: {parsed}")

    print("Offline parser result")
    print("---------------------")
    print(f"CycleCount: {parsed['cycle_count']}")
    print(f"MultiChannel enabled: {parsed['multi_channel_enabled']}")
    print("Exact differences versus verified 16-RX Compression reference:")
    for line_number, old, new in differences:
        print(f"  line {line_number}: {old} -> {new}")
    print("[OK] AOS parser accepted candidate; no TX or acquisition fields changed")


def print_load_diagnostic():
    diagnostic = get_configuration_diagnostic()
    print("\nLoad-stage diagnostic")
    print("---------------------")
    print(f"Entered ReadFileWriteHW: {diagnostic['entered']}")
    print(f"Reached eWriteHW_Enter: {diagnostic['before_hw']}")
    print(f"Reached eWriteHW_Leave: {diagnostic['after_hw']}")
    print(f"Reached eReadFileWriteHW_Leave: {diagnostic['left']}")
    print(f"Parsed cycle count: {diagnostic['parsed_cycle_count']}")
    return diagnostic


def read_and_verify(handle):
    mismatches = []
    cycle_count = get_cycle_count(handle)
    multichannel = get_multichannel_state(handle)
    snapshot = get_cycle_snapshot(handle, 0)
    delays = get_pa_delay_snapshot(handle, 0)
    receive = get_pa_receive_snapshot(handle, 0)

    tx = [index for index, enabled in enumerate(snapshot["tx_enabled"]) if enabled]
    rx = [index for index, enabled in enumerate(snapshot["rx_enabled"]) if enabled]

    print("\nHardware readback")
    print("-----------------")
    print(f"CycleCount: {cycle_count}")
    print(f"MultiChannel enabled: {multichannel['enabled']}")
    print(f"TX aperture: {tx}")
    print(f"RX aperture: {rx}")
    print(f"CompressionType enum: {snapshot['compression_type']}")
    print(f"Range: {snapshot['range_s'] * 1e6:.3f} us")
    print(f"PointCount: {snapshot['point_count']}")
    print(f"PointFactor: {snapshot['point_factor']}")
    print(f"SamplingFrequency: {snapshot['sampling_hz'] / 1e6:.3f} MHz")
    print(f"TimeSlot: {snapshot['time_slot_s'] * 1e6:.3f} us")
    print(f"TX delays (us): {[value * 1e6 for value in delays['tx_delays_s']]}")
    print(f"RX delays (us): {[value * 1e6 for value in delays['rx_delays_s']]}")
    print(f"Analog gain: {snapshot['gain_analog_db']:.3f} dB")
    print(f"Digital gain: {snapshot['gain_digital_db']:.3f} dB")
    print(f"Rectification enum: {snapshot['rectification']}")
    print(f"Bit-size enum: {snapshot['bit_size']}")
    print(f"Filter: {snapshot['filter_index']}")
    print(f"TX/RX delay counts: {delays['tx_element_count']}/{delays['rx_element_count']}")
    print(f"RX focusing enum: {delays['rx_focusing']}")
    print(f"DDF enabled: {receive['ddf_enabled']}")
    print(f"RX gain count/values: {receive['element_count']}/{receive['gains_db']}")
    print(f"RX focal count/TOF (us): {receive['focal_count']}/{[value * 1e6 for value in receive['focal_tof_s']]}")

    if cycle_count != 1:
        mismatches.append(f"CycleCount: {cycle_count} != 1")
    if multichannel["enabled"]:
        mismatches.append("MultiChannel is enabled")
    if tx != EXPECTED_TX:
        mismatches.append(f"TX aperture: {tx} != {EXPECTED_TX}")
    if rx != EXPECTED_RX:
        mismatches.append(f"RX aperture: {rx} != {EXPECTED_RX}")
    if delays["tx_element_count"] != 16 or delays["rx_element_count"] != 1:
        mismatches.append("TX/RX delay counts are not 16/1")
    if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
        mismatches.append("TX delays are not all zero")
    if len(delays["rx_delays_s"]) != 1 or abs(delays["rx_delays_s"][0]) > 1e-9:
        mismatches.append("RX delay for selected element is not zero")
    if delays["rx_focusing"] != 0:
        mismatches.append("RX focusing is not Standard")
    if receive["ddf_enabled"]:
        mismatches.append("DDF is enabled")
    if receive["element_count"] != 1 or len(receive["gains_db"]) != 1:
        mismatches.append("RX gain readback is not one element")
    elif abs(receive["gains_db"][0]) > 0.01:
        mismatches.append("RX gain for selected element is not 0 dB")
    if receive["focal_count"] != 1 or any(abs(value) > 1e-12 for value in receive["focal_tof_s"]):
        mismatches.append("RX focal law is not one zero-TOF Standard law")
    if abs(receive["emission_wedge_delay_s"]) > 1e-12 or abs(receive["reception_wedge_delay_s"]) > 1e-12:
        mismatches.append("Emission or reception wedge delay is nonzero")

    require_close("CompressionType enum", snapshot["compression_type"], 0, 0, mismatches)
    require_close("Range (us)", snapshot["range_s"] * 1e6, 30.0, 0.01, mismatches)
    require_close("PointCount", snapshot["point_count"], 3001, 0, mismatches)
    require_close("PointFactor", snapshot["point_factor"], 256, 0, mismatches)
    require_close("SamplingFrequency (MHz)", snapshot["sampling_hz"] / 1e6, 100.0, 0.01, mismatches)
    require_close("TimeSlot (us)", snapshot["time_slot_s"] * 1e6, 2600.0, 0.01, mismatches)
    require_close("Analog gain (dB)", snapshot["gain_analog_db"], 20.0, 0.01, mismatches)
    require_close("Digital gain (dB)", snapshot["gain_digital_db"], 0.0, 0.01, mismatches)
    require_close("Start (us)", snapshot["start_s"] * 1e6, 0.0, 0.001, mismatches)
    if snapshot["rectification"] != 0:
        mismatches.append("Rectification is not Signed")
    if snapshot["bit_size"] != 0:
        mismatches.append("A-scan bit size is not 8-bit")
    if snapshot["filter_index"] != 1:
        mismatches.append(f"Filter index {snapshot['filter_index']} != 1")

    return mismatches


def main():
    print("OEM-PA 0-Degree Single-RX Stage 1: Load and Readback Only")
    print("----------------------------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print("[SAFE] Acquisition remains OFF; no acquisition-enable call is present.")

    validate_offline_candidate()

    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("\n[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF (eAcqOff succeeded)")

        try:
            load_configuration(handle, CONFIG_PATH)
        except RuntimeError as exc:
            print(f"[FAIL] Configuration load: {exc}")
            print_load_diagnostic()
            print("[STOP] No retry or acquisition will be attempted.")
            return 1

        print("[OK] Candidate loaded through existing OEMPA_ReadFileWriteHW(..., eAcqOff) path")
        load_diagnostic = print_load_diagnostic()
        if not all((
            load_diagnostic["entered"],
            load_diagnostic["before_hw"],
            load_diagnostic["after_hw"],
            load_diagnostic["left"],
        )):
            print("[STOP] Load-stage callbacks incomplete; no acquisition will be attempted.")
            return 1

        disable_acquisition(handle)
        print("[OK] Acquisition OFF after load")

        mismatches = read_and_verify(handle)
        if mismatches:
            print("\n[STOP] Required readback mismatch; no acquisition will be attempted.")
            for mismatch in mismatches:
                print(f"[MISMATCH] {mismatch}")
            return 1

        power = get_pulser_power_snapshot(handle)
        print("\nPulser power observation")
        print("------------------------")
        print(f"PulserPowerMax: {power['max_power_w']:.2f} W")
        print(f"PulserPowerCurrent: {power['current_power_w']:.2f} W")
        print("[INFO] Current power is an observation, not required configuration power.")
        print("[OK] Single-RX Stage 1 readback PASSED. Acquisition remains OFF.")
        return 0

    finally:
        if handle is not None:
            try:
                if connected:
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