from pathlib import Path

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
    get_pulser_power_snapshot,
    load_configuration,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg_timeslot_2600us_estimate.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001
EXPECTED_ELEMENTS = list(range(16))


def require_close(name, actual, expected, tolerance):
    if abs(actual - expected) > tolerance:
        raise RuntimeError(
            f"{name} mismatch: {actual} != {expected}"
        )


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


def verify_hardware_readback(handle):
    cycle_count = get_cycle_count(handle)
    multichannel = get_multichannel_state(handle)
    snapshot = get_cycle_snapshot(handle, 0)
    delays = get_pa_delay_snapshot(handle, 0)

    tx_elements = [
        index for index, enabled in enumerate(snapshot["tx_enabled"]) if enabled
    ]
    rx_elements = [
        index for index, enabled in enumerate(snapshot["rx_enabled"]) if enabled
    ]

    print("\nHardware readback")
    print("-----------------")
    print(f"CycleCount: {cycle_count}")
    print(f"MultiChannel enabled: {multichannel['enabled']}")
    print(f"TX aperture: {tx_elements}")
    print(f"RX aperture: {rx_elements}")
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
    print(f"TX element count: {delays['tx_element_count']}")
    print(f"RX element count: {delays['rx_element_count']}")

    if cycle_count != 1:
        raise RuntimeError(f"Expected CycleCount=1, got {cycle_count}.")
    if multichannel["enabled"]:
        raise RuntimeError("MultiChannel must be disabled.")
    if tx_elements != EXPECTED_ELEMENTS:
        raise RuntimeError(f"TX aperture mismatch: {tx_elements}")
    if rx_elements != EXPECTED_ELEMENTS:
        raise RuntimeError(f"RX aperture mismatch: {rx_elements}")
    if delays["tx_element_count"] != 16 or delays["rx_element_count"] != 16:
        raise RuntimeError("Expected 16 TX and 16 RX delay elements.")
    if any(abs(value) > 1e-9 for value in delays["tx_delays_s"]):
        raise RuntimeError("TX delays are not all zero.")
    if any(abs(value) > 1e-9 for value in delays["rx_delays_s"]):
        raise RuntimeError("RX delays are not all zero.")
    if delays["rx_focal_count"] != 1:
        raise RuntimeError("Expected one RX focal law.")

    require_close("TimeSlot (us)", snapshot["time_slot_s"] * 1e6, 2600.0, 0.01)
    require_close("Analog gain (dB)", snapshot["gain_analog_db"], 20.0, 0.01)
    require_close("Digital gain (dB)", snapshot["gain_digital_db"], 0.0, 0.01)
    require_close("Start (us)", snapshot["start_s"] * 1e6, 0.0, 0.001)
    require_close("Range (us)", snapshot["range_s"] * 1e6, 30.0, 0.01)
    if snapshot["point_count"] != 3001:
        raise RuntimeError(
            f"Expected PointCount=3001, got {snapshot['point_count']}."
        )
    require_close("Sampling (MHz)", snapshot["sampling_hz"] / 1e6, 100.0, 0.01)
    if snapshot["filter_index"] != 1:
        raise RuntimeError(f"Expected filter index 1, got {snapshot['filter_index']}.")

    return snapshot, delays


def main():
    print("OEM-PA 0-Degree PA 2600-us Controlled Load Test")
    print("------------------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print("[SAFE] No A-scan acquisition will be started.")
    print("[SAFE] No ultrasound will be intentionally transmitted.")

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition OFF confirmed (eAcqOff succeeded)")

        load_ok = False
        load_error = None
        try:
            load_configuration(handle, CONFIG_PATH)
            load_ok = True
            print("[OK] Configuration loaded through OEMPA_ReadFileWriteHW(..., eAcqOff)")
        except RuntimeError as exc:
            load_error = exc
            print(f"[FAIL] Configuration load: {exc}")

        diagnostic = print_load_diagnostic()

        if not load_ok:
            print("[STOP] Load failed; no readback or retry will be attempted.")
            if diagnostic["before_hw"] and not diagnostic["after_hw"]:
                print("[RESULT] Failure occurred during the hardware-write stage.")
            return 1

        disable_acquisition(handle)
        print("[OK] Acquisition OFF after configuration load")

        verify_hardware_readback(handle)
        power = get_pulser_power_snapshot(handle)
        print("\nPulser power observation")
        print("------------------------")
        print(f"PulserPowerMax: {power['max_power_w']:.2f} W")
        print(f"PulserPowerCurrent: {power['current_power_w']:.2f} W")
        print("[INFO] Current power is an observation, not the rejected configuration estimate.")
        print("[OK] Hardware readback PASSED; acquisition remains OFF.")
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