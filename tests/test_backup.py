import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_DIR = PROJECT_DIR / "bridge"
AOS_DIR = Path(r"C:\Program Files\AOS\OEMPA 1.1.5.4")
BACKUP_PATH = PROJECT_DIR / "configs" / "backup_original.txt"


# DLL search paths

os.add_dll_directory(str(AOS_DIR))
os.add_dll_directory(str(BRIDGE_DIR))


# Load bridge

bridge = ctypes.CDLL(str(BRIDGE_DIR / "oempa_bridge.dll"))


# Function signatures

bridge.OEMPA_Create.argtypes = []
bridge.OEMPA_Create.restype = ctypes.c_void_p

bridge.OEMPA_Destroy.argtypes = [ctypes.c_void_p]
bridge.OEMPA_Destroy.restype = None

bridge.OEMPA_Connect.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ushort,
]
bridge.OEMPA_Connect.restype = ctypes.c_int

bridge.OEMPA_Disconnect.argtypes = [ctypes.c_void_p]
bridge.OEMPA_Disconnect.restype = ctypes.c_int

bridge.OEMPA_BackupConfiguration.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
]
bridge.OEMPA_BackupConfiguration.restype = ctypes.c_int


# Backup

def main():
    print("AOS OEM-PA Configuration Backup")
    print("-------------------------------")
    print(f"Target: 192.168.1.11:5001")
    print(f"Backup: {BACKUP_PATH}")
    print()

    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

    handle = bridge.OEMPA_Create()

    if not handle:
        raise RuntimeError("Failed to create OEM-PA bridge.")

    connected = False

    try:
        if not bridge.OEMPA_Connect(
            handle,
            "192.168.1.11",
            5001,
        ):
            raise RuntimeError("Failed to connect to OEM-PA.")

        connected = True
        print("[OK] Connected")

        if not bridge.OEMPA_BackupConfiguration(
            handle,
            str(BACKUP_PATH),
        ):
            raise RuntimeError(
                "Failed to read hardware configuration."
            )

        if not BACKUP_PATH.exists():
            raise RuntimeError(
                "AOS reported success but backup file was not created."
            )

        print("[OK] Hardware configuration read successfully")
        print("[OK] Backup file created")
        print()
        print(f"Saved to:")
        print(BACKUP_PATH)
        print()
        print("[SAFE] Acquisition was not enabled.")

    finally:
        if connected:
            bridge.OEMPA_Disconnect(handle)
            print("[OK] Disconnected")

        bridge.OEMPA_Destroy(handle)


if __name__ == "__main__":
    main()