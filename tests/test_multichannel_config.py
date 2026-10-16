import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_DIR = PROJECT_DIR / "bridge"
CONFIG_PATH = PROJECT_DIR / "configs" / "fmc16_tx0.oemmc"

AOS_DIR = Path(r"C:\Program Files\AOS\OEMPA 1.1.5.4")
BRIDGE_PATH = BRIDGE_DIR / "oempa_bridge.dll"


# Runtime

os.add_dll_directory(str(AOS_DIR))
os.add_dll_directory(str(BRIDGE_DIR))

bridge = ctypes.CDLL(str(BRIDGE_PATH))


# Function signatures

bridge.OEMPA_Create.restype = ctypes.c_void_p

bridge.OEMPA_Destroy.argtypes = [
    ctypes.c_void_p
]

bridge.OEMPA_Connect.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ushort
]
bridge.OEMPA_Connect.restype = ctypes.c_int

bridge.OEMPA_Disconnect.argtypes = [
    ctypes.c_void_p
]
bridge.OEMPA_Disconnect.restype = ctypes.c_int

bridge.OEMPA_LoadConfiguration.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p
]
bridge.OEMPA_LoadConfiguration.restype = ctypes.c_int

bridge.OEMPA_GetConfigurationDiagnostic.argtypes = [
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int)
]
bridge.OEMPA_GetConfigurationDiagnostic.restype = ctypes.c_int

bridge.OEMPA_GetCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int)
]
bridge.OEMPA_GetCycleCount.restype = ctypes.c_int

bridge.OEMPA_GetMultiChannelSupport.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int)
]
bridge.OEMPA_GetMultiChannelSupport.restype = ctypes.c_int

bridge.OEMPA_DisableAcquisition.argtypes = [
    ctypes.c_void_p
]
bridge.OEMPA_DisableAcquisition.restype = ctypes.c_int


# Test

def main():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(CONFIG_PATH)

    print("AOS OEM-PA Multi-Channel Configuration Diagnostic")
    print("--------------------------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print()

    handle = bridge.OEMPA_Create()

    if not handle:
        raise RuntimeError("Failed to create OEM-PA device.")

    connected = False

    try:
        if not bridge.OEMPA_Connect(
            handle,
            "192.168.1.11",
            5001
        ):
            raise RuntimeError("Failed to connect.")

        connected = True

        print("[OK] Connected")
        print()
        print("Loading configuration")
        print("---------------------")
        print(CONFIG_PATH)
        print()

        load_result = bridge.OEMPA_LoadConfiguration(
            handle,
            str(CONFIG_PATH)
        )

        # Read configuration diagnostics

        entered = ctypes.c_int()
        before_hw = ctypes.c_int()
        after_hw = ctypes.c_int()
        left = ctypes.c_int()
        parsed_cycle_count = ctypes.c_int()

        diagnostic_ok = bridge.OEMPA_GetConfigurationDiagnostic(
            ctypes.byref(entered),
            ctypes.byref(before_hw),
            ctypes.byref(after_hw),
            ctypes.byref(left),
            ctypes.byref(parsed_cycle_count)
        )

        print("Configuration Diagnostic")
        print("------------------------")
        print(
            f"Load result:        "
            f"{'SUCCESS' if load_result else 'FAILED'}"
        )

        if diagnostic_ok:
            print(
                f"Callback entered:   "
                f"{'YES' if entered.value else 'NO'}"
            )
            print(
                f"Reached pre-HW:     "
                f"{'YES' if before_hw.value else 'NO'}"
            )
            print(
                f"Reached post-HW:    "
                f"{'YES' if after_hw.value else 'NO'}"
            )
            print(
                f"Reached exit:       "
                f"{'YES' if left.value else 'NO'}"
            )
            print(
                f"Parsed cycle count: "
                f"{parsed_cycle_count.value}"
            )
        else:
            print(
                "[ERROR] Could not read configuration diagnostics."
            )

        # Stop here if configuration loading failed.
        # Do not attempt acquisition.

        if not load_result:
            print()
            print("[STOP] Configuration load failed.")
            print("[SAFE] Acquisition was NOT enabled.")
            return

        print()
        print("[OK] Configuration loaded")

        # Hardware readback

        cycle_count = ctypes.c_int()

        if not bridge.OEMPA_GetCycleCount(
            handle,
            ctypes.byref(cycle_count)
        ):
            raise RuntimeError(
                "Failed to read cycle count."
            )

        supported = ctypes.c_int()
        enabled = ctypes.c_int()

        if not bridge.OEMPA_GetMultiChannelSupport(
            handle,
            ctypes.byref(supported),
            ctypes.byref(enabled)
        ):
            raise RuntimeError(
                "Failed to read Multi-Channel state."
            )

        print()
        print("Hardware Readback")
        print("-----------------")
        print(
            f"Cycle count:           "
            f"{cycle_count.value}"
        )
        print(
            f"Multi-channel support: "
            f"{'YES' if supported.value else 'NO'}"
        )
        print(
            f"Multi-channel enabled: "
            f"{'YES' if enabled.value else 'NO'}"
        )

        if cycle_count.value != 16:
            raise RuntimeError(
                f"Expected 16 cycles, "
                f"got {cycle_count.value}."
            )

        if not supported.value:
            raise RuntimeError(
                "Hardware no longer reports "
                "Multi-Channel support."
            )

        if not enabled.value:
            raise RuntimeError(
                "Multi-Channel configuration "
                "was not enabled."
            )

        print()
        print(
            "[OK] Basic Multi-Channel "
            "configuration verified"
        )
        print(
            "[SAFE] Acquisition was NOT enabled"
        )

    finally:
        if connected:
            bridge.OEMPA_DisableAcquisition(handle)
            bridge.OEMPA_Disconnect(handle)

        bridge.OEMPA_Destroy(handle)


if __name__ == "__main__":
    main()