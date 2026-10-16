from pathlib import Path
import math

from oempa.api import parse_configuration


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_30deg.txt"

EXPECTED_ELEMENTS = list(range(16))
EXPECTED_TX_DELAYS_US = [
    0.000, 0.052, 0.100, 0.152,
    0.204, 0.256, 0.304, 0.356,
    0.408, 0.456, 0.508, 0.560,
    0.612, 0.660, 0.712, 0.764,
]
EXPECTED_RX_DELAYS_US = [
    0.000, 0.050, 0.100, 0.155,
    0.205, 0.255, 0.305, 0.355,
    0.405, 0.460, 0.510, 0.560,
    0.610, 0.660, 0.710, 0.765,
]


def parse_sections(path):
    sections = {}
    current = None

    for raw_line in path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    ).splitlines():
        line = raw_line.strip()

        if not line or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections[current] = {}
            continue

        if current is None or "=" not in line:
            continue

        key, value = line.split("=", 1)
        sections[current][key.strip()] = value.strip()

    return sections


def parse_int_list(value):
    return [
        int(item.strip())
        for item in value.split(";")
        if item.strip()
    ]


def parse_float_list_us(value):
    values = []

    for item in value.split(";"):
        item = item.strip()

        if not item:
            continue

        if item.lower().endswith("us"):
            item = item[:-2].strip()

        values.append(float(item))

    return values


def assert_close_list(actual, expected, tolerance_us=0.0005):
    if len(actual) != len(expected):
        raise RuntimeError(
            f"Delay count mismatch: "
            f"actual={len(actual)}, expected={len(expected)}"
        )

    for index, (a, e) in enumerate(zip(actual, expected)):
        if not math.isclose(
            a,
            e,
            rel_tol=0.0,
            abs_tol=tolerance_us,
        ):
            raise RuntimeError(
                f"Delay mismatch at element {index}: "
                f"actual={a:.6f} us, expected={e:.6f} us"
            )


def verify_focal_section(
    section,
    expected_delays,
    name,
):
    element_count = int(section["Element.count"])
    elements = parse_int_list(section["Element"])

    delay_shape = parse_int_list(section["Delay.count"])
    delays = parse_float_list_us(section["Delay"])

    if element_count != 16:
        raise RuntimeError(
            f"{name} Element.count is {element_count}, expected 16."
        )

    if elements != EXPECTED_ELEMENTS:
        raise RuntimeError(
            f"{name} aperture is {elements}, expected 0..15."
        )

    if delay_shape != [16, 1]:
        raise RuntimeError(
            f"{name} Delay.count is {delay_shape}, expected [16, 1]."
        )

    if len(delays) != 16:
        raise RuntimeError(
            f"{name} has {len(delays)} delays, expected 16."
        )

    assert_close_list(
        delays,
        expected_delays,
    )

    return delays


def main():
    print("OEM-PA PA Focal-Law Parser Test")
    print("-------------------------------")
    print(f"Configuration: {CONFIG_PATH}")

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration not found: {CONFIG_PATH}"
        )

    print()
    print("Step 1: AOS vendor parser")

    result = parse_configuration(CONFIG_PATH)

    print(f"Cycle count: {result['cycle_count']}")
    print(
        f"Multi-Channel enabled: "
        f"{result['multi_channel_enabled']}"
    )

    if result["cycle_count"] != 1:
        raise RuntimeError("Expected CycleCount = 1.")

    if result["multi_channel_enabled"]:
        raise RuntimeError(
            "Multi-Channel must be disabled for PA mode."
        )

    print("[OK] AOS OEMPA_ReadFileText accepted configuration")

    print()
    print("Step 2: PA focal-law fields")

    sections = parse_sections(CONFIG_PATH)

    pulser_name = r"Cycle:0\Pulser"
    receiver_name = r"Cycle:0\Receiver"

    if pulser_name not in sections:
        raise RuntimeError("Pulser section is missing.")

    if receiver_name not in sections:
        raise RuntimeError("Receiver section is missing.")

    tx = sections[pulser_name]
    rx = sections[receiver_name]

    tx_delays = verify_focal_section(
        tx,
        EXPECTED_TX_DELAYS_US,
        "TX",
    )

    rx_delays = verify_focal_section(
        rx,
        EXPECTED_RX_DELAYS_US,
        "RX",
    )

    if rx.get("Focusing") != "Standard":
        raise RuntimeError(
            f"RX Focusing is {rx.get('Focusing')!r}, "
            f"expected 'Standard'."
        )

    focal_count = int(
        rx.get("FocalTimeOfFlight.count", "0")
    )

    if focal_count != 1:
        raise RuntimeError(
            f"RX focal count is {focal_count}, expected 1."
        )

    print(f"TX elements: {EXPECTED_ELEMENTS}")
    print(f"RX elements: {EXPECTED_ELEMENTS}")
    print(f"TX delays (us): {tx_delays}")
    print(f"RX delays (us): {rx_delays}")
    print("RX focusing: Standard")
    print("RX focal count: 1")

    print()
    print("[OK] TX aperture = elements 0..15")
    print("[OK] RX aperture = elements 0..15")
    print("[OK] TX Delay.count = 16;1")
    print("[OK] RX Delay.count = 16;1")
    print("[OK] TX delays match 4 ns quantization")
    print("[OK] RX delays match 5 ns quantization")
    print("[OK] RX standard focusing verified")
    print("[OK] PA focal-law parser test PASSED")

    print()
    print("[SAFE] No OEM-PA connection was made.")
    print("[SAFE] No hardware configuration was written.")
    print("[SAFE] No ultrasound was transmitted.")


if __name__ == "__main__":
    main()
