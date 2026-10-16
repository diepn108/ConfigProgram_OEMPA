from oempa import api


def main():
    print("OEM-PA API Test")
    print("---------------")

    handle = api.create_handle()
    connected = False

    try:
        api.connect(
            handle,
            "192.168.1.11",
            5001,
        )

        connected = True

        print("[OK] Connected")

        api.disable_acquisition(
            handle
        )

        print("[OK] Acquisition OFF")

        cycle_count = api.get_cycle_count(
            handle
        )

        print(
            f"Cycle count: {cycle_count}"
        )

        state = api.get_multichannel_state(
            handle
        )

        print(
            "Multi-channel supported:",
            "YES"
            if state["supported"]
            else "NO",
        )

        print(
            "Multi-channel enabled:",
            "YES"
            if state["enabled"]
            else "NO",
        )

        print()
        print("[OK] API layer test PASSED")
        print(
            "[SAFE] Acquisition was not enabled."
        )

    finally:
        if connected:
            api.disable_acquisition(
                handle
            )

            api.disconnect(
                handle
            )

            print("[OK] Disconnected")

        api.destroy_handle(
            handle
        )


if __name__ == "__main__":
    main()