import numpy as np

from oempa.cscan import CScanProcessor


def main():
    print("OEM-PA C-Scan Backend Test")
    print("--------------------------")

    y_count = 4
    x_count = 5
    tx_count = 16
    rx_count = 16
    point_count = 3001

    time_us = np.linspace(
        0.0,
        30.0,
        point_count,
    )

    x_positions = np.arange(
        x_count,
        dtype=float,
    )

    y_positions = np.arange(
        y_count,
        dtype=float,
    )

    fmc_grid = np.zeros(
        (
            y_count,
            x_count,
            tx_count,
            rx_count,
            point_count,
        ),
        dtype=np.int8,
    )

    # Synthetic reflectors

    sample_10_us = int(
        np.argmin(
            np.abs(
                time_us - 10.0
            )
        )
    )

    sample_20_us = int(
        np.argmin(
            np.abs(
                time_us - 20.0
            )
        )
    )

    fmc_grid[
        1,
        2,
        0,
        0,
        sample_10_us,
    ] = 80

    fmc_grid[
        3,
        4,
        0,
        0,
        sample_20_us,
    ] = 120

    processor = CScanProcessor(
        gate_start_us=5.0,
        gate_end_us=25.0,
        tx_element=0,
        rx_element=0,
    )

    cscan = processor.process(
        fmc_grid=fmc_grid,
        time_us=time_us,
        x_positions=x_positions,
        y_positions=y_positions,
    )

    print(
        f"FMC grid shape: "
        f"{fmc_grid.shape}"
    )

    print(
        f"C-scan shape: "
        f"{cscan.shape}"
    )

    print(
        f"Amplitude range: "
        f"{cscan.minimum:.0f} to "
        f"{cscan.maximum:.0f}"
    )

    if cscan.shape != (
        y_count,
        x_count,
    ):
        raise RuntimeError(
            "Incorrect C-scan shape."
        )

    if cscan.data[1, 2] != 80:
        raise RuntimeError(
            "First synthetic reflector "
            "was not detected."
        )

    if cscan.data[3, 4] != 120:
        raise RuntimeError(
            "Second synthetic reflector "
            "was not detected."
        )

    print(
        "[OK] Reflector at "
        "(x=2, y=1) detected"
    )

    print(
        "[OK] Reflector at "
        "(x=4, y=3) detected"
    )

    print(
        "[OK] C-scan backend test PASSED"
    )

    print(
        "[SAFE] No hardware connection "
        "was made."
    )


if __name__ == "__main__":
    main()