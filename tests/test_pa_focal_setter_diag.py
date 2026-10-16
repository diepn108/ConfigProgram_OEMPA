from oempa.api import (
    create_handle,
    destroy_handle,
    connect,
    disconnect,
    disable_acquisition,
    test_pa_focal_law_setters,
)

IP_ADDRESS = "192.168.1.11"
PORT = 5001

def main():
    print("OEM-PA 0-Degree PA Focal-Law Setter Diagnostic")
    print("-----------------------------------------------")
    print("[SAFE] Acquisition will remain OFF.")
    print("[INFO] This test writes only the cycle-0 focal-law fields.")
    print("[INFO] It does not enable ultrasound acquisition.")

    handle = None
    connected = False

    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF")

        results = test_pa_focal_law_setters(handle, cycle=0)

        print()
        print("Vendor focal-law setter sequence")
        print("--------------------------------")
        for name, passed in results.items():
            print(f"{name:.<36} {'PASS' if passed else 'FAIL'}")

        failed = [name for name, passed in results.items() if not passed]

        print()
        if failed:
            print("[RESULT] One or more focal-law hardware operations failed:")
            for name in failed:
                print(f"  - {name}")
        else:
            print("[RESULT] All focal-law setters and the OFF-state commit passed.")
            print("[NEXT] The earlier full configuration failure is outside these")
            print("       focal-law setter calls or depends on the full WriteHW sequence.")

        print()
        print("[OK] PA FOCAL-LAW SETTER DIAGNOSTIC COMPLETE")

    finally:
        if handle is not None:
            if connected:
                try:
                    disable_acquisition(handle)
                except Exception:
                    pass
                try:
                    disconnect(handle)
                    print("[OK] Disconnected")
                except Exception:
                    pass
            destroy_handle(handle)

        print("[SAFE] Acquisition is OFF.")

if __name__ == "__main__":
    main()
