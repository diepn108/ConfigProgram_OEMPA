import numpy as np

from oempa.focal_law import FocalLawCalculator


def print_law(
    calculator,
    angle_deg,
):
    law = calculator.steering_delays(
        angle_deg=angle_deg,
        start_element=0,
        aperture_size=16,
    )

    print()
    print(
        f"Steering angle: {angle_deg:+.1f} deg"
    )

    print(
        "Element   Position    Ideal       TX       RX"
    )

    print(
        "            (mm)       (us)      (us)     (us)"
    )

    print(
        "------------------------------------------------"
    )

    for element, position, ideal, tx, rx in zip(
        law.element_indices,
        law.element_positions_mm,
        law.ideal_delays_us,
        law.tx_delays_us,
        law.rx_delays_us,
    ):
        print(
            f"{element:7d}"
            f"{position:11.3f}"
            f"{ideal:11.6f}"
            f"{tx:10.3f}"
            f"{rx:9.3f}"
        )

    return law


def main():
    print(
        "OEM-PA Phased-Array Focal Law Test"
    )

    print(
        "----------------------------------"
    )

    calculator = FocalLawCalculator(
        element_count=16,
        pitch_mm=0.6,
        velocity_m_s=5900.0,
        tx_resolution_ns=4.0,
        rx_resolution_ns=5.0,
    )

    law_zero = print_law(
        calculator,
        0.0,
    )

    law_positive = print_law(
        calculator,
        30.0,
    )

    law_negative = print_law(
        calculator,
        -30.0,
    )

    if not np.allclose(
        law_zero.tx_delays_us,
        0.0,
    ):
        raise RuntimeError(
            "0-degree TX delays are not zero."
        )

    if not np.allclose(
        law_zero.rx_delays_us,
        0.0,
    ):
        raise RuntimeError(
            "0-degree RX delays are not zero."
        )

    tx_step_us = 0.004
    rx_step_us = 0.005

    tx_units = (
        law_positive.tx_delays_us
        / tx_step_us
    )

    rx_units = (
        law_positive.rx_delays_us
        / rx_step_us
    )

    if not np.allclose(
        tx_units,
        np.round(tx_units),
    ):
        raise RuntimeError(
            "TX delays are not quantized to 4 ns."
        )

    if not np.allclose(
        rx_units,
        np.round(rx_units),
    ):
        raise RuntimeError(
            "RX delays are not quantized to 5 ns."
        )

    if not np.all(
        np.diff(
            law_positive.tx_delays_us
        ) >= 0
    ):
        raise RuntimeError(
            "Positive TX steering is not monotonic."
        )

    if not np.all(
        np.diff(
            law_negative.tx_delays_us
        ) <= 0
    ):
        raise RuntimeError(
            "Negative TX steering is not monotonic."
        )

    print()
    print(
        "[OK] 0-degree focal law verified"
    )

    print(
        "[OK] +30-degree steering verified"
    )

    print(
        "[OK] -30-degree steering verified"
    )

    print(
        "[OK] TX quantization = 4 ns"
    )

    print(
        "[OK] RX quantization = 5 ns"
    )

    print(
        "[OK] Focal-law calculation test PASSED"
    )

    print(
        "[SAFE] No OEM-PA connection was made."
    )

    print(
        "[SAFE] No ultrasound was transmitted."
    )


if __name__ == "__main__":
    main()