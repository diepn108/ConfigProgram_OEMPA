from pathlib import Path
import ctypes
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np


# Paths

AOS_DIR = os.environ.get("OEMPA_AOS_RUNTIME", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "AOS", "OEMPA 1.1.5.4"))

BRIDGE_PATH = str(Path(__file__).resolve().parents[1] / "bridge" / "oempa_bridge.dll")

IP_ADDRESS = "192.168.1.11"
PORT = 5001


# DLL loading

os.add_dll_directory(AOS_DIR)

bridge = ctypes.CDLL(BRIDGE_PATH)


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

bridge.OEMPA_Disconnect.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_Disconnect.restype = ctypes.c_int

bridge.OEMPA_StartAscan.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_StartAscan.restype = ctypes.c_int

bridge.OEMPA_EnableAcquisition.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_EnableAcquisition.restype = ctypes.c_int

bridge.OEMPA_DisableAcquisition.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_DisableAcquisition.restype = ctypes.c_int

bridge.OEMPA_HasAscan.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_HasAscan.restype = ctypes.c_int

bridge.OEMPA_GetAscanInfo.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetAscanInfo.restype = ctypes.c_int

bridge.OEMPA_CopyAscan.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
]
bridge.OEMPA_CopyAscan.restype = ctypes.c_int


# Create device

print("AOS OEM-PA A-scan Test")
print(f"Target: {IP_ADDRESS}:{PORT}")
print()

handle = bridge.OEMPA_Create()

if not handle:
    raise RuntimeError("Failed to create OEM-PA device")


try:
    # Register callback before connection

    if not bridge.OEMPA_StartAscan(handle):
        raise RuntimeError("Failed to register A-scan callback")

    print("[OK] A-scan callback registered")

    # Connect

    if not bridge.OEMPA_Connect(
        handle,
        IP_ADDRESS,
        PORT,
    ):
        raise RuntimeError("Failed to connect")

    print("[OK] Connected")

    # Enable acquisition

    if not bridge.OEMPA_EnableAcquisition(handle):
        raise RuntimeError("Failed to enable acquisition")

    print("[OK] Acquisition enabled")

    # Wait for A-scan

    timeout = 5.0
    start_time = time.time()

    while not bridge.OEMPA_HasAscan(handle):
        if time.time() - start_time > timeout:
            raise TimeoutError(
                "No A-scan received within 5 seconds"
            )

        time.sleep(0.01)

    print("[OK] A-scan received")

    # Read metadata

    cycle = ctypes.c_int()
    point_count = ctypes.c_int()
    data_size = ctypes.c_int()
    is_signed = ctypes.c_int()
    bit_size = ctypes.c_int()

    if not bridge.OEMPA_GetAscanInfo(
        handle,
        ctypes.byref(cycle),
        ctypes.byref(point_count),
        ctypes.byref(data_size),
        ctypes.byref(is_signed),
        ctypes.byref(bit_size),
    ):
        raise RuntimeError("Failed to read A-scan information")

    print()
    print("A-scan information")
    print("------------------")
    print(f"Cycle:       {cycle.value}")
    print(f"Point count: {point_count.value}")
    print(f"Data size:   {data_size.value} byte(s)")
    print(f"Signed:      {bool(is_signed.value)}")
    print(f"Bit size:    {bit_size.value}")

    # Allocate raw buffer

    byte_count = point_count.value * data_size.value

    raw_buffer = (
        ctypes.c_ubyte * byte_count
    )()

    copied = bridge.OEMPA_CopyAscan(
        handle,
        raw_buffer,
        byte_count,
    )

    if copied <= 0:
        raise RuntimeError(
            f"Failed to copy A-scan data: {copied}"
        )

    print(f"Bytes copied: {copied}")

    # Convert to NumPy

    raw = np.ctypeslib.as_array(raw_buffer).copy()

    if data_size.value == 1:
        dtype = np.int8 if is_signed.value else np.uint8

    elif data_size.value == 2:
        dtype = np.int16 if is_signed.value else np.uint16

    else:
        raise RuntimeError(
            f"Unsupported sample size: "
            f"{data_size.value} bytes"
        )

    waveform = raw.view(dtype)

    waveform = waveform[:point_count.value]

    print(f"NumPy shape: {waveform.shape}")
    print(f"Minimum:     {waveform.min()}")
    print(f"Maximum:     {waveform.max()}")

finally:
    # Always stop acquisition

    try:
        bridge.OEMPA_DisableAcquisition(handle)
    except Exception:
        pass

    # Disconnect

    try:
        bridge.OEMPA_Disconnect(handle)
    except Exception:
        pass

    bridge.OEMPA_Destroy(handle)


# Plot

plt.figure(figsize=(10, 5))

plt.plot(waveform)

plt.xlabel("Sample")
plt.ylabel("Amplitude")
plt.title(
    f"OEM-PA A-scan - Cycle {cycle.value}"
)

plt.grid(True)

plt.tight_layout()
plt.show()