from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_DIR
    / "configs"
    / "fmc16_full.txt"
)


# Probe

TX_COUNT = 16
RX_COUNT = 16

TOTAL_CYCLES = TX_COUNT * RX_COUNT


# Acquisition settings

RANGE_US = 30.0
TIME_SLOT_US = 2000.0

GAIN_DIGITAL_DB = 0.0
GAIN_ANALOG_DB = 20.0
BEAM_CORRECTION_DB = 0.0

FILTER_INDEX = 1

PULSER_WIDTH_US = 0.5


# Helpers

def add_common_cycle(lines):
    lines.append(
        f"GainDigital={GAIN_DIGITAL_DB:.6f} dB"
    )
    lines.append(
        f"Range={RANGE_US:.6f} us"
    )
    lines.append(
        "PointCount=0"
    )
    lines.append(
        "Rectification=Signed"
    )
    lines.append(
        f"FilterIndex={FILTER_INDEX}"
    )
    lines.append(
        "GateCount=0"
    )
    lines.append(
        f"BeamCorrection={BEAM_CORRECTION_DB:.6f} dB"
    )


def add_hardware_acquisition_cycle(
    lines,
    cycle,
    tx,
):
    lines.append(
        f"[Cycle:{cycle}]"
    )

    add_common_cycle(lines)

    lines.append(
        f"GainAnalog={GAIN_ANALOG_DB:.6f} dB"
    )
    lines.append(
        f"HWAcquisitionTime={TIME_SLOT_US:.6f} us"
    )
    lines.append(
        "HWAcquisition=1"
    )

    lines.append("")

    lines.append(
        f"[Cycle:{cycle}\\Pulser]"
    )
    lines.append(
        "Element.count=1"
    )
    lines.append(
        f"Element={tx}"
    )
    lines.append(
        "Width.count=1"
    )
    lines.append(
        f"Width={PULSER_WIDTH_US:.6f} us"
    )

    lines.append("")

    lines.append(
        f"[Cycle:{cycle}\\Receiver]"
    )
    lines.append(
        "Element.count=1"
    )
    lines.append(
        "Element=0"
    )
    lines.append(
        "StartFirst=0"
    )
    lines.append(
        f"Start.count={RX_COUNT}"
    )

    start_values = ";".join(
        ["0.000000 us"] * RX_COUNT
    )

    lines.append(
        f"Start={start_values}"
    )

    decimation_values = ";".join(
        ["0"] * RX_COUNT
    )

    lines.append(
        f"Decimation={decimation_values}"
    )

    lines.append("")


def add_replay_cycle(
    lines,
    cycle,
    rx,
):
    lines.append(
        f"[Cycle:{cycle}]"
    )

    add_common_cycle(lines)

    lines.append(
        f"HWReplayTime={TIME_SLOT_US:.6f} us"
    )
    lines.append(
        "HWAcquisition=0"
    )

    lines.append("")

    lines.append(
        f"[Cycle:{cycle}\\Receiver]"
    )
    lines.append(
        "Element.count=1"
    )
    lines.append(
        f"Element={rx}"
    )

    lines.append("")


# Generate configuration

def generate_config():
    lines = []

    lines.append(
        "[Root]"
    )
    lines.append(
        "VersionDriverOEMPA=1.1.5.4"
    )
    lines.append(
        f"CycleCount={TOTAL_CYCLES}"
    )
    lines.append(
        "EnableMultiChannel=1"
    )
    lines.append("")

    for tx in range(TX_COUNT):
        base_cycle = tx * RX_COUNT

        add_hardware_acquisition_cycle(
            lines,
            base_cycle,
            tx,
        )

        for rx in range(
            1,
            RX_COUNT,
        ):
            cycle = (
                base_cycle
                + rx
            )

            add_replay_cycle(
                lines,
                cycle,
                rx,
            )

    return "\n".join(lines)


# Validate generated structure

def validate_config(text):
    expected_acquisition_cycles = [
        tx * RX_COUNT
        for tx in range(TX_COUNT)
    ]

    if (
        f"CycleCount={TOTAL_CYCLES}"
        not in text
    ):
        raise RuntimeError(
            "Incorrect CycleCount"
        )

    if "EnableMultiChannel=1" not in text:
        raise RuntimeError(
            "Multi-Channel is not enabled"
        )

    for tx, cycle in enumerate(
        expected_acquisition_cycles
    ):
        section = (
            f"[Cycle:{cycle}\\Pulser]"
        )

        if section not in text:
            raise RuntimeError(
                f"Missing pulser section "
                f"for TX{tx}"
            )

        expected_element = (
            f"{section}\n"
            f"Element.count=1\n"
            f"Element={tx}"
        )

        if expected_element not in text:
            raise RuntimeError(
                f"Incorrect TX mapping "
                f"for TX{tx}"
            )

    if "[Cycle:255]" not in text:
        raise RuntimeError(
            "Final cycle 255 is missing"
        )


# Main

def main():
    print(
        "AOS OEM-PA Full 16 x 16 "
        "FMC Configuration Generator"
    )
    print(
        "-------------------------------------------"
    )

    print(
        f"TX elements: {TX_COUNT}"
    )
    print(
        f"RX elements: {RX_COUNT}"
    )
    print(
        f"Total cycles: {TOTAL_CYCLES}"
    )

    print()

    config_text = generate_config()

    validate_config(
        config_text
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        config_text,
        encoding="utf-8",
    )

    print(
        "[OK] Configuration structure validated"
    )

    print()
    print(
        "Hardware acquisition cycles:"
    )

    for tx in range(TX_COUNT):
        cycle = tx * RX_COUNT

        print(
            f"TX{tx:02d}: "
            f"cycle {cycle:3d} "
            f"-> RX0-15"
        )

    print()

    print(
        f"[OK] Generated {TOTAL_CYCLES} cycles"
    )

    print()

    print(
        "Configuration saved:"
    )
    print(
        OUTPUT_PATH
    )

    print()

    print(
        "[SAFE] No OEM-PA connection was made."
    )
    print(
        "[SAFE] No hardware configuration was changed."
    )


if __name__ == "__main__":
    main()