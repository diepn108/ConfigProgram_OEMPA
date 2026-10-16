from oempa.driver import OEMPADevice


def main():
    print("OEM-PA Driver Test")
    print("------------------")

    device = OEMPADevice(
        ip_address="192.168.1.11",
        port=5001,
    )

    try:
        print("Connecting...")

        device.connect()

        print("[OK] Connected")
        print()

        status = device.get_status()

        print("Device Status")
        print("-------------")

        print(
            f"Connected: "
            f"{status['connected']}"
        )

        print(
            f"IP address: "
            f"{status['ip_address']}"
        )

        print(
            f"Port: "
            f"{status['port']}"
        )

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

        print()

        if status["cycle_count"] != 256:
            raise RuntimeError(
                f"Expected 256 cycles, "
                f"but hardware reports "
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
            "[OK] Driver layer test PASSED"
        )

        print(
            "[SAFE] Acquisition was not enabled."
        )

    finally:
        print()
        print("Closing device...")

        device.close()

        print("[OK] Device closed")


if __name__ == "__main__":
    main()