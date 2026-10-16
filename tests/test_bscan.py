from pathlib import Path

import numpy as np

from oempa.bscan import BScanProcessor
from oempa.fmc import FMCData


PROJECT_DIR = Path(__file__).resolve().parents[1]

FMC_PATH = (
    PROJECT_DIR
    / "data"
    / "fmc16x16_gui.npy"
)


def main():
    print("OEM-PA B-Scan Test")
    print("------------------")

    raw = np.load(
        FMC_PATH
    )

    print(
        f"Loaded FMC shape: {raw.shape}"
    )

    if raw.shape != (
        16,
        16,
        3001,
    ):
        raise RuntimeError(
            f"Unexpected FMC shape: {raw.shape}"
        )

    fmc = FMCData(
        data=raw,
        tx_count=16,
        rx_count=16,
        point_count=3001,
        data_size=1,
        signed=True,
        bit_size=0,
        start_us=0.0,
        sampling_hz=100e6,
    )

    processor = BScanProcessor(
        mode="pulse_echo"
    )

    bscan = processor.process(
        fmc
    )

    print(
        f"B-scan shape: {bscan.shape}"
    )

    print(
        f"Elements: {bscan.element_count}"
    )

    print(
        f"Samples/A-scan: {bscan.point_count}"
    )

    print(
        f"Time range: "
        f"{bscan.time_us[0]:.3f} to "
        f"{bscan.time_us[-1]:.3f} us"
    )

    print(
        f"Amplitude range: "
        f"{int(bscan.minimum)} to "
        f"{int(bscan.maximum)}"
    )

    # Verify diagonal extraction

    for element in range(16):
        if not np.array_equal(
            bscan.data[element, :],
            raw[element, element, :],
        ):
            raise RuntimeError(
                f"Element {element} mapping failed."
            )

    print()
    print(
        "[OK] All 16 pulse-echo A-scans "
        "mapped correctly"
    )

    print(
        "[OK] B-scan backend test PASSED"
    )

    print(
        "[SAFE] No hardware connection was made."
    )


if __name__ == "__main__":
    main()