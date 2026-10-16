import ctypes
import os
import time
from pathlib import Path

import numpy as np


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]

BRIDGE_PATH = (
    PROJECT_DIR
    / "bridge"
    / "oempa_bridge.dll"
)

OUTPUT_PATH = (
    PROJECT_DIR
    / "data"
    / "fmc16x16.npy"
)


# Device

IP_ADDRESS = "192.168.1.11"
PORT = 5001

TX_COUNT = 16
RX_COUNT = 16
EXPECTED_CYCLES = TX_COUNT * RX_COUNT

TIMEOUT_S = 5.0
POLL_INTERVAL_S = 0.02


# Load AOS runtime

AOS_RUNTIME = Path(
    r"C:\Program Files\AOS\OEMPA 1.1.5.4"
)

if not AOS_RUNTIME.exists():
    raise FileNotFoundError(
        f"AOS runtime directory not found: {AOS_RUNTIME}"
    )

aos_dll_directory = os.add_dll_directory(
    str(AOS_RUNTIME)
)


# Load bridge

dll = ctypes.CDLL(
    str(BRIDGE_PATH)
)


# Function definitions

dll.OEMPA_Create.argtypes = []
dll.OEMPA_Create.restype = ctypes.c_void_p

dll.OEMPA_Destroy.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_Destroy.restype = None

dll.OEMPA_Connect.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ushort,
]
dll.OEMPA_Connect.restype = ctypes.c_int

dll.OEMPA_Disconnect.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_Disconnect.restype = ctypes.c_int

dll.OEMPA_GetMultiChannelSupport.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
dll.OEMPA_GetMultiChannelSupport.restype = ctypes.c_int

dll.OEMPA_SetMultiAscanCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]
dll.OEMPA_SetMultiAscanCycleCount.restype = ctypes.c_int

dll.OEMPA_StartAscan.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_StartAscan.restype = ctypes.c_int

dll.OEMPA_ClearMultiAscan.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_ClearMultiAscan.restype = ctypes.c_int

dll.OEMPA_GetMultiAscanCount.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_GetMultiAscanCount.restype = ctypes.c_int

dll.OEMPA_HasMultiAscanCycle.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]
dll.OEMPA_HasMultiAscanCycle.restype = ctypes.c_int

dll.OEMPA_GetMultiAscanInfo.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
dll.OEMPA_GetMultiAscanInfo.restype = ctypes.c_int

dll.OEMPA_CopyMultiAscan.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_int,
]
dll.OEMPA_CopyMultiAscan.restype = ctypes.c_int

dll.OEMPA_EnableAcquisition.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_EnableAcquisition.restype = ctypes.c_int

dll.OEMPA_DisableAcquisition.argtypes = [
    ctypes.c_void_p,
]
dll.OEMPA_DisableAcquisition.restype = ctypes.c_int


# Read one stored A-scan

def read_cycle(handle, cycle):
    point_count = ctypes.c_int()
    data_size = ctypes.c_int()
    is_signed = ctypes.c_int()
    bit_size = ctypes.c_int()

    ok = dll.OEMPA_GetMultiAscanInfo(
        handle,
        cycle,
        ctypes.byref(point_count),
        ctypes.byref(data_size),
        ctypes.byref(is_signed),
        ctypes.byref(bit_size),
    )

    if not ok:
        raise RuntimeError(
            f"Could not read A-scan information for cycle {cycle}"
        )

    byte_count = point_count.value * data_size.value

    if byte_count <= 0:
        raise RuntimeError(
            f"Invalid byte count for cycle {cycle}: {byte_count}"
        )

    buffer = (ctypes.c_ubyte * byte_count)()

    copied = dll.OEMPA_CopyMultiAscan(
        handle,
        cycle,
        buffer,
        byte_count,
    )

    if copied != byte_count:
        raise RuntimeError(
            f"Cycle {cycle}: expected {byte_count} bytes, "
            f"but copied {copied}"
        )

    raw = bytes(buffer)

    if data_size.value == 1:
        dtype = np.int8 if is_signed.value else np.uint8

    elif data_size.value == 2:
        dtype = np.int16 if is_signed.value else np.uint16

    else:
        raise RuntimeError(
            f"Unsupported data size: {data_size.value} bytes"
        )

    scan = np.frombuffer(
        raw,
        dtype=dtype,
    ).copy()

    return (
        scan,
        point_count.value,
        data_size.value,
        is_signed.value,
        bit_size.value,
    )


# Main acquisition

def main():
    print("AOS OEM-PA 2 TX x 16 RX Acquisition")
    print("----------------------------------")
    print(f"Target: {IP_ADDRESS}:{PORT}")
    print(f"Expected cycles: {EXPECTED_CYCLES}")
    print()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = dll.OEMPA_Create()

    if not handle:
        raise RuntimeError(
            "OEMPA_Create failed"
        )

    connected = False
    acquisition_enabled = False

    try:
        # Connect

        if not dll.OEMPA_Connect(
            handle,
            IP_ADDRESS,
            PORT,
        ):
            raise RuntimeError(
                "Failed to connect to OEM-PA"
            )

        connected = True

        print("[OK] Connected")

        # Check Multi-Channel mode

        supported = ctypes.c_int()
        enabled = ctypes.c_int()

        if not dll.OEMPA_GetMultiChannelSupport(
            handle,
            ctypes.byref(supported),
            ctypes.byref(enabled),
        ):
            raise RuntimeError(
                "Could not read Multi-Channel status"
            )

        print(
            "Multi-channel supported:",
            "YES" if supported.value else "NO",
        )

        print(
            "Multi-channel enabled:",
            "YES" if enabled.value else "NO",
        )

        if not supported.value:
            raise RuntimeError(
                "Multi-Channel is not supported"
            )

        if not enabled.value:
            raise RuntimeError(
                "Multi-Channel is not enabled"
            )

        # Allocate storage for all 32 cycles

        if not dll.OEMPA_SetMultiAscanCycleCount(
            handle,
            EXPECTED_CYCLES,
        ):
            raise RuntimeError(
                "Failed to allocate Multi-A-scan storage"
            )

        print(
            f"[OK] Multi-A-scan storage: "
            f"{EXPECTED_CYCLES} cycles"
        )

        # Register callback

        if not dll.OEMPA_StartAscan(
            handle
        ):
            raise RuntimeError(
                "Failed to register A-scan callback"
            )

        print(
            "[OK] A-scan callback registered"
        )

        # Make sure acquisition is OFF

        if not dll.OEMPA_DisableAcquisition(
            handle
        ):
            raise RuntimeError(
                "Failed to disable acquisition"
            )

        print("[OK] Acquisition OFF")

        # Clear previous callback data

        if not dll.OEMPA_ClearMultiAscan(
            handle
        ):
            raise RuntimeError(
                "Failed to clear Multi-A-scan buffers"
            )

        print(
            "[OK] Multi-Channel buffers cleared"
        )

        print()

        # Enable acquisition

        if not dll.OEMPA_EnableAcquisition(
            handle
        ):
            raise RuntimeError(
                "Failed to enable acquisition"
            )

        acquisition_enabled = True

        print("[ON] Acquisition enabled")

        # Wait for all 32 unique cycles

        start_time = time.monotonic()
        last_count = -1

        while True:
            count = dll.OEMPA_GetMultiAscanCount(
                handle
            )

            if count != last_count:
                print(
                    f"A-scans received: "
                    f"{count}/{EXPECTED_CYCLES}"
                )

                last_count = count

            if count >= EXPECTED_CYCLES:
                break

            if (
                time.monotonic() - start_time
                > TIMEOUT_S
            ):
                break

            time.sleep(
                POLL_INTERVAL_S
            )

        # Stop acquisition immediately

        if not dll.OEMPA_DisableAcquisition(
            handle
        ):
            raise RuntimeError(
                "Failed to disable acquisition"
            )

        acquisition_enabled = False

        print(
            "[OFF] Acquisition disabled"
        )

        print()

        # Determine which cycles arrived

        received_cycles = []

        for cycle in range(
            EXPECTED_CYCLES
        ):
            if dll.OEMPA_HasMultiAscanCycle(
                handle,
                cycle,
            ):
                received_cycles.append(
                    cycle
                )

        print(
            f"Unique cycles received: "
            f"{len(received_cycles)}/"
            f"{EXPECTED_CYCLES}"
        )

        print(
            "Cycles:",
            received_cycles,
        )

        if len(received_cycles) != EXPECTED_CYCLES:
            missing = sorted(
                set(range(EXPECTED_CYCLES))
                - set(received_cycles)
            )

            raise RuntimeError(
                f"Missing cycles: {missing}"
            )

        # Read all A-scans in cycle order

        scans = []

        reference_point_count = None
        reference_data_size = None
        reference_signed = None
        reference_bit_size = None

        for cycle in range(
            EXPECTED_CYCLES
        ):
            (
                scan,
                point_count,
                data_size,
                is_signed,
                bit_size,
            ) = read_cycle(
                handle,
                cycle,
            )

            if reference_point_count is None:
                reference_point_count = (
                    point_count
                )
                reference_data_size = (
                    data_size
                )
                reference_signed = (
                    is_signed
                )
                reference_bit_size = (
                    bit_size
                )

            if (
                point_count
                != reference_point_count
            ):
                raise RuntimeError(
                    f"Cycle {cycle} has "
                    f"{point_count} points; "
                    f"expected "
                    f"{reference_point_count}"
                )

            scans.append(
                scan
            )

        # Cycle-major raw matrix

        raw = np.stack(
            scans,
            axis=0,
        )

        print()
        print(
            f"Raw shape: {raw.shape}"
        )

        # cycle = TX * 16 + RX

        fmc = raw.reshape(
            TX_COUNT,
            RX_COUNT,
            raw.shape[1],
        )

        print(
            f"FMC partial shape: "
            f"{fmc.shape}"
        )

        print(
            "Samples/A-scan:",
            reference_point_count,
        )

        print(
            "Data size:",
            reference_data_size,
            "byte(s)",
        )

        print(
            "Signed:",
            bool(reference_signed),
        )

        print(
            "Bit size enum:",
            reference_bit_size,
        )

        print(
            "Minimum:",
            int(fmc.min()),
        )

        print(
            "Maximum:",
            int(fmc.max()),
        )

        # Save partial FMC

        np.save(
            OUTPUT_PATH,
            fmc,
        )

        print()
        print("Saved:")
        print(OUTPUT_PATH)

        print()
        print(
            "[OK] 2 TX x 16 RX "
            "acquisition complete"
        )

    finally:
        # Safety: acquisition OFF before disconnect

        if handle:
            if acquisition_enabled:
                try:
                    dll.OEMPA_DisableAcquisition(
                        handle
                    )
                except Exception:
                    pass

            if connected:
                try:
                    dll.OEMPA_Disconnect(
                        handle
                    )

                    print(
                        "[OK] Disconnected"
                    )

                except Exception:
                    pass

            dll.OEMPA_Destroy(
                handle
            )


if __name__ == "__main__":
    main()