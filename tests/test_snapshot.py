from pathlib import Path
import ctypes
import os


# Paths

AOS_DIR = os.environ.get("OEMPA_AOS_RUNTIME", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "AOS", "OEMPA 1.1.5.4"))
BRIDGE_PATH = str(Path(__file__).resolve().parents[1] / "bridge" / "oempa_bridge.dll")

IP_ADDRESS = "192.168.1.11"
PORT = 5001


# Structures

class OEMPACycleSnapshot(ctypes.Structure):
    _fields_ = [
        ("cycle", ctypes.c_int),

        ("gain_digital_db", ctypes.c_double),
        ("gain_analog_db", ctypes.c_float),
        ("beam_correction_db", ctypes.c_float),

        ("start_s", ctypes.c_double),
        ("range_s", ctypes.c_double),
        ("sampling_hz", ctypes.c_double),
        ("time_slot_s", ctypes.c_double),

        ("point_count", ctypes.c_long),
        ("point_factor", ctypes.c_long),

        ("bit_size", ctypes.c_int),
        ("rectification", ctypes.c_int),
        ("compression_type", ctypes.c_int),
        ("filter_index", ctypes.c_int),

        ("tx_enabled", ctypes.c_int * 16),
        ("rx_enabled", ctypes.c_int * 16),
    ]


# DLL

os.add_dll_directory(AOS_DIR)
bridge = ctypes.CDLL(BRIDGE_PATH)

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

bridge.OEMPA_GetCycleSnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(OEMPACycleSnapshot),
]
bridge.OEMPA_GetCycleSnapshot.restype = ctypes.c_int


# Helpers

BIT_SIZE_NAMES = {
    0: "8-bit",
    1: "12-bit",
    2: "16-bit",
    3: "Log 8-bit",
}

RECTIFICATION_NAMES = {
    0: "Signed",
    1: "Unsigned",
    2: "Unsigned Positive",
    3: "Unsigned Negative",
}

COMPRESSION_NAMES = {
    0: "Compression",
    1: "Decimation",
}


# Test

handle = bridge.OEMPA_Create()

if not handle:
    raise RuntimeError("Failed to create OEM-PA device")

try:
    if not bridge.OEMPA_Connect(
        handle,
        IP_ADDRESS,
        PORT,
    ):
        raise RuntimeError("Failed to connect")

    print("[OK] Connected")

    snapshot = OEMPACycleSnapshot()

    if not bridge.OEMPA_GetCycleSnapshot(
        handle,
        0,
        ctypes.byref(snapshot),
    ):
        raise RuntimeError(
            "Failed to read Cycle 0 snapshot"
        )

    tx = [
        i
        for i, enabled in enumerate(snapshot.tx_enabled)
        if enabled
    ]

    rx = [
        i
        for i, enabled in enumerate(snapshot.rx_enabled)
        if enabled
    ]

    print()
    print("Cycle 0 Snapshot")
    print("----------------")
    print(f"Digital gain:      {snapshot.gain_digital_db:.2f} dB")
    print(f"Analog gain:       {snapshot.gain_analog_db:.2f} dB")
    print(f"Beam correction:   {snapshot.beam_correction_db:.2f} dB")
    print(f"Start:             {snapshot.start_s * 1e6:.3f} us")
    print(f"Range:             {snapshot.range_s * 1e6:.3f} us")
    print(f"Sampling rate:     {snapshot.sampling_hz / 1e6:.3f} MHz")
    print(f"Time slot:         {snapshot.time_slot_s * 1e6:.3f} us")
    print(f"Point count:       {snapshot.point_count}")
    print(f"Point factor:      {snapshot.point_factor}")

    print(
        f"Bit size:          "
        f"{BIT_SIZE_NAMES.get(snapshot.bit_size, snapshot.bit_size)}"
    )

    print(
        f"Rectification:     "
        f"{RECTIFICATION_NAMES.get(snapshot.rectification, snapshot.rectification)}"
    )

    print(
        f"Compression:       "
        f"{COMPRESSION_NAMES.get(snapshot.compression_type, snapshot.compression_type)}"
    )

    print(f"Filter index:      {snapshot.filter_index}")
    print(f"TX enabled:        {tx}")
    print(f"RX enabled:        {rx}")

finally:
    bridge.OEMPA_Disconnect(handle)
    bridge.OEMPA_Destroy(handle)