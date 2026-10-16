from pathlib import Path
import shutil

import numpy as np

from oempa.scan_grid import ScanGrid


PROJECT_DIR = Path(__file__).resolve().parents[1]

TEST_SCAN_DIR = (
    PROJECT_DIR
    / "data"
    / "test_scan_grid"
)


def main():
    print("OEM-PA Scan Grid Test")
    print("---------------------")

    if TEST_SCAN_DIR.exists():
        shutil.rmtree(
            TEST_SCAN_DIR
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

    scan = ScanGrid(
        scan_dir=TEST_SCAN_DIR,
        x_positions=x_positions,
        y_positions=y_positions,
    )

    print(
        f"Grid: "
        f"{scan.x_count} x "
        f"{scan.y_count}"
    )

    print(
        f"Positions: "
        f"{scan.position_count}"
    )

    if scan.position_count != 6:
        raise RuntimeError(
            "Incorrect position count."
        )

    # Synthetic FMC

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
        1000,
    ] = 75

    print()
    print(
        "Saving FMC at "
        "(x=0, y=0)..."
    )

    saved_path = scan.save_fmc(
        x_index=0,
        y_index=0,
        fmc_data=fmc,
    )

    print(
        f"Saved: {saved_path}"
    )

    if not scan.is_complete(
        0,
        0,
    ):
        raise RuntimeError(
            "Saved position was not "
            "marked complete."
        )

    loaded = scan.load_fmc(
        0,
        0,
    )

    if not np.array_equal(
        loaded,
        fmc,
    ):
        raise RuntimeError(
            "Loaded FMC does not match "
            "saved FMC."
        )

    print(
        "[OK] FMC save/load verified"
    )

    print()
    print(
        f"Completed positions: "
        f"{scan.completed_count()} / "
        f"{scan.position_count}"
    )

    next_position = (
        scan.next_incomplete()
    )

    print(
        f"Next incomplete position: "
        f"{next_position}"
    )

    if next_position != (
        1,
        0,
    ):
        raise RuntimeError(
            "Incorrect next position."
        )

    # Save remaining positions

    for y_index in range(
        scan.y_count
    ):
        for x_index in range(
            scan.x_count
        ):
            if scan.is_complete(
                x_index,
                y_index,
            ):
                continue

            test_fmc = np.full(
                (
                    16,
                    16,
                    3001,
                ),
                x_index + y_index,
                dtype=np.int8,
            )

            scan.save_fmc(
                x_index=x_index,
                y_index=y_index,
                fmc_data=test_fmc,
            )

    print()
    print(
        f"Completed positions: "
        f"{scan.completed_count()} / "
        f"{scan.position_count}"
    )

    if scan.completed_count() != 6:
        raise RuntimeError(
            "Not all positions were saved."
        )

    if scan.next_incomplete() is not None:
        raise RuntimeError(
            "Grid should be complete."
        )

    mask = scan.completed_mask()

    if not np.all(
        mask
    ):
        raise RuntimeError(
            "Completion mask is incorrect."
        )

    print(
        "[OK] Position tracking verified"
    )

    print(
        "[OK] Resume tracking verified"
    )

    print(
        "[OK] Scan grid backend test PASSED"
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