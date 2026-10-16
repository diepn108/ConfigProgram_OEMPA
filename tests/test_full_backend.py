from pathlib import Path

import numpy as np

from oempa.acquisition import OEMPAAcquisition
from oempa.config import FMCConfig, FMCConfigBuilder
from oempa.driver import OEMPADevice
from oempa.fmc import FMCProcessor


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]

CONFIG_PATH = (
    PROJECT_DIR
    / "configs"
    / "backend_full_test.txt"
)

DATA_PATH = (
    PROJECT_DIR
    / "data"
    / "backend_full_test.npy"
)


# FMC setup

TX_COUNT = 16
RX_COUNT = 16
EXPECTED_CYCLES = TX_COUNT * RX_COUNT


def show_progress(received, total):
    if received == total or received % 16 == 0:
        print(
            f"A-scans received: "
            f"{received}/{total}"
        )


def main():
    print("OEM-PA Full Backend Integration Test")
    print("------------------------------------")

    # Build configuration

    print()
    print("1. Generating configuration...")

    config = FMCConfig(
        tx_count=TX_COUNT,
        rx_count=RX_COUNT,
        range_us=30.0,
        time_slot_us=2000.0,
        analog_gain_db=20.0,
        digital_gain_db=0.0,
        beam_correction_db=0.0,
        filter_index=1,
        pulser_width_us=0.5,
    )

    builder = FMCConfigBuilder(
        config
    )

    builder.save(
        CONFIG_PATH
    )

    print(
        f"[OK] Generated "
        f"{config.cycle_count}-cycle configuration"
    )

    print(
        f"[OK] Configuration saved: "
        f"{CONFIG_PATH}"
    )

    # Create device

    device = OEMPADevice(
        ip_address="192.168.1.11",
        port=5001,
    )

    acquisition = OEMPAAcquisition(
        device
    )

    try:
        # Connect

        print()
        print("2. Connecting to OEM-PA...")

        device.connect()

        print("[OK] Connected")

        print(
            f"Current cycle count: "
            f"{device.cycle_count}"
        )

        # Load configuration

        print()
        print("3. Loading generated configuration...")

        device.load_configuration(
            CONFIG_PATH,
            reconnect=True,
        )

        print(
            "[OK] Configuration write completed"
        )

        print(
            "[OK] Device reconnected"
        )

        # Verify hardware state

        print()
        print("4. Verifying hardware state...")

        status = device.refresh_status()

        print(
            f"Cycle count: "
            f"{status['cycle_count']}"
        )

        print(
            "Multi-channel supported: "
            + (
                "YES"
                if status[
                    "multichannel_supported"
                ]
                else "NO"
            )
        )

        print(
            "Multi-channel enabled: "
            + (
                "YES"
                if status[
                    "multichannel_enabled"
                ]
                else "NO"
            )
        )

        if (
            status["cycle_count"]
            != EXPECTED_CYCLES
        ):
            raise RuntimeError(
                f"Expected "
                f"{EXPECTED_CYCLES} cycles, "
                f"hardware reports "
                f"{status['cycle_count']}."
            )

        if not status[
            "multichannel_supported"
        ]:
            raise RuntimeError(
                "Multi-Channel is not supported."
            )

        if not status[
            "multichannel_enabled"
        ]:
            raise RuntimeError(
                "Multi-Channel is not enabled."
            )

        print(
            "[OK] Hardware configuration verified"
        )

        # Acquire

        print()
        print("5. Acquiring full FMC data...")

        result = acquisition.acquire(
            cycle_count=EXPECTED_CYCLES,
            timeout_s=5.0,
            progress_callback=show_progress,
        )

        print()
        print(
            f"Raw acquisition shape: "
            f"{result.shape}"
        )

        if result.shape != (
            EXPECTED_CYCLES,
            3001,
        ):
            raise RuntimeError(
                f"Unexpected raw shape: "
                f"{result.shape}"
            )

        print(
            "[OK] 256/256 cycles acquired"
        )

        # Process FMC

        print()
        print("6. Building FMC matrix...")

        processor = FMCProcessor(
            tx_count=TX_COUNT,
            rx_count=RX_COUNT,
            start_us=0.0,
            sampling_hz=100e6,
        )

        fmc = processor.process(
            result
        )

        print(
            f"FMC shape: "
            f"{fmc.shape}"
        )

        if fmc.shape != (
            16,
            16,
            3001,
        ):
            raise RuntimeError(
                f"Unexpected FMC shape: "
                f"{fmc.shape}"
            )

        print(
            "[OK] FMC matrix created"
        )

        # Verify mapping

        print()
        print("7. Verifying TX/RX mapping...")

        for tx in range(TX_COUNT):
            for rx in range(RX_COUNT):
                cycle = (
                    tx * RX_COUNT
                    + rx
                )

                mapped_cycle = (
                    fmc.cycle_from_tx_rx(
                        tx,
                        rx,
                    )
                )

                if mapped_cycle != cycle:
                    raise RuntimeError(
                        f"Mapping failure at "
                        f"TX{tx}/RX{rx}."
                    )

                if not np.array_equal(
                    fmc.get_ascan(
                        tx,
                        rx,
                    ),
                    result.scans[
                        cycle,
                        :
                    ],
                ):
                    raise RuntimeError(
                        f"Data mismatch at "
                        f"TX{tx}/RX{rx}."
                    )

        print(
            "[OK] All 256 TX/RX mappings verified"
        )

        # Acquisition information

        print()
        print("8. FMC information...")

        print(
            f"TX elements: "
            f"{fmc.tx_count}"
        )

        print(
            f"RX elements: "
            f"{fmc.rx_count}"
        )

        print(
            f"Samples/A-scan: "
            f"{fmc.point_count}"
        )

        print(
            f"Data size: "
            f"{fmc.data_size} byte(s)"
        )

        print(
            f"Signed: "
            f"{fmc.signed}"
        )

        print(
            f"Bit size enum: "
            f"{fmc.bit_size}"
        )

        print(
            f"Sampling rate: "
            f"{fmc.sampling_hz / 1e6:.1f} MHz"
        )

        print(
            f"Time range: "
            f"{fmc.time_us[0]:.3f} "
            f"to "
            f"{fmc.time_us[-1]:.3f} us"
        )

        print(
            f"Minimum amplitude: "
            f"{int(fmc.data.min())}"
        )

        print(
            f"Maximum amplitude: "
            f"{int(fmc.data.max())}"
        )

        # Save

        print()
        print("9. Saving FMC data...")

        saved_path = fmc.save(
            DATA_PATH
        )

        print(
            f"[OK] Saved: "
            f"{saved_path}"
        )

        # Reload and verify

        loaded = np.load(
            saved_path
        )

        if loaded.shape != fmc.shape:
            raise RuntimeError(
                "Saved FMC shape does not "
                "match original data."
            )

        if not np.array_equal(
            loaded,
            fmc.data,
        ):
            raise RuntimeError(
                "Saved FMC data does not "
                "match original data."
            )

        print(
            "[OK] Saved FMC file verified"
        )

        # Final result

        print()
        print(
            "===================================="
        )

        print(
            "[OK] FULL BACKEND TEST PASSED"
        )

        print(
            "===================================="
        )

        print()

        print(
            "Backend workflow:"
        )

        print(
            "Configuration -> Hardware -> "
            "Acquisition -> FMC -> Save"
        )

        print()

        print(
            f"Final FMC shape: "
            f"{fmc.shape}"
        )

    finally:
        print()
        print("10. Safe shutdown...")

        try:
            acquisition.stop()

            print(
                "[OK] Acquisition OFF"
            )

        finally:
            device.close()

            print(
                "[OK] Device closed"
            )


if __name__ == "__main__":
    main()