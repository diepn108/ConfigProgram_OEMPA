from pathlib import Path

from oempa.api import (
    create_handle,
    destroy_handle,
    connect,
    disconnect,
    disable_acquisition,
    load_configuration,
    get_cycle_snapshot,
    get_pa_delay_snapshot,
    get_pa_receive_snapshot,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
PA_CONFIG = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001

def fmt_us(values):
    return [round(v * 1e6, 6) for v in values]

def main():
    print("OEM-PA 0-Degree PA Receive-Path Diagnostic")
    print("-------------------------------------------")
    print("[SAFE] Acquisition remains OFF.")
    print("[SAFE] No A-scan callback is started.")
    print("[SAFE] No ultrasound acquisition is enabled.")

    handle = None
    connected = False

    try:
        if not PA_CONFIG.exists():
            raise FileNotFoundError(PA_CONFIG)

        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        load_configuration(handle, PA_CONFIG)
        disable_acquisition(handle)
        print("[OK] 0-degree PA configuration loaded")

        cycle = get_cycle_snapshot(handle, 0)
        delays = get_pa_delay_snapshot(handle, 0)
        receive = get_pa_receive_snapshot(handle, 0)

        print()
        print("Receive-path hardware readback")
        print("------------------------------")
        print(f"RX aperture: {cycle['rx_enabled']}")
        print(f"RX gain element count: {receive['element_count']}")
        print(f"RX gains (dB): {receive['gains_db']}")
        print(f"RX delay element count: {delays['rx_element_count']}")
        print(f"RX focal count: {delays['rx_focal_count']}")
        print(f"RX delays (us): {delays['rx_delays_us']}")
        print(f"DDF enabled: {receive['ddf_enabled']}")
        print(f"Focal TOF (us): {fmt_us(receive['focal_tof_s'])}")
        print(
            "Emission wedge delay: "
            f"{receive['emission_wedge_delay_s'] * 1e6:.6f} us"
        )
        print(
            "Reception wedge delay: "
            f"{receive['reception_wedge_delay_s'] * 1e6:.6f} us"
        )

        expected = list(range(16))

        if cycle["rx_enabled"] != expected:
            raise RuntimeError(
                f"Unexpected RX aperture: {cycle['rx_enabled']}"
            )

        if receive["element_count"] != 16:
            raise RuntimeError(
                "Expected 16 receive-gain elements, got "
                f"{receive['element_count']}."
            )

        if any(abs(x) > 1e-6 for x in receive["gains_db"]):
            raise RuntimeError(
                "Expected all receive normalization gains to be 0 dB."
            )

        if delays["rx_element_count"] != 16:
            raise RuntimeError(
                "Expected 16 receive-delay elements, got "
                f"{delays['rx_element_count']}."
            )

        if delays["rx_focal_count"] != 1:
            raise RuntimeError(
                "Expected one static receive focal law, got "
                f"{delays['rx_focal_count']}."
            )

        if any(abs(x) > 1e-9 for x in delays["rx_delays_us"]):
            raise RuntimeError(
                "Expected zero RX delays for the 0-degree law."
            )

        if receive["ddf_enabled"]:
            raise RuntimeError(
                "DDF should be disabled for this static 0-degree law."
            )

        if receive["focal_count"] != 1:
            raise RuntimeError(
                "Expected one focal TOF entry, got "
                f"{receive['focal_count']}."
            )

        if any(abs(x) > 1e-12 for x in receive["focal_tof_s"]):
            raise RuntimeError(
                "Expected zero focal TOF for static focusing."
            )

        if abs(receive["emission_wedge_delay_s"]) > 1e-12:
            raise RuntimeError("Emission wedge delay is not zero.")

        if abs(receive["reception_wedge_delay_s"]) > 1e-12:
            raise RuntimeError("Reception wedge delay is not zero.")

        print()
        print("[OK] RX aperture = elements 0..15")
        print("[OK] RX normalization gains = 0 dB")
        print("[OK] RX static delays = 0 us")
        print("[OK] DDF disabled")
        print("[OK] Focal TOF = 0 us")
        print("[OK] TX/RX wedge delays = 0 us")
        print("[OK] PA RECEIVE-PATH DIAGNOSTIC PASSED")

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
