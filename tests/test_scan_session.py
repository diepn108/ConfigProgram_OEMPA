from pathlib import Path
import shutil

import numpy as np

from oempa.scan_session import ScanSession


PROJECT_DIR = Path(__file__).resolve().parents[1]

TEST_DIR = (
    PROJECT_DIR
    / "data"
    / "test_scan_session"
)


def make_fmc(
    amplitude,
    sample_index,
):
    fmc = np.zeros(
        (
            16,
            16,
            3001,
        ),
        dtype=np.int8,
    )

    fmc[
        0,
        0,
        sample_index,
    ] = amplitude

    return fmc


def main():
    print(
        "OEM-PA Scan Session Test"
    )

    print(
        "------------------------"
    )

    if TEST_DIR.exists():
        shutil.rmtree(
            TEST_DIR
        )

    x_positions = np.array(
        [
            0.0,
            1.0,
            2.0,
        ]
    )

    y_positions = np.array(
        [
            0.0,
            1.0,
        ]
    )

    time_us = np.linspace(
        0.0,
        30.0,
        3001,
    )

    sample_10_us = int(
        np.argmin(
            np.abs(
                time_us - 10.0
            )
        )
    )

    session = ScanSession(
        scan_dir=TEST_DIR,
        x_positions=x_positions,
        y_positions=y_positions,
        time_us=time_us,
        gate_start_us=5.0,
        gate_end_us=20.0,
        tx_element=0,
        rx_element=0,
    )

    print(
        f"Grid: "
        f"{session.grid.x_count} x "
        f"{session.grid.y_count}"
    )

    print(
        f"Positions: "
        f"{session.position_count}"
    )

    amplitudes = [
        [10, 20, 30],
        [40, 50, 60],
    ]

    for y_index in range(
        session.grid.y_count
    ):
        for x_index in range(
            session.grid.x_count
        ):
            amplitude = amplitudes[
                y_index
            ][
                x_index
            ]

            fmc = make_fmc(
                amplitude,
                sample_10_us,
            )

            path, value = (
                session.add_fmc(
                    x_index=x_index,
                    y_index=y_index,
                    fmc_data=fmc,
                )
            )

            print(
                f"({x_index}, "
                f"{y_index}) "
                f"-> {value:.0f} "
                f"-> {path.name}"
            )

    expected = np.array(
        [
            [10, 20, 30],
            [40, 50, 60],
        ],
        dtype=np.float32,
    )

    cscan = (
        session.get_cscan()
    )

    print()
    print(
        f"C-scan shape: "
        f"{cscan.shape}"
    )

    print(
        "C-scan:"
    )

    print(
        cscan
    )

    if not np.array_equal(
        cscan,
        expected,
    ):
        raise RuntimeError(
            "C-scan values are incorrect."
        )

    print()
    print(
        "[OK] Live C-scan updates verified"
    )

    if session.completed_count != 6:
        raise RuntimeError(
            "Incorrect completed count."
        )

    if session.next_position() is not None:
        raise RuntimeError(
            "Session should be complete."
        )

    print(
        "[OK] Scan completion verified"
    )

    # Resume test

    resumed = ScanSession(
        scan_dir=TEST_DIR,
        x_positions=x_positions,
        y_positions=y_positions,
        time_us=time_us,
        gate_start_us=5.0,
        gate_end_us=20.0,
        tx_element=0,
        rx_element=0,
    )

    resumed_cscan = (
        resumed.get_cscan()
    )

    if not np.array_equal(
        resumed_cscan,
        expected,
    ):
        raise RuntimeError(
            "C-scan resume failed."
        )

    print(
        "[OK] C-scan restored from "
        "saved FMC files"
    )

    print(
        "[OK] Scan session backend "
        "test PASSED"
    )

    print(
        "[SAFE] No OEM-PA connection "
        "was made."
    )

    print(
        "[SAFE] No scanner motion "
        "was performed."
    )


if __name__ == "__main__":
    main()