from pathlib import Path
from oempa.api import (
    create_handle, destroy_handle, connect, disconnect,
    disable_acquisition, load_configuration, parse_configuration,
    get_configuration_diagnostic,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
PA_CONFIG = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001

def main():
    print("OEM-PA PA Configuration Load Diagnostic")
    print("---------------------------------------")
    print(f"Configuration: {PA_CONFIG}")
    print("[SAFE] Acquisition remains OFF.")
    print("[SAFE] No A-scan callback is started.")
    print("[SAFE] No ultrasound acquisition is enabled.")

    if not PA_CONFIG.exists():
        raise FileNotFoundError(PA_CONFIG)

    parsed = parse_configuration(PA_CONFIG)
    print("\nOffline parser check")
    print("--------------------")
    print(f"Cycle count: {parsed['cycle_count']}")
    print(f"Multi-Channel enabled: {parsed['multi_channel_enabled']}")
    print("[OK] File parses with OEMPA_ReadFileText")

    handle = None
    connected = False
    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("\n[OK] Connected")
        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF")

        load_ok = False
        try:
            load_configuration(handle, PA_CONFIG)
            load_ok = True
        except RuntimeError as exc:
            print(f"[FAIL] {exc}")

        d = get_configuration_diagnostic()
        print("\nLoad-stage diagnostic")
        print("---------------------")
        print(f"Entered ReadFileWriteHW: {d['entered']}")
        print(f"Reached before HW write: {d['before_hw']}")
        print(f"Reached after HW write: {d['after_hw']}")
        print(f"Reached load exit: {d['left']}")
        print(f"Parsed cycle count: {d['parsed_cycle_count']}")

        print()
        if load_ok:
            print("[RESULT] Configuration load succeeded.")
        elif not d["entered"]:
            print("[RESULT] Failure occurred before OEMPA_ReadFileWriteHW entered.")
        elif not d["before_hw"]:
            print("[RESULT] Failure occurred while reading/parsing/preparing the configuration.")
        elif not d["after_hw"]:
            print("[RESULT] Configuration reached the hardware-write stage but did not complete it.")
        elif not d["left"]:
            print("[RESULT] Hardware write completed, but load did not reach normal exit.")
        else:
            print("[RESULT] Customized API reached normal exit but returned failure.")

        print("[OK] CONFIGURATION LOAD DIAGNOSTIC COMPLETE")
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
