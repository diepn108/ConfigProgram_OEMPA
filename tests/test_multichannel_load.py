import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_DIR = PROJECT_DIR / "bridge"
AOS_DIR = Path(r"C:\Program Files\AOS\OEMPA 1.1.5.4")
CONFIG_PATH = PROJECT_DIR / "configs" / "fmc16_full.txt"


# Device

IP_ADDRESS = "192.168.1.11"
PORT = 5001
EXPECTED_CYCLES = 256


# DLL search paths

os.add_dll_directory(str(AOS_DIR))
os.add_dll_directory(str(BRIDGE_DIR))


# Load bridge

bridge = ctypes.CDLL(
    str(BRIDGE_DIR / "oempa_bridge.dll")
)


# Function signatures

bridge.OEMPA_Create.argtypes = []
bridge.OEMPA_Create.restype = ctypes.c_void_p

bridge.OEMPA_Destroy.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_Destroy.restype = None

bridge.OEMPA_Connect.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ushort,
]
bridge.OEMPA_Connect.restype = ctypes.c_int

bridge.OEMPA_Disconnect.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_Disconnect.restype = ctypes.c_int

bridge.OEMPA_LoadConfiguration.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
]
bridge.OEMPA_LoadConfiguration.restype = ctypes.c_int

bridge.OEMPA_GetCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetCycleCount.restype = ctypes.c_int

bridge.OEMPA_GetMultiChannelSupport.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetMultiChannelSupport.restype = ctypes.c_int

bridge.OEMPA_DisableAcquisition.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_DisableAcquisition.restype = ctypes.c_int


# Main

def main():
    print("AOS OEM-PA Full 16 x 16 FMC Hardware Load")
    print("------------------------------------------")
    print(f"Target: {IP_ADDRESS}:{PORT}")
    print(f"Configuration: {CONFIG_PATH}")
    print()

    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Configuration file does not exist: {CONFIG_PATH}"
        )

    handle = bridge.OEMPA_Create()

    if not handle:
        raise RuntimeError(
            "Failed to create OEM-PA bridge."
        )

    connected = False

    try:
        # Connect

        if not bridge.OEMPA_Connect(
            handle,
            IP_ADDRESS,
            PORT,
        ):
            raise RuntimeError(
                "Failed to connect to OEM-PA."
            )

        connected = True
        print("[OK] Connected")

        # Ensure acquisition is OFF

        if not bridge.OEMPA_DisableAcquisition(handle):
            raise RuntimeError(
                "Failed to disable acquisition."
            )

        print("[OK] Acquisition OFF")

        # Write configuration

        print()
        print("Writing configuration")
        print("---------------------")

        result = bridge.OEMPA_LoadConfiguration(
            handle,
            str(CONFIG_PATH),
        )

        if not result:
            raise RuntimeError(
                "Configuration write failed."
            )

        print("[OK] Configuration write reported SUCCESS")
        print("[SAFE] Acquisition remains OFF")

        # Refresh connection

        print()
        print("Refreshing device connection")
        print("----------------------------")

        print(
            "Disconnecting after configuration write..."
        )

        if not bridge.OEMPA_Disconnect(handle):
            raise RuntimeError(
                "Failed to disconnect after configuration write."
            )

        connected = False

        print(
            "[OK] Disconnected after write"
        )

        print(
            "Reconnecting..."
        )

        if not bridge.OEMPA_Connect(
            handle,
            IP_ADDRESS,
            PORT,
        ):
            raise RuntimeError(
                "Failed to reconnect to OEM-PA."
            )

        connected = True

        print("[OK] Reconnected")

        if not bridge.OEMPA_DisableAcquisition(handle):
            raise RuntimeError(
                "Failed to disable acquisition after reconnect."
            )

        print("[OK] Acquisition OFF")

        # Hardware readback

        print()
        print("Hardware Readback")
        print("-----------------")

        # Cycle count

        print(
            "Reading cycle count..."
        )

        cycle_count = ctypes.c_int(0)

        result = bridge.OEMPA_GetCycleCount(
            handle,
            ctypes.byref(cycle_count),
        )

        if not result:
            raise RuntimeError(
                "Failed to read hardware cycle count."
            )

        print(
            f"Cycle count: {cycle_count.value}"
        )

        # Multi-Channel state

        print(
            "Reading Multi-Channel state..."
        )

        supported = ctypes.c_int(0)
        enabled = ctypes.c_int(0)

        result = bridge.OEMPA_GetMultiChannelSupport(
            handle,
            ctypes.byref(supported),
            ctypes.byref(enabled),
        )

        if not result:
            raise RuntimeError(
                "Failed to read Multi-Channel state."
            )

        print(
            "Multi-channel supported: "
            + ("YES" if supported.value else "NO")
        )

        print(
            "Multi-channel enabled:   "
            + ("YES" if enabled.value else "NO")
        )

        # Verification

        print()
        print("Verification")
        print("------------")

        if cycle_count.value != EXPECTED_CYCLES:
            raise RuntimeError(
                f"Expected {EXPECTED_CYCLES} cycles, "
                f"but hardware reports {cycle_count.value}."
            )

        print(
            f"[OK] Cycle count = {EXPECTED_CYCLES}"
        )

        if not supported.value:
            raise RuntimeError(
                "Hardware reports Multi-Channel unsupported."
            )

        print(
            "[OK] Multi-Channel supported"
        )

        if not enabled.value:
            raise RuntimeError(
                "Multi-Channel is not enabled."
            )

        print(
            "[OK] Multi-Channel enabled"
        )

        print()
        print(
            "[OK] Full 16 x 16 FMC hardware "
            "configuration verification PASSED"
        )

        print()
        print(
            "[SAFE] Acquisition was NOT enabled."
        )
        print(
            "[SAFE] No ultrasonic firing was performed."
        )

    finally:
        # Always leave acquisition OFF

        if connected:
            print()
            print("Closing connection")
            print("------------------")

            try:
                bridge.OEMPA_DisableAcquisition(
                    handle
                )
                print(
                    "[OK] Acquisition OFF"
                )
            except Exception:
                pass

            try:
                bridge.OEMPA_Disconnect(
                    handle
                )
                print(
                    "[OK] Disconnected"
                )
            except Exception:
                pass

        bridge.OEMPA_Destroy(
            handle
        )


if __name__ == "__main__":
    main()