import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_DIR = PROJECT_DIR / "bridge"
CONFIG_PATH = PROJECT_DIR / "configs" / "fmc16_full.txt"
AOS_DIR = Path(r"C:\Program Files\AOS\OEMPA 1.1.5.4")


# DLL search paths

os.add_dll_directory(str(AOS_DIR))
os.add_dll_directory(str(BRIDGE_DIR))


# Load bridge

bridge = ctypes.CDLL(str(BRIDGE_DIR / "oempa_bridge.dll"))


# Function signatures

bridge.OEMPA_ParseConfiguration.argtypes = [
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]

bridge.OEMPA_ParseConfiguration.restype = ctypes.c_int


# Parse configuration

def main():
    print("AOS OEM-PA Configuration Parse Test")
    print("-----------------------------------")
    print(f"Configuration: {CONFIG_PATH}")
    print()

    if not CONFIG_PATH.exists():
        print("[FAIL] Configuration file does not exist.")
        return

    cycle_count = ctypes.c_int(-1)
    multi_channel_enabled = ctypes.c_int(0)

    result = bridge.OEMPA_ParseConfiguration(
        str(CONFIG_PATH),
        ctypes.byref(cycle_count),
        ctypes.byref(multi_channel_enabled),
    )

    print("Parse Result")
    print("------------")

    if not result:
        print("Parse:                 FAILED")
        print(f"Cycle count:           {cycle_count.value}")
        print()
        print("[STOP] AOS could not parse the configuration.")
        print("[SAFE] No hardware connection or hardware write was performed.")
        return

    print("Parse:                 SUCCESS")
    print(f"Cycle count:           {cycle_count.value}")
    print(
        "Multi-channel enabled: "
        + ("YES" if multi_channel_enabled.value else "NO")
    )

    print()
    print("[OK] Configuration parsed successfully.")
    print("[SAFE] No hardware connection or hardware write was performed.")


if __name__ == "__main__":
    main()