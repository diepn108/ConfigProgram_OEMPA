import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
BRIDGE_PATH = PROJECT_DIR / "bridge" / "oempa_bridge.dll"
AOS_DIR = r"C:\Program Files\AOS\OEMPA 1.1.5.4"


# DLL setup

os.add_dll_directory(AOS_DIR)

bridge = ctypes.CDLL(str(BRIDGE_PATH))


# Function prototypes

bridge.OEMPA_Create.argtypes = []
bridge.OEMPA_Create.restype = ctypes.c_void_p

bridge.OEMPA_Destroy.argtypes = [ctypes.c_void_p]
bridge.OEMPA_Destroy.restype = None

bridge.OEMPA_Connect.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ushort
]
bridge.OEMPA_Connect.restype = ctypes.c_int

bridge.OEMPA_Disconnect.argtypes = [ctypes.c_void_p]
bridge.OEMPA_Disconnect.restype = ctypes.c_int

bridge.OEMPA_GetMultiChannelSupport.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int)
]
bridge.OEMPA_GetMultiChannelSupport.restype = ctypes.c_int


# Device

IP_ADDRESS = "192.168.1.11"
PORT = 5001

handle = bridge.OEMPA_Create()

if not handle:
    raise RuntimeError("Failed to create OEM-PA device.")

try:
    if not bridge.OEMPA_Connect(handle, IP_ADDRESS, PORT):
        raise RuntimeError("Failed to connect to OEM-PA.")

    print("[OK] Connected")

    supported = ctypes.c_int()
    enabled = ctypes.c_int()

    if not bridge.OEMPA_GetMultiChannelSupport(
        handle,
        ctypes.byref(supported),
        ctypes.byref(enabled)
    ):
        raise RuntimeError(
            "Failed to query multi-channel capability."
        )

    print()
    print("Multi-Channel Capability")
    print("------------------------")
    print(
        f"Multi-channel supported: "
        f"{'YES' if supported.value else 'NO'}"
    )
    print(
        f"Multi-channel enabled:   "
        f"{'YES' if enabled.value else 'NO'}"
    )

finally:
    bridge.OEMPA_Disconnect(handle)
    bridge.OEMPA_Destroy(handle)