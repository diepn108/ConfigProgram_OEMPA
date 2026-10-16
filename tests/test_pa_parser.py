from pathlib import Path

from oempa.api import parse_configuration


PROJECT_DIR = Path(__file__).resolve().parents[1]

CONFIG_PATH = (
    PROJECT_DIR
    / "configs"
    / "pa_test_30deg.txt"
)


def main():
    print(
        "OEM-PA PA Vendor Parser Test"
    )

    print(
        "----------------------------"
    )

    print(
        f"Configuration: {CONFIG_PATH}"
    )

    result = parse_configuration(
        CONFIG_PATH
    )

    print()
    print(
        "AOS parser accepted configuration."
    )

    print(
        f"Cycle count: "
        f"{result['cycle_count']}"
    )

    print(
        f"Multi-Channel enabled: "
        f"{result['multi_channel_enabled']}"
    )

    if result["cycle_count"] != 1:
        raise RuntimeError(
            "Expected CycleCount = 1."
        )

    if result["multi_channel_enabled"]:
        raise RuntimeError(
            "Multi-Channel should be disabled "
            "for this PA configuration."
        )

    print()
    print(
        "[OK] OEMPA_ReadFileText accepted file"
    )

    print(
        "[OK] CycleCount = 1"
    )

    print(
        "[OK] Multi-Channel disabled"
    )

    print(
        "[OK] PA vendor parser test PASSED"
    )

    print(
        "[SAFE] No OEM-PA connection was made."
    )

    print(
        "[SAFE] No hardware configuration "
        "was written."
    )

    print(
        "[SAFE] No ultrasound was transmitted."
    )


if __name__ == "__main__":
    main()