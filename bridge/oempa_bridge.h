#pragma once

#ifdef OEMPA_BRIDGE_EXPORTS
#define OEMPA_BRIDGE_API __declspec(dllexport)
#else
#define OEMPA_BRIDGE_API __declspec(dllimport)
#endif

// Cycle configuration snapshot

struct OEMPACycleSnapshot
{
    int cycle;

    double gain_digital_db;
    float gain_analog_db;
    float beam_correction_db;

    double start_s;
    double range_s;
    double sampling_hz;
    double time_slot_s;

    long point_count;
    long point_factor;

    int bit_size;
    int rectification;
    int compression_type;
    int filter_index;

    int tx_enabled[16];
    int rx_enabled[16];
};

enum
{
    OEMPA_CALLBACK_BUFFER_COUNT = 3,
    OEMPA_CALLBACK_WINDOW_COUNT = 6,
    OEMPA_CALLBACK_WINDOW_MAX_SAMPLES = 101,
    OEMPA_CALLBACK_WINDOW_MAX_DATA_SIZE = 2,
    OEMPA_CALLBACK_WINDOW_BYTE_CAPACITY =
        OEMPA_CALLBACK_WINDOW_MAX_SAMPLES * OEMPA_CALLBACK_WINDOW_MAX_DATA_SIZE
};

// Additional readbacks needed to distinguish FMC from normal PA timing

struct OEMPAExtendedCycleSnapshot
{
    int width_count;
    float widths_s[16];
    int tx_delay_count;
    float tx_delays_s[16];
    int hw_acquisition;
    int start_count;
    float multi_starts_s[16];
    unsigned char multi_decimation_bytes[8];
};

struct OEMPAAscanBufferDiagnostic
{
    int validity_flag;
    int pointer_nonnull;
    int analyzed;
    int min_max_valid;
    int sample_193_to_end_all_zero;
    int first_nonzero_index;
    int last_nonzero_index;
    unsigned long long nonzero_sample_count;
    unsigned long long exact_zero_sample_count;
    int terminal_zero_sample_count;
    int minimum_value;
    int maximum_value;
    unsigned long long saturation_lsb_set_count;
    int window_start_indices[OEMPA_CALLBACK_WINDOW_COUNT];
    int window_sample_counts[OEMPA_CALLBACK_WINDOW_COUNT];
    int window_byte_counts[OEMPA_CALLBACK_WINDOW_COUNT];
    int window_truncated[OEMPA_CALLBACK_WINDOW_COUNT];
    unsigned char window_bytes[OEMPA_CALLBACK_WINDOW_COUNT][OEMPA_CALLBACK_WINDOW_BYTE_CAPACITY];
};

struct OEMPAAscanCallbackDiagnostic
{
    int cycle;
    int data_count;
    int data_size;
    int is_signed;
    int bit_size;
    unsigned long long expected_byte_count;
    int max_flag;
    int min_flag;
    int sat_flag;
    int max_pointer_nonnull;
    int min_pointer_nonnull;
    int sat_pointer_nonnull;
    int bridge_copy_capacity_ok;
    struct OEMPAAscanBufferDiagnostic buffers[OEMPA_CALLBACK_BUFFER_COUNT];
};

extern "C"
{
    // Device

    OEMPA_BRIDGE_API void* __cdecl OEMPA_Create();

    OEMPA_BRIDGE_API void __cdecl OEMPA_Destroy(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_Connect(
        void* handle,
        const wchar_t* ip,
        unsigned short port
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_Disconnect(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_IsConnected(
        void* handle
    );

    // Hardware information

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetCycleCount(
        void* handle,
        int* cycle_count
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetFirmwareId(
        void* handle,
        unsigned short* firmware_id
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetElementCount(
        void* handle,
        int* element_count
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetApertureCount(
        void* handle,
        int* aperture_count
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetPulserPowerSnapshot(
        void* handle,
        double* max_power_w,
        double* current_power_w
    );

    // Configuration

    OEMPA_BRIDGE_API int __cdecl OEMPA_LoadConfiguration(
        void* handle,
        const wchar_t* file_path
    );

    // Diagnostic

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetConfigurationDiagnostic(
        int* entered,
        int* before_hw,
        int* after_hw,
        int* left,
        int* parsed_cycle_count
    );

    // Cycle configuration

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetCycleSnapshot(
        void* handle,
        int cycle,
        OEMPACycleSnapshot* snapshot
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetExtendedCycleSnapshot(
        void* handle,
        int cycle,
        int multi_channel,
        OEMPAExtendedCycleSnapshot* snapshot
    );

    // A-scan configuration hardware readback

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetAscanConfigSnapshot(
        void* handle,
        int cycle,
        int* ascan_enabled,
        int* ascan_request,
        double* ascan_request_frequency_hz,
        int* maximum_enabled,
        int* minimum_enabled,
        int* saturation_enabled,
        int* trigger_mode
    );

    // PA receive-path hardware readback

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetPAReceiveSnapshot(
        void* handle,
        int cycle,
        int capacity,
        int* element_count,
        float* gains_db,
        int* focal_count,
        double* focal_tof_s,
        int* ddf_enabled,
        double* emission_wedge_delay_s,
        double* reception_wedge_delay_s
    );

    // PA focal-law hardware readback

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetPADelaySnapshot(
        void* handle,
        int cycle,
        int capacity,
        int* tx_element_count,
        float* tx_delays_s,
        int* rx_element_count,
        int* rx_focal_count,
        float* rx_delays_s,
        int* rx_focusing
    );

    // PA focal-law setter diagnostic

    OEMPA_BRIDGE_API int __cdecl OEMPA_TestPAFocalLawSetters(
        void* handle,
        int cycle,
        int* status,
        int status_count
    );

    // A-scan

    OEMPA_BRIDGE_API int __cdecl OEMPA_StartAscan(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_PrepareAscanCallbackBuffers(
        void* handle,
        int buffer_capacity_bytes
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetAscanCallbackDiagnostic(
        void* handle,
        OEMPAAscanCallbackDiagnostic* diagnostic
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_HasAscan(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetAscanInfo(
        void* handle,
        int* cycle,
        int* point_count,
        int* data_size,
        int* is_signed,
        int* bit_size
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_CopyAscan(
        void* handle,
        void* buffer,
        int buffer_size
    );

    // Multi-channel A-scan capture

    OEMPA_BRIDGE_API int __cdecl OEMPA_SetMultiAscanCycleCount(
        void* handle,
        int cycle_count
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_ClearMultiAscan(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiAscanCount(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_HasMultiAscanCycle(
        void* handle,
        int cycle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiAscanInfo(
        void* handle,
        int cycle,
        int* point_count,
        int* data_size,
        int* is_signed,
        int* bit_size
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_CopyMultiAscan(
        void* handle,
        int cycle,
        void* buffer,
        int buffer_size
    );

    // Read-only local callback counts (summary: total, duplicates, unexpected, malformed, first unexpected).
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetCallbackRecordStats(void* handle, int capacity, int* counts, int* summary);

    // OFF-only, once per handle: bounded local chronological diagnostics.
    OEMPA_BRIDGE_API int __cdecl OEMPA_BeginCallbackOrder(void* handle, int cycles, int points, int size, int sign, int bits);
    // Caller supplies 576x10 event values, 9 summary values and 2047 first indices.
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetCallbackOrder(void* handle, long long* rows, long long* summary, long long* first);

    // Acquisition

    OEMPA_BRIDGE_API int __cdecl OEMPA_EnableAcquisition(
        void* handle
    );

    OEMPA_BRIDGE_API int __cdecl OEMPA_DisableAcquisition(
        void* handle
    );

    // FMC

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCSupport(
        void* handle,
        int* supported,
        int* enabled
    );

    // Multichannel

    OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiChannelSupport(
        void* handle,
        int* supported,
        int* enabled
    );

    // Direct read-only cycle classification diagnostic
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiHWChannelCycleDiagnostic(
        void* handle, int cycle, int initial_state,
        int* getter_success, int* acquisition_state, int* unlock_success
    );

    // Read-only emission getter diagnostic; arrays have 64 floats / 4 DWORDs.
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetEmissionGetterDiagnostic(
        void* handle, int cycle, int getter, int capacity, int count_seed,
        const float* float_seed, const unsigned long* aperture_seed,
        int* observations, float* after_call, float* after_unlock,
        unsigned long* aperture_after_call, unsigned long* aperture_after_unlock
    );

    // Parse

    // Local ordered FMC storage policy and completion notification; no SDK access.
    OEMPA_BRIDGE_API int __cdecl OEMPA_BeginFMCFirstFrame(void* handle, int points, int size, int sign, int bits);
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCFirstFrame(void* handle, long long* values);
    OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCTiming(void* handle, long long* values);
    OEMPA_BRIDGE_API int __cdecl OEMPA_WaitFMCFirstFrame(void* handle, int milliseconds);

    OEMPA_BRIDGE_API int __cdecl OEMPA_ParseConfiguration(
        const wchar_t* file_path,
        int* cycle_count,
        int* multi_channel_enabled
    );

    // Back up

    OEMPA_BRIDGE_API int __cdecl OEMPA_BackupConfiguration(
        void* handle,
        const wchar_t* file_path
    );
}

// Bounded, thread-local SDK preparation observations; no device operations.
extern "C" OEMPA_BRIDGE_API int __cdecl OEMPA_BeginPreparationTiming();
extern "C" OEMPA_BRIDGE_API int __cdecl OEMPA_EndPreparationTiming();
extern "C" OEMPA_BRIDGE_API int __cdecl OEMPA_GetPreparationTiming(int index, char* name, long long* values);

// Same full FMC coverage in one explicit OFF lock session; arrays each have256 entries.
extern "C" OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCSnapshotBatch(
    void* handle, const int* base_cycles, OEMPACycleSnapshot* normal,
    OEMPAExtendedCycleSnapshot* multi, OEMPAExtendedCycleSnapshot* tx, int* topology);
