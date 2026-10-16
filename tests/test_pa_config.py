from pathlib import Path

from oempa.pa_config import (
    PAConfig,
    PAConfigBuilder,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_DIR
    / "configs"
    / "pa_test_30deg.txt"
)


def main():
    print(
        "OEM-PA PA Configuration Test"
    )

    print(
        "----------------------------"
    )

    config = PAConfig(
        angle_deg=30.0,
        element_count=16,
        start_element=0,
        pitch_mm=0.6,
        velocity_m_s=5900.0,
        range_us=30.0,
        time_slot_us=2000.0,
        analog_gain_db=20.0,
        digital_gain_db=0.0,
        filter_index=1,
        pulser_width_us=0.5,
    )

    builder = PAConfigBuilder(
        config
    )

    law = builder.calculate_law()

    print(
        f"Angle: "
        f"{law.angle_deg:+.1f} deg"
    )

    print(
        f"Aperture: "
        f"{len(law.element_indices)} elements"
    )

    print(
        "Elements:"
    )

    print(
        law.element_indices
    )

    print(
        "Ideal delays (us):"
    )

    print(
        law.ideal_delays_us
    )

    print(
        "TX delays - 4 ns resolution (us):"
    )
    print(
        law.tx_delays_us
    )

    print(
        "RX delays - 5 ns resolution (us):"
    )
    print(
        law.rx_delays_us
    )

    path = builder.save(
        OUTPUT_PATH
    )

    print()
    print(
        f"Configuration written:"
    )

    print(
        path
    )

    text = path.read_text(
        encoding="utf-8",
    )

    required = [
        "CycleCount=1",
        "Element.count=16",
        (
            "Element="
            "0;1;2;3;4;5;6;7;"
            "8;9;10;11;12;13;14;15"
        ),
        "Focusing=Standard",
        "Delay.count=16;1",
        "Gain.count=16",
        "FocalTimeOfFlight.count=1",
    ]

    for item in required:
        if item not in text:
            raise RuntimeError(
                f"Missing configuration "
                f"entry: {item}"
            )

    if "EnableFMC=1" in text:
        raise RuntimeError(
            "PA configuration must not "
            "enable dedicated FMC."
        )

    if "EnableMultiChannel=1" in text:
        raise RuntimeError(
            "PA configuration must not "
            "enable MultiChannel."
        )

    print()
    print(
        "[OK] 16-element TX aperture generated"
    )

    print(
        "[OK] 16-element RX aperture generated"
    )

    print(
        "[OK] TX steering delays generated"
    )

    print(
        "[OK] Static RX focal law generated"
    )

    print(
        "[OK] Dedicated FMC disabled"
    )

    print(
        "[OK] MultiChannel disabled"
    )

    print(
        "[OK] PA configuration file "
        "generation PASSED"
    )

    print(
        "[SAFE] Configuration was NOT "
        "loaded into the OEM-PA."
    )

    print(
        "[SAFE] No ultrasound was transmitted."
    )


if __name__ == "__main__":
    main()