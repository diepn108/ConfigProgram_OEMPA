from oempa.api import (
    connect,
    create_handle,
    destroy_handle,
    disconnect,
    disable_acquisition,
    get_pulser_power_snapshot,
)


IP_ADDRESS = "192.168.1.11"
PORT = 5001


def main():
    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition disabled")

        power = get_pulser_power_snapshot(handle)
        print(f"PulserPowerMax: {power['max_power_w']:.2f} W")
        print(f"PulserPowerCurrent: {power['current_power_w']:.2f} W")

    finally:
        if handle is not None:
            try:
                if connected:
                    disable_acquisition(handle)
                    print("[SAFE] Acquisition is OFF")
                    disconnect(handle)
                    print("[OK] Disconnected")
            finally:
                destroy_handle(handle)


if __name__ == "__main__":
    main()