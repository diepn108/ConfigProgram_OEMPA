import ctypes
import os
from pathlib import Path

# Paths
aos_dir = Path(r"C:\Program Files\AOS\OEMPA 1.1.5.4")
bridge_path = Path(__file__).resolve().parents[1] / "bridge" / "oempa_bridge.dll"

# OEM-PA network
ip_address = "192.168.1.11"
port = 5001

# Load AOS runtime dependencies
os.add_dll_directory(str(aos_dir))

# Load bridge
bridge = ctypes.CDLL(str(bridge_path))

# Function definitions
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

bridge.OEMPA_IsConnected.argtypes = [ctypes.c_void_p]
bridge.OEMPA_IsConnected.restype = ctypes.c_int

bridge.OEMPA_GetCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetCycleCount.restype = ctypes.c_int

bridge.OEMPA_GetFirmwareId.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_ushort),
]
bridge.OEMPA_GetFirmwareId.restype = ctypes.c_int

bridge.OEMPA_GetElementCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetElementCount.restype = ctypes.c_int

bridge.OEMPA_GetApertureCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetApertureCount.restype = ctypes.c_int

# Create device
device = bridge.OEMPA_Create()

if not device:
    raise RuntimeError("Failed to create OEM-PA device object.")

try:
    print("AOS OEM-PA Connection Test")
    print(f"Target: {ip_address}:{port}")
    print()

    # Connect
    if not bridge.OEMPA_Connect(device, ip_address, port):
        raise RuntimeError("Failed to connect to OEM-PA.")

    print("[OK] Connected")

    if not bridge.OEMPA_IsConnected(device):
        raise RuntimeError("OEM-PA did not report a connected state.")

    print("[OK] Connection state confirmed")

    # Read cycle count
    cycle_count = ctypes.c_int()

    if bridge.OEMPA_GetCycleCount(device, ctypes.byref(cycle_count)):
        print(f"Cycle count: {cycle_count.value}")
    else:
        print("[ERROR] Could not read cycle count")

    # Read firmware ID
    firmware_id = ctypes.c_ushort()

    if bridge.OEMPA_GetFirmwareId(device, ctypes.byref(firmware_id)):
        print(f"Firmware ID: 0x{firmware_id.value:04X}")
    else:
        print("[ERROR] Could not read firmware ID")

    # Read element count
    element_count = ctypes.c_int()

    if bridge.OEMPA_GetElementCount(device, ctypes.byref(element_count)):
        print(f"Element count: {element_count.value}")
    else:
        print("[ERROR] Could not read element count")

    # Read aperture count
    aperture_count = ctypes.c_int()

    if bridge.OEMPA_GetApertureCount(device, ctypes.byref(aperture_count)):
        print(f"Aperture count: {aperture_count.value}")
    else:
        print("[ERROR] Could not read aperture count")

finally:
    # Disconnect
    if device:
        if bridge.OEMPA_IsConnected(device):
            if bridge.OEMPA_Disconnect(device):
                print("[OK] Disconnected")
            else:
                print("[WARNING] Disconnect failed")

        bridge.OEMPA_Destroy(device)