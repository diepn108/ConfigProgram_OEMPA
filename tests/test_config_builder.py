from pathlib import Path

from oempa.config import (
    FMCConfig,
    FMCConfigBuilder,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_DIR
    / "configs"
    / "fmc16_generated.txt"
)


def main():
    print("OEM-PA FMC Configuration Builder Test")
    print("-------------------------------------")

    config = FMCConfig(
        tx_count=16,
        rx_count=16,
        range_us=30.0,
        time_slot_us=2000.0,
        analog_gain_db=20.0,
        digital_gain_db=0.0,
        beam_correction_db=0.0,
        filter_index=1,
        pulser_width_us=0.5,
    )

    print(
        f"TX elements: {config.tx_count}"
    )

    print(
        f"RX elements: {config.rx_count}"
    )

    print(
        f"Cycle count: {config.cycle_count}"
    )

    builder = FMCConfigBuilder(
        config
    )

    output_path = builder.save(
        OUTPUT_PATH
    )

    text = output_path.read_text(
        encoding="utf-8"
    )

    # Basic structure

    if "CycleCount=256" not in text:
        raise RuntimeError(
            "Generated CycleCount is incorrect."
        )

    if "EnableMultiChannel=1" not in text:
        raise RuntimeError(
            "Multi-Channel is not enabled."
        )

    # Verify all TX acquisition groups

    for tx in range(16):
        cycle = tx * 16

        cycle_section = (
            f"[Cycle:{cycle}]"
        )

        pulser_section = (
            f"[Cycle:{cycle}\\Pulser]"
        )

        if cycle_section not in text:
            raise RuntimeError(
                f"Missing cycle {cycle}."
            )

        if pulser_section not in text:
            raise RuntimeError(
                f"Missing pulser section "
                f"for TX{tx}."
            )

        expected = (
            f"{pulser_section}\n"
            f"Element.count=1\n"
            f"Element={tx}"
        )

        if expected not in text:
            raise RuntimeError(
                f"Incorrect TX mapping "
                f"for TX{tx}."
            )

    # Verify final cycle

    if "[Cycle:255]" not in text:
        raise RuntimeError(
            "Cycle 255 is missing."
        )

    print()
    print(
        "[OK] 16 TX acquisition groups verified"
    )

    print(
        "[OK] Cycles 0-255 generated"
    )

    print(
        "[OK] Multi-Channel enabled"
    )

    print()

    print(
        "Generated configuration:"
    )

    print(
        output_path
    )

    print()

    print(
        "[OK] Configuration builder test PASSED"
    )

    print(
        "[SAFE] No hardware connection was made."
    )


if __name__ == "__main__":
    main()