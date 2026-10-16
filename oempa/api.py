import ctypes
import os
from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parent.parent
BRIDGE_DIR = PROJECT_DIR / "bridge"
BRIDGE_PATH = BRIDGE_DIR / "oempa_bridge.dll"

AOS_DIR = Path(os.environ.get("OEMPA_AOS_RUNTIME", str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "AOS" / "OEMPA 1.1.5.4")))


# DLL search paths

if not AOS_DIR.exists():
    raise FileNotFoundError(
        f"AOS runtime directory not found: {AOS_DIR}"
    )

if not BRIDGE_PATH.exists():
    raise FileNotFoundError(
        f"OEM-PA bridge DLL not found: {BRIDGE_PATH}"
    )

_aos_dll_directory = os.add_dll_directory(
    str(AOS_DIR)
)

_bridge_dll_directory = os.add_dll_directory(
    str(BRIDGE_DIR)
)


# Load bridge

bridge = ctypes.CDLL(
    str(BRIDGE_PATH)
)

CALLBACK_BUFFER_COUNT = 3
CALLBACK_WINDOW_COUNT = 6
CALLBACK_WINDOW_BYTE_CAPACITY = 202


class OEMPAAscanBufferDiagnostic(ctypes.Structure):
    _fields_ = [
        ("validity_flag", ctypes.c_int),
        ("pointer_nonnull", ctypes.c_int),
        ("analyzed", ctypes.c_int),
        ("min_max_valid", ctypes.c_int),
        ("sample_193_to_end_all_zero", ctypes.c_int),
        ("first_nonzero_index", ctypes.c_int),
        ("last_nonzero_index", ctypes.c_int),
        ("nonzero_sample_count", ctypes.c_ulonglong),
        ("exact_zero_sample_count", ctypes.c_ulonglong),
        ("terminal_zero_sample_count", ctypes.c_int),
        ("minimum_value", ctypes.c_int),
        ("maximum_value", ctypes.c_int),
        ("saturation_lsb_set_count", ctypes.c_ulonglong),
        ("window_start_indices", ctypes.c_int * CALLBACK_WINDOW_COUNT),
        ("window_sample_counts", ctypes.c_int * CALLBACK_WINDOW_COUNT),
        ("window_byte_counts", ctypes.c_int * CALLBACK_WINDOW_COUNT),
        ("window_truncated", ctypes.c_int * CALLBACK_WINDOW_COUNT),
        ("window_bytes", (ctypes.c_ubyte * CALLBACK_WINDOW_BYTE_CAPACITY) * CALLBACK_WINDOW_COUNT),
    ]


class OEMPAAscanCallbackDiagnostic(ctypes.Structure):
    _fields_ = [
        ("cycle", ctypes.c_int),
        ("data_count", ctypes.c_int),
        ("data_size", ctypes.c_int),
        ("is_signed", ctypes.c_int),
        ("bit_size", ctypes.c_int),
        ("expected_byte_count", ctypes.c_ulonglong),
        ("max_flag", ctypes.c_int),
        ("min_flag", ctypes.c_int),
        ("sat_flag", ctypes.c_int),
        ("max_pointer_nonnull", ctypes.c_int),
        ("min_pointer_nonnull", ctypes.c_int),
        ("sat_pointer_nonnull", ctypes.c_int),
        ("bridge_copy_capacity_ok", ctypes.c_int),
        ("buffers", OEMPAAscanBufferDiagnostic * CALLBACK_BUFFER_COUNT),
    ]


# Device lifecycle

bridge.OEMPA_Create.argtypes = []
bridge.OEMPA_Create.restype = ctypes.c_void_p

bridge.OEMPA_Destroy.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_Destroy.restype = None


# Connection

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


# Device information

bridge.OEMPA_GetCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetCycleCount.restype = ctypes.c_int

bridge.OEMPA_GetPulserPowerSnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
bridge.OEMPA_GetPulserPowerSnapshot.restype = ctypes.c_int

bridge.OEMPA_GetMultiChannelSupport.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetMultiChannelSupport.restype = ctypes.c_int


# Configuration

bridge.OEMPA_LoadConfiguration.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
]
bridge.OEMPA_LoadConfiguration.restype = ctypes.c_int

bridge.OEMPA_ParseConfiguration.argtypes = [
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_ParseConfiguration.restype = ctypes.c_int


# Cycle snapshot

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


bridge.OEMPA_GetCycleSnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(OEMPACycleSnapshot),
]
bridge.OEMPA_GetCycleSnapshot.restype = ctypes.c_int


# A-scan configuration hardware readback

bridge.OEMPA_GetAscanConfigSnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetAscanConfigSnapshot.restype = ctypes.c_int


# PA receive-path hardware readback

bridge.OEMPA_GetPAReceiveSnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
bridge.OEMPA_GetPAReceiveSnapshot.restype = ctypes.c_int


# PA focal-law hardware readback

bridge.OEMPA_GetPADelaySnapshot.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetPADelaySnapshot.restype = ctypes.c_int


# PA focal-law setter diagnostic

bridge.OEMPA_TestPAFocalLawSetters.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_int,
]
bridge.OEMPA_TestPAFocalLawSetters.restype = ctypes.c_int


# A-scan callback

bridge.OEMPA_StartAscan.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_StartAscan.restype = ctypes.c_int

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

bridge.OEMPA_PrepareAscanCallbackBuffers.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]
bridge.OEMPA_PrepareAscanCallbackBuffers.restype = ctypes.c_int

bridge.OEMPA_GetAscanCallbackDiagnostic.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(OEMPAAscanCallbackDiagnostic),
]
bridge.OEMPA_GetAscanCallbackDiagnostic.restype = ctypes.c_int


# Multi-A-scan storage

bridge.OEMPA_SetMultiAscanCycleCount.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]
bridge.OEMPA_SetMultiAscanCycleCount.restype = ctypes.c_int

bridge.OEMPA_ClearMultiAscan.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_ClearMultiAscan.restype = ctypes.c_int

bridge.OEMPA_GetMultiAscanCount.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_GetMultiAscanCount.restype = ctypes.c_int

bridge.OEMPA_HasMultiAscanCycle.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]
bridge.OEMPA_HasMultiAscanCycle.restype = ctypes.c_int

bridge.OEMPA_GetMultiAscanInfo.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]
bridge.OEMPA_GetMultiAscanInfo.restype = ctypes.c_int

bridge.OEMPA_CopyMultiAscan.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_int,
]
bridge.OEMPA_CopyMultiAscan.restype = ctypes.c_int


# Acquisition control

bridge.OEMPA_EnableAcquisition.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_EnableAcquisition.restype = ctypes.c_int

bridge.OEMPA_DisableAcquisition.argtypes = [
    ctypes.c_void_p,
]
bridge.OEMPA_DisableAcquisition.restype = ctypes.c_int


# Helper functions

def create_handle():
    handle = bridge.OEMPA_Create()

    if not handle:
        raise RuntimeError(
            "Failed to create OEM-PA bridge handle."
        )

    return handle


def destroy_handle(handle):
    if handle:
        bridge.OEMPA_Destroy(
            handle
        )


def connect(
    handle,
    ip_address,
    port,
):
    result = bridge.OEMPA_Connect(
        handle,
        str(ip_address),
        int(port),
    )

    if not result:
        raise RuntimeError(
            f"Failed to connect to OEM-PA at "
            f"{ip_address}:{port}."
        )


def disconnect(handle):
    if not bridge.OEMPA_Disconnect(
        handle
    ):
        raise RuntimeError(
            "Failed to disconnect from OEM-PA."
        )


def disable_acquisition(handle):
    if not bridge.OEMPA_DisableAcquisition(
        handle
    ):
        raise RuntimeError(
            "Failed to disable acquisition."
        )


def enable_acquisition(handle):
    if not bridge.OEMPA_EnableAcquisition(
        handle
    ):
        raise RuntimeError(
            "Failed to enable acquisition."
        )


def get_cycle_count(handle):
    cycle_count = ctypes.c_int()

    result = bridge.OEMPA_GetCycleCount(
        handle,
        ctypes.byref(cycle_count),
    )

    if not result:
        raise RuntimeError(
            "Failed to read cycle count."
        )

    return cycle_count.value


def get_pulser_power_snapshot(handle):
    max_power_w = ctypes.c_double()
    current_power_w = ctypes.c_double()

    result = bridge.OEMPA_GetPulserPowerSnapshot(
        handle,
        ctypes.byref(max_power_w),
        ctypes.byref(current_power_w),
    )

    if not result:
        raise RuntimeError("Failed to read pulser-power snapshot.")

    return {
        "max_power_w": max_power_w.value,
        "current_power_w": current_power_w.value,
    }


def get_multichannel_state(handle):
    supported = ctypes.c_int()
    enabled = ctypes.c_int()

    result = bridge.OEMPA_GetMultiChannelSupport(
        handle,
        ctypes.byref(supported),
        ctypes.byref(enabled),
    )

    if not result:
        raise RuntimeError(
            "Failed to read Multi-Channel state."
        )

    return {
        "supported": bool(supported.value),
        "enabled": bool(enabled.value),
    }


def load_configuration(
    handle,
    file_path,
):
    file_path = Path(
        file_path
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: "
            f"{file_path}"
        )

    result = bridge.OEMPA_LoadConfiguration(
        handle,
        str(file_path),
    )

    if not result:
        raise RuntimeError(
            "Failed to load OEM-PA configuration."
        )


def parse_configuration(
    file_path,
):
    file_path = Path(
        file_path
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: "
            f"{file_path}"
        )

    cycle_count = ctypes.c_int(
        -1
    )

    multi_channel_enabled = ctypes.c_int(
        0
    )

    result = bridge.OEMPA_ParseConfiguration(
        str(file_path),
        ctypes.byref(
            cycle_count
        ),
        ctypes.byref(
            multi_channel_enabled
        ),
    )

    if not result:
        raise RuntimeError(
            "AOS OEMPA_ReadFileText failed "
            "to parse the configuration."
        )

    return {
        "cycle_count": cycle_count.value,
        "multi_channel_enabled": bool(
            multi_channel_enabled.value
        ),
    }


def get_configuration_diagnostic():
    values = [ctypes.c_int() for _ in range(5)]
    result = bridge.OEMPA_GetConfigurationDiagnostic(
        *[ctypes.byref(value) for value in values]
    )
    if not result:
        raise RuntimeError("Failed to read configuration diagnostic.")
    return {
        "entered": bool(values[0].value),
        "before_hw": bool(values[1].value),
        "after_hw": bool(values[2].value),
        "left": bool(values[3].value),
        "parsed_cycle_count": values[4].value,
    }


class OEMPAExtendedCycleSnapshot(ctypes.Structure):
    _fields_ = [
        ("width_count", ctypes.c_int), ("widths_s", ctypes.c_float * 16),
        ("tx_delay_count", ctypes.c_int), ("tx_delays_s", ctypes.c_float * 16),
        ("hw_acquisition", ctypes.c_int), ("start_count", ctypes.c_int),
        ("multi_starts_s", ctypes.c_float * 16), ("multi_decimation_bytes", ctypes.c_ubyte * 8),
    ]


def get_multihw_cycle_diagnostic(handle, cycle, initial_state=False):
    """Keep SDK call success separate from its bool output; never writes configuration."""
    function = bridge.OEMPA_GetMultiHWChannelCycleDiagnostic
    function.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int] + [ctypes.POINTER(ctypes.c_int)] * 3
    function.restype = ctypes.c_int
    values = [ctypes.c_int(-1) for _ in range(3)]
    if not function(handle, int(cycle), int(bool(initial_state)), *(ctypes.byref(value) for value in values)):
        raise RuntimeError("MultiHWChannel diagnostic could not complete.")
    if any(value.value not in (0, 1) for value in values):
        raise RuntimeError("Invalid MultiHWChannel diagnostic output.")
    return dict(zip(("getter_success", "acquisition_state", "unlock_success"), (bool(value.value) for value in values)))


def get_emission_getter_diagnostic(handle, cycle, getter, capacity=16, count_seed=0, seed_variant=0):
    """Return raw seeded observations, never inferred TX state or verification."""
    if getter not in (0, 1, 2) or capacity not in (16, 64) or not 0 <= count_seed <= capacity or seed_variant not in (0, 1):
        raise ValueError("Invalid emission diagnostic arguments.")
    function = bridge.OEMPA_GetEmissionGetterDiagnostic
    floats = ctypes.c_float * 64
    words = ctypes.c_uint32 * 4
    seed = floats(*(0.00000025 + seed_variant * 0.0000001 + index * 0.000000004 for index in range(64)))
    aperture = words(0 if seed_variant == 0 else 65535, 0, 0, 0)
    values_call, values_unlock = floats(), floats()
    aperture_call, aperture_unlock = words(), words()
    observations = (ctypes.c_int * 6)(*([-1] * 6))
    function.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_int)] + [ctypes.POINTER(ctypes.c_float)] * 2 + [ctypes.POINTER(ctypes.c_uint32)] * 2
    function.restype = ctypes.c_int
    if not function(handle, cycle, getter, capacity, count_seed, seed, aperture, observations, values_call, values_unlock, aperture_call, aperture_unlock):
        raise RuntimeError("Emission getter diagnostic could not complete.")
    return {
        "getter_success": bool(observations[0]), "unlock_success": bool(observations[3]),
        "capacity_before": capacity, "capacity_after_call": observations[1], "capacity_after_unlock": observations[4],
        "count_before": count_seed, "count_after_call": observations[2], "count_after_unlock": observations[5],
        "output_before": list(aperture) if getter == 0 else list(seed),
        "output_after_call": list(aperture_call) if getter == 0 else list(values_call),
        "output_after_unlock": list(aperture_unlock) if getter == 0 else list(values_unlock),
    }


def get_extended_cycle_snapshot(handle, cycle, multi_channel=False):
    function = getattr(bridge, "OEMPA_GetExtendedCycleSnapshot", None)
    if function is None:
        raise RuntimeError("Extended readback unavailable; rebuild the bridge.")
    function.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(OEMPAExtendedCycleSnapshot)]
    function.restype = ctypes.c_int
    snapshot = OEMPAExtendedCycleSnapshot()
    if not function(handle, int(cycle), int(multi_channel), ctypes.byref(snapshot)):
        raise RuntimeError(f"Failed extended readback for cycle {cycle}.")
    return _decode_extended_cycle_snapshot(snapshot, multi_channel)


def _decode_extended_cycle_snapshot(snapshot, multi_channel):
    counts = (snapshot.width_count, snapshot.tx_delay_count, snapshot.start_count)
    if any(count < -1 or count > 16 for count in counts[:2]) or counts[2] < 0 or counts[2] > 16:
        raise RuntimeError("Invalid extended snapshot counts.")
    return {
        "widths_s": None if snapshot.width_count == -1 else tuple(snapshot.widths_s[:snapshot.width_count]),
        "tx_delays_s": None if snapshot.tx_delay_count == -1 else tuple(snapshot.tx_delays_s[:snapshot.tx_delay_count]),
        # Documented AOS 1.1.5.4 output is unchanged: never expose its seed as state.
        "hw_acquisition": None,
        "multi_starts_s": tuple(snapshot.multi_starts_s[:snapshot.start_count]) if multi_channel else None,
        "multi_decimation_bytes": tuple(snapshot.multi_decimation_bytes) if multi_channel else None,
    }


def get_cycle_snapshot(handle, cycle):
    snapshot = OEMPACycleSnapshot()

    result = bridge.OEMPA_GetCycleSnapshot(
        handle,
        int(cycle),
        ctypes.byref(snapshot),
    )

    if not result:
        raise RuntimeError(
            f"Failed to read cycle snapshot for cycle {cycle}."
        )

    return _decode_cycle_snapshot(snapshot)


def _decode_cycle_snapshot(snapshot):
    return {
        "cycle": snapshot.cycle,
        "gain_digital_db": snapshot.gain_digital_db,
        "gain_analog_db": snapshot.gain_analog_db,
        "beam_correction_db": snapshot.beam_correction_db,
        "start_s": snapshot.start_s,
        "range_s": snapshot.range_s,
        "sampling_hz": snapshot.sampling_hz,
        "time_slot_s": snapshot.time_slot_s,
        "point_count": snapshot.point_count,
        "point_factor": snapshot.point_factor,
        "bit_size": snapshot.bit_size,
        "rectification": snapshot.rectification,
        "compression_type": snapshot.compression_type,
        "filter_index": snapshot.filter_index,
        "tx_enabled": list(snapshot.tx_enabled),
        "rx_enabled": list(snapshot.rx_enabled),
    }


def get_ascan_config_snapshot(handle, cycle):
    ascan_enabled = ctypes.c_int()
    ascan_request = ctypes.c_int()
    request_frequency = ctypes.c_double()
    maximum_enabled = ctypes.c_int()
    minimum_enabled = ctypes.c_int()
    saturation_enabled = ctypes.c_int()
    trigger_mode = ctypes.c_int()

    result = bridge.OEMPA_GetAscanConfigSnapshot(
        handle,
        int(cycle),
        ctypes.byref(ascan_enabled),
        ctypes.byref(ascan_request),
        ctypes.byref(request_frequency),
        ctypes.byref(maximum_enabled),
        ctypes.byref(minimum_enabled),
        ctypes.byref(saturation_enabled),
        ctypes.byref(trigger_mode),
    )

    if not result:
        raise RuntimeError(
            f"Failed to read A-scan configuration for cycle {cycle}."
        )

    request_names = {
        0: "All",
        1: "Sampled",
        2: "BscanOnLine",
    }

    return {
        "ascan_enabled": bool(ascan_enabled.value),
        "ascan_request": ascan_request.value,
        "ascan_request_name": request_names.get(
            ascan_request.value,
            f"Unknown({ascan_request.value})",
        ),
        "ascan_request_frequency_hz": request_frequency.value,
        "maximum_enabled": bool(maximum_enabled.value),
        "minimum_enabled": bool(minimum_enabled.value),
        "saturation_enabled": bool(saturation_enabled.value),
        "trigger_mode": trigger_mode.value,
    }


def get_pa_receive_snapshot(handle, cycle, capacity=64):
    gains = (ctypes.c_float * capacity)()
    focal_tof = (ctypes.c_double * capacity)()
    element_count = ctypes.c_int()
    focal_count = ctypes.c_int()
    ddf_enabled = ctypes.c_int()
    emission_wedge = ctypes.c_double()
    reception_wedge = ctypes.c_double()

    result = bridge.OEMPA_GetPAReceiveSnapshot(
        handle,
        int(cycle),
        int(capacity),
        ctypes.byref(element_count),
        gains,
        ctypes.byref(focal_count),
        focal_tof,
        ctypes.byref(ddf_enabled),
        ctypes.byref(emission_wedge),
        ctypes.byref(reception_wedge),
    )

    if not result:
        raise RuntimeError(
            f"Failed to read PA receive configuration for cycle {cycle}."
        )

    ec = element_count.value
    fc = focal_count.value

    if ec < 0 or ec > capacity or fc < 0 or fc > capacity:
        raise RuntimeError(
            f"Invalid receive snapshot counts: elements={ec}, focal={fc}."
        )

    return {
        "element_count": ec,
        "gains_db": [float(gains[i]) for i in range(ec)],
        "focal_count": fc,
        "focal_tof_s": [float(focal_tof[i]) for i in range(fc)],
        "ddf_enabled": bool(ddf_enabled.value),
        "emission_wedge_delay_s": emission_wedge.value,
        "reception_wedge_delay_s": reception_wedge.value,
    }


def get_pa_delay_snapshot(handle, cycle, capacity=16):
    capacity = int(capacity)

    if capacity <= 0:
        raise ValueError("Capacity must be greater than zero.")

    tx_count = ctypes.c_int()
    rx_count = ctypes.c_int()
    focal_count = ctypes.c_int()
    focusing = ctypes.c_int()

    tx_delays = (ctypes.c_float * capacity)()
    rx_delays = (ctypes.c_float * capacity)()

    result = bridge.OEMPA_GetPADelaySnapshot(
        handle,
        int(cycle),
        capacity,
        ctypes.byref(tx_count),
        tx_delays,
        ctypes.byref(rx_count),
        ctypes.byref(focal_count),
        rx_delays,
        ctypes.byref(focusing),
    )

    if not result:
        raise RuntimeError(
            f"Failed to read PA delay snapshot for cycle {cycle}."
        )

    if tx_count.value < 0 or tx_count.value > capacity:
        raise RuntimeError("Invalid TX element count returned by OEM-PA.")

    if rx_count.value < 0 or rx_count.value > capacity:
        raise RuntimeError("Invalid RX element count returned by OEM-PA.")

    if focal_count.value != 1:
        raise RuntimeError(
            f"Expected one standard RX focal law, got {focal_count.value}."
        )

    return {
        "tx_element_count": tx_count.value,
        "tx_delays_s": list(tx_delays)[:tx_count.value],
        "rx_element_count": rx_count.value,
        "rx_focal_count": focal_count.value,
        "rx_delays_s": list(rx_delays)[:rx_count.value],
        "rx_focusing": focusing.value,
    }


def test_pa_focal_law_setters(handle, cycle=0):
    names = [
        "TX wedge delay",
        "TX widths",
        "TX delays",
        "TX aperture",
        "RX wedge delay",
        "RX gains",
        "RX delays",
        "RX aperture",
        "RX focusing",
        "RX DDF mode",
        "Unlock/commit with acquisition OFF",
    ]

    values = (ctypes.c_int * len(names))()

    result = bridge.OEMPA_TestPAFocalLawSetters(
        handle,
        int(cycle),
        values,
        len(names),
    )

    if not result:
        raise RuntimeError("PA focal-law setter diagnostic could not run.")

    return {
        name: bool(values[index])
        for index, name in enumerate(names)
    }


def register_ascan_callback(handle):
    if not bridge.OEMPA_StartAscan(
        handle
    ):
        raise RuntimeError(
            "Failed to register A-scan callback."
        )


def prepare_ascan_callback_buffers(handle, capacity_bytes):
    capacity_bytes = int(capacity_bytes)

    if capacity_bytes <= 0:
        raise ValueError("Callback buffer capacity must be positive.")

    if not bridge.OEMPA_PrepareAscanCallbackBuffers(
        handle,
        capacity_bytes,
    ):
        raise RuntimeError("Failed to preallocate A-scan callback buffers.")


def get_ascan_callback_diagnostic(handle):
    diagnostic = OEMPAAscanCallbackDiagnostic()

    if not bridge.OEMPA_GetAscanCallbackDiagnostic(
        handle,
        ctypes.byref(diagnostic),
    ):
        raise RuntimeError("No A-scan callback diagnostic is available.")

    buffers = []

    for buffer_index, buffer in enumerate(diagnostic.buffers):
        windows = []

        for window_index in range(CALLBACK_WINDOW_COUNT):
            byte_count = buffer.window_byte_counts[window_index]

            if not 0 <= byte_count <= CALLBACK_WINDOW_BYTE_CAPACITY:
                raise RuntimeError("Invalid callback window byte count.")

            windows.append({
                "start_index": buffer.window_start_indices[window_index],
                "sample_count": buffer.window_sample_counts[window_index],
                "byte_count": byte_count,
                "truncated": bool(buffer.window_truncated[window_index]),
                "bytes": bytes(buffer.window_bytes[window_index][:byte_count]),
            })

        buffers.append({
            "name": ("MAX", "MIN", "SAT")[buffer_index],
            "validity_flag": bool(buffer.validity_flag),
            "pointer_nonnull": bool(buffer.pointer_nonnull),
            "analyzed": bool(buffer.analyzed),
            "min_max_valid": bool(buffer.min_max_valid),
            "sample_193_to_end_all_zero": bool(buffer.sample_193_to_end_all_zero),
            "first_nonzero_index": buffer.first_nonzero_index,
            "last_nonzero_index": buffer.last_nonzero_index,
            "nonzero_sample_count": buffer.nonzero_sample_count,
            "exact_zero_sample_count": buffer.exact_zero_sample_count,
            "terminal_zero_sample_count": buffer.terminal_zero_sample_count,
            "minimum_value": buffer.minimum_value,
            "maximum_value": buffer.maximum_value,
            "saturation_lsb_set_count": buffer.saturation_lsb_set_count,
            "windows": windows,
        })

    maximum = buffers[0]
    near_window = maximum["windows"][0]

    return {
        "cycle": diagnostic.cycle,
        "data_count": diagnostic.data_count,
        "data_size": diagnostic.data_size,
        "signed": bool(diagnostic.is_signed),
        "bit_size": diagnostic.bit_size,
        "expected_byte_count": diagnostic.expected_byte_count,
        "max_flag": bool(diagnostic.max_flag),
        "min_flag": bool(diagnostic.min_flag),
        "sat_flag": bool(diagnostic.sat_flag),
        "max_pointer_nonnull": bool(diagnostic.max_pointer_nonnull),
        "min_pointer_nonnull": bool(diagnostic.min_pointer_nonnull),
        "sat_pointer_nonnull": bool(diagnostic.sat_pointer_nonnull),
        "first_nonzero_index": maximum["first_nonzero_index"],
        "last_nonzero_index": maximum["last_nonzero_index"],
        "nonzero_sample_count": maximum["nonzero_sample_count"],
        "all_samples_after_last_nonzero_zero": bool(maximum["analyzed"]),
        "terminal_zero_sample_count": maximum["terminal_zero_sample_count"],
        "window_start_index": near_window["start_index"],
        "window_sample_count": near_window["sample_count"],
        "window_byte_count": near_window["byte_count"],
        "window_truncated": near_window["truncated"],
        "bridge_copy_capacity_ok": bool(diagnostic.bridge_copy_capacity_ok),
        "window_bytes": near_window["bytes"],
        "buffers": buffers,
    }


def get_ascan_info(handle):
    cycle = ctypes.c_int()
    point_count = ctypes.c_int()
    data_size = ctypes.c_int()
    is_signed = ctypes.c_int()
    bit_size = ctypes.c_int()

    result = bridge.OEMPA_GetAscanInfo(
        handle,
        ctypes.byref(cycle),
        ctypes.byref(point_count),
        ctypes.byref(data_size),
        ctypes.byref(is_signed),
        ctypes.byref(bit_size),
    )

    if not result:
        raise RuntimeError("Failed to read copied A-scan metadata.")

    return {
        "cycle": cycle.value,
        "point_count": point_count.value,
        "data_size": data_size.value,
        "signed": bool(is_signed.value),
        "bit_size": bit_size.value,
    }


def copy_ascan(handle):
    info = get_ascan_info(handle)
    byte_count = info["point_count"] * info["data_size"]

    if byte_count <= 0:
        raise RuntimeError(f"Invalid copied A-scan size: {byte_count} bytes.")

    buffer = (ctypes.c_ubyte * byte_count)()
    copied = bridge.OEMPA_CopyAscan(handle, buffer, byte_count)

    if copied != byte_count:
        raise RuntimeError(
            f"Expected {byte_count} bytes from A-scan copy, got {copied}."
        )

    return bytes(buffer), info


def set_multiascan_cycle_count(
    handle,
    cycle_count,
):
    cycle_count = int(
        cycle_count
    )

    if cycle_count <= 0:
        raise ValueError(
            "Cycle count must be greater than zero."
        )

    result = bridge.OEMPA_SetMultiAscanCycleCount(
        handle,
        cycle_count,
    )

    if not result:
        raise RuntimeError(
            "Failed to allocate Multi-A-scan storage."
        )


def clear_multiascan(handle):
    if not bridge.OEMPA_ClearMultiAscan(
        handle
    ):
        raise RuntimeError(
            "Failed to clear Multi-A-scan storage."
        )


def get_multiascan_count(handle):
    return int(
        bridge.OEMPA_GetMultiAscanCount(
            handle
        )
    )


def get_callback_record_stats(handle, cycle_count):
    """Read local callback counters only; never accesses the device."""
    if not isinstance(cycle_count, int) or not 0 < cycle_count <= 2047:
        raise ValueError("Invalid callback statistics capacity.")
    counts = (ctypes.c_int * cycle_count)()
    summary = (ctypes.c_int * 5)()
    function = bridge.OEMPA_GetCallbackRecordStats
    function.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    function.restype = ctypes.c_int
    if not function(handle, cycle_count, counts, summary):
        raise RuntimeError("Callback record statistics unavailable.")
    return {**dict(zip(("total", "duplicates", "unexpected", "malformed", "first_unexpected"), summary)), "cycle_counts": tuple(counts)}


def begin_callback_order(handle, cycle_count, point_count, data_size, signed, bit_size):
    """Arm local diagnostics once per handle, after OFF callback preparation."""
    function = bridge.OEMPA_BeginCallbackOrder
    function.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 5
    function.restype = ctypes.c_int
    if not function(handle, cycle_count, point_count, data_size, int(signed), bit_size):
        raise RuntimeError("Callback order diagnostics could not be armed.")


def get_callback_order(handle):
    """Snapshot local diagnostics; no device API access or callback drainage claim."""
    from oempa.callback_order import decode_callback_order
    rows = (ctypes.c_int64 * (576 * 10))()
    summary = (ctypes.c_int64 * 9)()
    first = (ctypes.c_int64 * 2047)()
    function = bridge.OEMPA_GetCallbackOrder
    function.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_int64)] * 3
    function.restype = ctypes.c_int
    if not function(handle, rows, summary, first):
        raise RuntimeError("Callback order diagnostics unavailable.")
    return decode_callback_order(rows, summary, first)


def get_fmc_timing(handle):
    """Read local QPC observations only; SDK/device is never accessed here."""
    from oempa.timing import NATIVE_MARKS
    function = bridge.OEMPA_GetFMCTiming
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
    function.restype = ctypes.c_int
    values = (ctypes.c_int64 * (1 + len(NATIVE_MARKS)))()
    if not function(handle, values):
        raise RuntimeError("Native FMC timing unavailable")
    return dict(zip(('frequency',) + NATIVE_MARKS, values))


def begin_fmc_first_frame(handle, point_count, data_size, signed, bit_size):
    """Arm local first-frame storage protection after OFF/preallocation."""
    function = bridge.OEMPA_BeginFMCFirstFrame
    function.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 4
    function.restype = ctypes.c_int
    if not function(handle, point_count, data_size, int(signed), bit_size):
        raise RuntimeError("FMC first-frame protection could not be armed.")


def get_fmc_first_frame(handle):
    """Read mutex-protected local boundary counters; no device API access."""
    from oempa.fmc_acceptance import FRAME_FIELDS
    values = (ctypes.c_int64 * len(FRAME_FIELDS))()
    function = bridge.OEMPA_GetFMCFirstFrame
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
    function.restype = ctypes.c_int
    if not function(handle, values):
        raise RuntimeError("FMC first-frame evidence unavailable.")
    return dict(zip(FRAME_FIELDS, values))


def wait_fmc_first_frame(handle, interval_s):
    """Worker-only local notification wait, bounded for cooperative cancellation."""
    function = bridge.OEMPA_WaitFMCFirstFrame
    function.argtypes = [ctypes.c_void_p, ctypes.c_int]
    function.restype = ctypes.c_int
    if not function(handle, max(0, min(1000, int(interval_s * 1000)))):
        raise RuntimeError("FMC first-frame notification unavailable.")


def has_multiascan_cycle(
    handle,
    cycle,
):
    return bool(
        bridge.OEMPA_HasMultiAscanCycle(
            handle,
            int(cycle),
        )
    )


def get_multiascan_info(
    handle,
    cycle,
):
    point_count = ctypes.c_int()
    data_size = ctypes.c_int()
    is_signed = ctypes.c_int()
    bit_size = ctypes.c_int()

    result = bridge.OEMPA_GetMultiAscanInfo(
        handle,
        int(cycle),
        ctypes.byref(point_count),
        ctypes.byref(data_size),
        ctypes.byref(is_signed),
        ctypes.byref(bit_size),
    )

    if not result:
        raise RuntimeError(
            f"Failed to read A-scan information "
            f"for cycle {cycle}."
        )

    return {
        "point_count": point_count.value,
        "data_size": data_size.value,
        "signed": bool(is_signed.value),
        "bit_size": bit_size.value,
    }


def copy_multiascan(
    handle,
    cycle,
):
    info = get_multiascan_info(
        handle,
        cycle,
    )

    byte_count = (
        info["point_count"]
        * info["data_size"]
    )

    if byte_count <= 0:
        raise RuntimeError(
            f"Invalid A-scan size for cycle "
            f"{cycle}: {byte_count} bytes."
        )

    buffer = (
        ctypes.c_ubyte
        * byte_count
    )()

    copied = bridge.OEMPA_CopyMultiAscan(
        handle,
        int(cycle),
        buffer,
        byte_count,
    )

    if copied != byte_count:
        raise RuntimeError(
            f"Cycle {cycle}: expected "
            f"{byte_count} bytes, "
            f"but copied {copied}."
        )

    return bytes(buffer), info


def begin_preparation_timing():
    """Enable bounded local timing on the calling worker; no SDK access."""
    function = bridge.OEMPA_BeginPreparationTiming
    function.argtypes = []
    function.restype = ctypes.c_int
    if not function():
        raise RuntimeError("Preparation profiling unavailable")


def end_preparation_timing():
    """Disable and copy aggregate observations from the same worker."""
    finish = bridge.OEMPA_EndPreparationTiming
    finish.argtypes = []
    finish.restype = ctypes.c_int
    complete = bool(finish())
    function = bridge.OEMPA_GetPreparationTiming
    function.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char), ctypes.POINTER(ctypes.c_int64)]
    function.restype = ctypes.c_int
    calls = {}
    for index in range(64):
        name = ctypes.create_string_buffer(80)
        values = (ctypes.c_int64 * 3)()
        result = function(index, name, values)
        if result < 0:
            raise RuntimeError("Preparation profiling read failed")
        if not result:
            break
        calls[name.value.decode('ascii')] = {'count': values[0], 'total_s': values[1] / 1e9, 'max_s': values[2] / 1e9}
    return {'calls': calls, 'overflow': not complete}


def get_fmc_snapshot_batch(handle, base_cycles):
    """Read complete full16x16 FMC while OFF. None means old DLL lacks the export.

    A failed supported export never falls back/retries or exposes partial data.
    """
    function = getattr(bridge, 'OEMPA_GetFMCSnapshotBatch', None)
    if function is None:
        return None
    flags = tuple(base_cycles)
    if flags != tuple(index % 16 == 0 for index in range(256)):
        raise ValueError('Invalid full FMC base-cycle structure')
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(OEMPACycleSnapshot),
                         ctypes.POINTER(OEMPAExtendedCycleSnapshot), ctypes.POINTER(OEMPAExtendedCycleSnapshot), ctypes.POINTER(ctypes.c_int)]
    function.restype = ctypes.c_int
    normal = (OEMPACycleSnapshot * 256)()
    multi, tx = (OEMPAExtendedCycleSnapshot * 256)(), (OEMPAExtendedCycleSnapshot * 256)()
    topology = (ctypes.c_int * 3)(-1, -1, -1)
    if not function(handle, (ctypes.c_int * 256)(*flags), normal, multi, tx, topology):
        raise RuntimeError('FMC OFF batch readback failed (lock/getter/flush/unlock/decoding); configuration not accepted')
    if tuple(topology) != (256, 1, 1) or any(item.cycle != index for index, item in enumerate(normal)):
        raise RuntimeError('Invalid FMC batch topology/cycle order; configuration not accepted')
    return {'status': {'cycle_count': topology[0], 'multichannel_supported': bool(topology[1]), 'multichannel_enabled': bool(topology[2])},
            'normal': tuple(_decode_cycle_snapshot(item) for item in normal),
            'multi': tuple(_decode_extended_cycle_snapshot(item, True) for item in multi),
            'tx': tuple(_decode_extended_cycle_snapshot(item, False) for item in tx)}
