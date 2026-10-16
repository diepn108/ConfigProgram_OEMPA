from oempa.acquisition import OEMPAAcquisition
from oempa.driver import OEMPADevice


EXPECTED_CYCLES = 256


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
    print("OEM-PA Acquisition Backend Test")
    print("-------------------------------")

    device = OEMPADevice(
        ip_address="192.168.1.11",
        port=5001,
    )

    acquisition = OEMPAAcquisition(
        device
    )

    try:
        device.connect()

        print("[OK] Connected")

        if device.cycle_count != EXPECTED_CYCLES:
            raise RuntimeError(
                f"Expected {EXPECTED_CYCLES} cycles, "
                f"hardware reports "
                f"{device.cycle_count}."
            )

        if not device.multichannel_supported:
            raise RuntimeError(
                "Multi-Channel is not supported."
            )

        if not device.multichannel_enabled:
            raise RuntimeError(
                "Multi-Channel is not enabled."
            )

        print(
            "[OK] 256-cycle Multi-Channel "
            "configuration active"
        )

        print()
        print("Acquiring...")

        result = acquisition.acquire(
            cycle_count=EXPECTED_CYCLES,
            timeout_s=5.0,
            progress_callback=show_progress,
        )

        print()

        print(
            f"Raw shape: {result.shape}"
        )

        print(
            f"Cycle count: "
            f"{result.cycle_count}"
        )

        print(
            f"Samples/A-scan: "
            f"{result.point_count}"
        )

        print(
            f"Data size: "
            f"{result.data_size} byte(s)"
        )

        print(
            f"Signed: "
            f"{result.signed}"
        )

        print(
            f"Bit size enum: "
            f"{result.bit_size}"
        )

        print(
            f"Minimum: "
            f"{int(result.scans.min())}"
        )

        print(
            f"Maximum: "
            f"{int(result.scans.max())}"
        )

        if result.shape != (
            256,
            3001,
        ):
            raise RuntimeError(
                f"Unexpected acquisition shape: "
                f"{result.shape}"
            )

        print()
        print(
            "[OK] Acquisition backend test PASSED"
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