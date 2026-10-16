from pathlib import Path
import math

from oempa.api import (
    create_handle,
    destroy_handle,
    connect,
    disconnect,
    disable_acquisition,
    load_configuration,
    get_pa_delay_snapshot,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_0 = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
CONFIG_30 = PROJECT_DIR / "configs" / "pa_test_30deg.txt"

IP_ADDRESS = "192.168.1.11"
PORT = 5001

EXPECTED_TX_30_US = [
    0.000, 0.052, 0.100, 0.152,
    0.204, 0.256, 0.304, 0.356,
    0.408, 0.456, 0.508, 0.560,
    0.612, 0.660, 0.712, 0.764,
]
EXPECTED_RX_30_US = [
    0.000, 0.050, 0.100, 0.155,
    0.205, 0.255, 0.305, 0.355,
    0.405, 0.460, 0.510, 0.560,
    0.610, 0.660, 0.710, 0.765,
]

def us(values):
    return [value * 1e6 for value in values]

def check(values, expected, tolerance_us=0.002):
    if len(values) != len(expected):
        raise RuntimeError(
            f"Delay count mismatch: {len(values)} != {len(expected)}"
        )
    for i, (actual, wanted) in enumerate(zip(values, expected)):
        if not math.isclose(actual, wanted, rel_tol=0.0, abs_tol=tolerance_us):
            raise RuntimeError(
                f"Delay mismatch at element {i}: "
                f"{actual:.6f} us != {wanted:.6f} us"
            )

def read_config(handle, path, name):
    disable_acquisition(handle)
    load_configuration(handle, path)
    disable_acquisition(handle)

    data = get_pa_delay_snapshot(handle, 0)
    tx = us(data["tx_delays_s"])
    rx = us(data["rx_delays_s"])

    print()
    print(name)
    print("-" * len(name))
    print(f"TX element count: {data['tx_element_count']}")
    print(f"RX element count: {data['rx_element_count']}")
    print(f"RX focal count: {data['rx_focal_count']}")
    print(f"RX focusing enum: {data['rx_focusing']}")
    print(f"TX delays (us): {[round(v, 6) for v in tx]}")
    print(f"RX delays (us): {[round(v, 6) for v in rx]}")

    return data, tx, rx

def main():
    print("OEM-PA PA Hardware Delay Readback Test")
    print("--------------------------------------")
    print("[SAFE] Acquisition remains OFF.")
    print("[SAFE] No A-scan acquisition is started.")

    for path in (CONFIG_0, CONFIG_30):
        if not path.exists():
            raise FileNotFoundError(path)

    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        data0, tx0, rx0 = read_config(
            handle, CONFIG_0, "0-degree hardware readback"
        )

        if data0["tx_element_count"] != 16:
            raise RuntimeError("0-degree TX element count is not 16.")
        if data0["rx_element_count"] != 16:
            raise RuntimeError("0-degree RX element count is not 16.")
        if data0["rx_focal_count"] != 1:
            raise RuntimeError("0-degree RX focal count is not 1.")

        check(tx0, [0.0] * 16)
        check(rx0, [0.0] * 16)
        print("[OK] 0-degree TX/RX hardware delays are zero")

        data30, tx30, rx30 = read_config(
            handle, CONFIG_30, "+30-degree hardware readback"
        )

        if data30["tx_element_count"] != 16:
            raise RuntimeError("+30-degree TX element count is not 16.")
        if data30["rx_element_count"] != 16:
            raise RuntimeError("+30-degree RX element count is not 16.")
        if data30["rx_focal_count"] != 1:
            raise RuntimeError("+30-degree RX focal count is not 1.")

        check(tx30, EXPECTED_TX_30_US)
        check(rx30, EXPECTED_RX_30_US)

        print("[OK] +30-degree TX delays match 4 ns law")
        print("[OK] +30-degree RX delays match 5 ns law")
        print()
        print("[OK] PA HARDWARE DELAY READBACK PASSED")

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
