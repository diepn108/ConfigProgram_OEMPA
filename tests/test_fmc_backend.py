from pathlib import Path

import numpy as np

from oempa.acquisition import (
    OEMPAAcquisition,
)
from oempa.driver import (
    OEMPADevice,
)
from oempa.fmc import (
    FMCProcessor,
)


TX_COUNT = 16
RX_COUNT = 16
EXPECTED_CYCLES = (
    TX_COUNT
    * RX_COUNT
)

PROJECT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_DIR
    / "data"
    / "fmc_backend_test.npy"
)


def show_progress(
    received,
    total,
):
    if (
        received == total
        or received % 16 == 0
    ):
        print(
            f"A-scans received: "
            f"{received}/{total}"
        )


def main():
    print(
        "OEM-PA FMC Backend Test"
    )

    print(
        "-----------------------"
    )

    device = OEMPADevice(
        ip_address="192.168.1.11",
        port=5001,
    )

    acquisition = (
        OEMPAAcquisition(
            device
        )
    )

    try:
        # Connect

        device.connect()

        print(
            "[OK] Connected"
        )

        if (
            device.cycle_count
            != EXPECTED_CYCLES
        ):
            raise RuntimeError(
                f"Expected "
                f"{EXPECTED_CYCLES} "
                f"cycles, hardware "
                f"reports "
                f"{device.cycle_count}."
            )

        if not (
            device.multichannel_supported
        ):
            raise RuntimeError(
                "Multi-Channel is "
                "not supported."
            )

        if not (
            device.multichannel_enabled
        ):
            raise RuntimeError(
                "Multi-Channel is "
                "not enabled."
            )

        print(
            "[OK] Full 16 x 16 "
            "configuration active"
        )

        # Acquire raw cycles

        print()
        print(
            "Acquiring 256 cycles..."
        )

        result = (
            acquisition.acquire(
                cycle_count=(
                    EXPECTED_CYCLES
                ),
                timeout_s=5.0,
                progress_callback=(
                    show_progress
                ),
            )
        )

        print()

        print(
            f"Raw shape: "
            f"{result.shape}"
        )

        # Process FMC

        processor = (
            FMCProcessor(
                tx_count=TX_COUNT,
                rx_count=RX_COUNT,
                start_us=0.0,
                sampling_hz=100e6,
            )
        )

        fmc = processor.process(
            result
        )

        print(
            f"FMC shape: "
            f"{fmc.shape}"
        )

        print(
            f"TX count: "
            f"{fmc.tx_count}"
        )

        print(
            f"RX count: "
            f"{fmc.rx_count}"
        )

        print(
            f"Samples/A-scan: "
            f"{fmc.point_count}"
        )

        print(
            f"Sampling rate: "
            f"{fmc.sampling_hz / 1e6:.1f} MHz"
        )

        print(
            f"Sample interval: "
            f"{fmc.sample_interval_us:.3f} us"
        )

        print(
            f"Time start: "
            f"{fmc.time_us[0]:.3f} us"
        )

        print(
            f"Time end: "
            f"{fmc.time_us[-1]:.3f} us"
        )

        # Mapping verification

        print()
        print(
            "Checking cycle mapping..."
        )

        checks = [
            (0, 0, 0),
            (0, 15, 15),
            (1, 0, 16),
            (1, 15, 31),
            (15, 0, 240),
            (15, 15, 255),
        ]

        for tx, rx, expected in checks:
            cycle = (
                fmc.cycle_from_tx_rx(
                    tx,
                    rx,
                )
            )

            if cycle != expected:
                raise RuntimeError(
                    f"TX{tx}/RX{rx}: "
                    f"expected cycle "
                    f"{expected}, got "
                    f"{cycle}."
                )

            mapped_tx, mapped_rx = (
                fmc.tx_rx_from_cycle(
                    cycle
                )
            )

            if (
                mapped_tx != tx
                or mapped_rx != rx
            ):
                raise RuntimeError(
                    f"Reverse mapping "
                    f"failed for "
                    f"cycle {cycle}."
                )

        print(
            "[OK] TX/RX cycle mapping"
        )

        # Verify reshape did not change data

        for tx in range(
            TX_COUNT
        ):
            for rx in range(
                RX_COUNT
            ):
                cycle = (
                    tx * RX_COUNT
                    + rx
                )

                if not np.array_equal(
                    fmc.data[
                        tx,
                        rx,
                        :
                    ],
                    result.scans[
                        cycle,
                        :
                    ],
                ):
                    raise RuntimeError(
                        f"Data mapping "
                        f"failed for "
                        f"TX{tx}/RX{rx}."
                    )

        print(
            "[OK] All 256 A-scans "
            "mapped correctly"
        )

        # Save

        saved_path = (
            fmc.save(
                OUTPUT_PATH
            )
        )

        print()
        print(
            "Saved:"
        )

        print(
            saved_path
        )

        # Reload and verify

        loaded = np.load(
            saved_path
        )

        if not np.array_equal(
            loaded,
            fmc.data,
        ):
            raise RuntimeError(
                "Saved FMC file does "
                "not match acquired data."
            )

        print(
            "[OK] Saved file verified"
        )

        # Final checks

        if fmc.shape != (
            16,
            16,
            3001,
        ):
            raise RuntimeError(
                f"Unexpected FMC "
                f"shape: {fmc.shape}"
            )

        print()
        print(
            "[OK] FMC backend test PASSED"
        )

    finally:
        acquisition.stop()

        device.close()

        print(
            "[OK] Acquisition OFF"
        )

        print(
            "[OK] Device closed"
        )


if __name__ == "__main__":
    main()