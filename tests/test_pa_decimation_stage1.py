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
BASE_CONFIG = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_estimate.txt"
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_decimation_stage1.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001
EXPECTED_ELEMENTS = list(range(16))


def close_to(name, actual, expected, tolerance, mismatches):
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        mismatches.append(f"{name}: actual={actual}, expected={expected}")


def validate_offline_candidate():
    if not BASE_CONFIG.exists():
        raise FileNotFoundError(BASE_CONFIG)
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    base_lines = BASE_CONFIG.read_text(encoding="utf-8-sig").splitlines()
    candidate_lines = CONFIG_PATH.read_text(encoding="utf-8-sig").splitlines()

    differences = [
        (line_number, base_line, candidate_line)
        for line_number, (base_line, candidate_line) in enumerate(
            zip(base_lines, candidate_lines),
            start=1,
        )
        if base_line != candidate_line
    ]

    expected_differences = [
        ("PointCount=0", "PointCount=3001"),
        ("CompressionType=Compression", "CompressionType=Decimation"),
    ]
    actual_differences = [(old, new) for _, old, new in differences]

    if len(base_lines) != len(candidate_lines) or actual_differences != expected_differences:
        raise RuntimeError(
            "Candidate config differs from the verified Compression file in "
            f"unexpected ways: {differences}"
        )

    parsed = parse_configuration(CONFIG_PATH)
    if parsed["cycle_count"] != 1 or parsed["multi_channel_enabled"]:
        raise RuntimeError(f"Unexpected offline parser result: {parsed}")

    print("Offline parser result")
    print("---------------------")
    print(f"CycleCount: {parsed['cycle_count']}")
    print(f"MultiChannel enabled: {parsed['multi_channel_enabled']}")
    print("Exact config differences from verified Compression candidate:")
    for line_number, old, new in differences:
        print(f"  line {line_number}: {old} -> {new}")
    print("[OK] AOS offline parser accepted the Decimation candidate")


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
    print(f"RX focusing enum: {delays['rx_focusing']}")
    print(f"DDF enabled: {receive['ddf_enabled']}")
    print(f"RX focal count: {receive['focal_count']}")
    print(f"RX focal TOF (us): {[value * 1e6 for value in receive['focal_tof_s']]}")
    print(f"Emission wedge delay: {receive['emission_wedge_delay_s'] * 1e6:.6f} us")
    print(f"Reception wedge delay: {receive['reception_wedge_delay_s'] * 1e6:.6f} us")

    if cycle_count != 1:
        mismatches.append(f"CycleCount: {cycle_count} != 1")
    if multichannel["enabled"]:
        mismatches.append("MultiChannel is enabled")
    if tx != EXPECTED_ELEMENTS:
        mismatches.append(f"TX aperture: {tx} != elements 0..15")
    if rx != EXPECTED_ELEMENTS:
        mismatches.append(f"RX aperture: {rx} != elements 0..15")
    if delays["tx_element_count"] != 16 or delays["rx_element_count"] != 16:
        mismatches.append("TX/RX delay element counts are not both 16")
    if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
        mismatches.append("TX delays are not all zero")
    if any(abs(value) > 1e-9 for value in delays["rx_delays_s"]):
        mismatches.append("RX delays are not all zero")
    if delays["rx_focal_count"] != 1:
        mismatches.append(f"RX focal count: {delays['rx_focal_count']} != 1")
    if delays["rx_focusing"] != 0:
        mismatches.append(f"RX focusing enum: {delays['rx_focusing']} != Standard(0)")
    if receive["ddf_enabled"]:
        mismatches.append("DDF is enabled")
    if receive["focal_count"] != 1:
        mismatches.append(f"Receive focal count: {receive['focal_count']} != 1")
    if any(abs(value) > 1e-12 for value in receive["focal_tof_s"]):
        mismatches.append("Receive focal TOF is not zero")
    if abs(receive["emission_wedge_delay_s"]) > 1e-12:
        mismatches.append("Emission wedge delay is not zero")
    if abs(receive["reception_wedge_delay_s"]) > 1e-12:
        mismatches.append("Reception wedge delay is not zero")

    close_to("CompressionType enum", snapshot["compression_type"], 1, 0, mismatches)
    close_to("Range (us)", snapshot["range_s"] * 1e6, 30.0, 0.01, mismatches)
    close_to("PointCount", snapshot["point_count"], 3001, 0, mismatches)
    close_to("PointFactor", snapshot["point_factor"], 1, 0, mismatches)
    close_to("SamplingFrequency (MHz)", snapshot["sampling_hz"] / 1e6, 100.0, 0.01, mismatches)
    close_to("TimeSlot (us)", snapshot["time_slot_s"] * 1e6, 2600.0, 0.01, mismatches)
    close_to("Analog gain (dB)", snapshot["gain_analog_db"], 20.0, 0.01, mismatches)
    close_to("Digital gain (dB)", snapshot["gain_digital_db"], 0.0, 0.01, mismatches)
    close_to("Start (us)", snapshot["start_s"] * 1e6, 0.0, 0.001, mismatches)
    if snapshot["rectification"] != 0:
        mismatches.append(f"Rectification enum: {snapshot['rectification']} != Signed(0)")
    if snapshot["bit_size"] != 0:
        mismatches.append(f"Bit-size enum: {snapshot['bit_size']} != 8-bit(0)")
    if snapshot["filter_index"] != 1:
        mismatches.append(f"Filter: {snapshot['filter_index']} != 1")

    return mismatches


def main():
    print("OEM-PA Decimation Stage 1: Load and Readback Only")
    print("--------------------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print("[SAFE] Acquisition will remain OFF; this test has no acquisition-enable call.")

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
            print("[STOP] No retry, readback, or acquisition will be attempted.")
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
        print("[OK] Stage 1 readback PASSED. Acquisition remained OFF; Stage 2 not run.")
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