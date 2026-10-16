#define OEMPA_BRIDGE_EXPORTS

#include "oempa_bridge.h"
#include "callback_order.h"
#include "fmc_first_frame.h"
#include "fmc_timing.h"
#include "preparation_timing.h"
#include "fmc_batch_readback.h"
#include <memory>

#include <windows.h>
#include <cwchar>
#include <cstring>
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <vector>

#include "UTKernelDriver.h"
#include "UTKernelDriverOEMPA.h"
#include "CustomizedDriverAPI.h"

// Preparation profiling is local to the serialized worker and opt-in.
static thread_local PreparationTiming preparation_timing;
template<class Function> static auto TimedPreparationCall(const char* name, Function call) -> decltype(call())
{
    if (!preparation_timing.enabled) return call();
    PreparationCall observation(preparation_timing, name);
    return call();
}

OEMPA_BRIDGE_API int __cdecl OEMPA_BeginPreparationTiming()
{
    preparation_timing = PreparationTiming();
    preparation_timing.enabled = true;
    return 1;
}

OEMPA_BRIDGE_API int __cdecl OEMPA_EndPreparationTiming()
{
    preparation_timing.enabled = false;
    return preparation_timing.overflow ? 0 : 1;
}

OEMPA_BRIDGE_API int __cdecl OEMPA_GetPreparationTiming(int index, char* name, int64_t* values)
{
    if (index < 0 || index >= 64 || !name || !values) return -1;
    const auto& entry = preparation_timing.entries[index];
    if (!entry.name) return 0;
    strcpy_s(name, 80, entry.name);
    values[0] = entry.count;
    values[1] = entry.total_ns;
    values[2] = entry.max_ns;
    return 1;
}

struct AOSBatchTraits
{
    using BitSize = enumBitSize;
    using Rectification = enumRectification;
    using Compression = enumCompressionType;
    using Filter = enumOEMPAFilterIndex;
    using Decimation = unionOEMMCDecimation;
    using Word = DWORD;
};

// Context

struct MultiAscanRecord
{
    std::vector<unsigned char> data;
    size_t data_bytes = 0;

    int point_count = 0;
    int data_size = 0;
    int is_signed = 0;
    int bit_size = 0;

    bool received = false;
    int callback_count = 0;
};


struct OEMPAContext
{
    // Declared before device: uncertain asynchronous outputs outlive device teardown.
    std::unique_ptr<FMCBatchStorage<AOSBatchTraits>> failed_batch_storage;
    CHWDeviceOEMPA device;

    std::mutex ascan_mutex;
    std::vector<unsigned char> ascan_data;
    size_t ascan_data_bytes = 0;

    int ascan_cycle = -1;
    int ascan_point_count = 0;
    int ascan_data_size = 0;
    int ascan_signed = 0;
    int ascan_bit_size = 0;

    bool ascan_received = false;

    OEMPAAscanCallbackDiagnostic callback_diagnostic = {};
    bool callback_diagnostic_ready = false;
    bool callback_buffers_preallocated = false;
    int callback_total = 0;
    int callback_duplicates = 0;
    int callback_unexpected = 0;
    int callback_malformed = 0;
    int callback_first_unexpected = -1;
    CallbackOrder callback_order;
    FMCFirstFrame first_frame;
    FMCTiming fmc_timing;
    std::condition_variable frame_changed;

    std::vector<MultiAscanRecord> multi_ascan;
};


// Configuration diagnostics

static long long MonotonicTick()
{
    LARGE_INTEGER value;
    return QueryPerformanceCounter(&value) ? value.QuadPart : 0;
}

struct AcquisitionOrderMarker
{
    OEMPAContext* context;
    bool on, success = false;
    AcquisitionOrderMarker(OEMPAContext* value, bool enable) : context(value), on(enable)
    {
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        context->callback_order.append(on ? CallbackOrder::OnRequested : CallbackOrder::OffRequested);
        if (!on && context->first_frame.active) context->fmc_timing.mark(FMCTiming::OffRequest, MonotonicTick());
        if (!on) context->callback_order.append(CallbackOrder::OffEntered);
    }
    ~AcquisitionOrderMarker()
    {
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        context->callback_order.append(on ? CallbackOrder::OnReturned : CallbackOrder::OffReturned, 0, -1, 0, 0, 0, 0, success ? 0 : 1);
    }
};

OEMPA_BRIDGE_API int __cdecl OEMPA_BeginCallbackOrder(void* handle, int cycles, int points, int size, int sign, int bits)
{
    if (!handle || cycles < 1 || cycles > 2047 || points < 1 || (size != 1 && size != 2) || (sign != 0 && sign != 1) || bits < 0 || bits > 3) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        if (context->callback_order.active || context->callback_total != 0 || context->multi_ascan.size() != static_cast<size_t>(cycles)) return 0;
        context->callback_order.reset(cycles, points, size, sign, bits);
        return 1;
    }
    catch (...) { return 0; }
}

OEMPA_BRIDGE_API int __cdecl OEMPA_GetCallbackOrder(void* handle, long long* rows, long long* summary, long long* first)
{
    if (!handle || !rows || !summary || !first) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        auto& log = context->callback_order;
        if (!log.active) return 0;
        // Observation marker refers to the last callback seen at this snapshot, not proof of drainage.
        log.append(CallbackOrder::FinalObserved, log.arrivals);
        const long long values[] = {log.stored, log.required, log.arrivals, log.dropped_callbacks, log.dropped_markers, log.complete_order, log.duplicate_order, log.last_callback_order, log.order};
        for (int i = 0; i < 9; ++i) summary[i] = values[i];
        for (int i = 0; i < log.stored; ++i)
            for (int j = 0; j < CallbackOrder::columns; ++j) rows[i * CallbackOrder::columns + j] = log.events[i][j];
        for (int i = 0; i < 2047; ++i) first[i] = log.first[i];
        return 1;
    }
    catch (...) { return 0; }
}

OEMPA_BRIDGE_API int __cdecl OEMPA_BeginFMCFirstFrame(void* handle, int points, int size, int sign, int bits)
{
    if (!handle || points < 1 || size != 1 || sign != 1 || bits != 0) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        if (!context->callback_buffers_preallocated || !context->callback_order.active || context->callback_total != 0 || context->first_frame.active || context->multi_ascan.size() != 256) return 0;
        for (const auto& record : context->multi_ascan)
            if (record.data.size() != static_cast<size_t>(points * size)) return 0;
        context->first_frame.reset(points, size, sign, bits);
        context->fmc_timing = FMCTiming{};
        return 1;
    }
    catch (...) { return 0; }
}

OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCFirstFrame(void* handle, long long* values)
{
    if (!handle || !values) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        const auto& f = context->first_frame;
        if (!f.active) return 0;
        const long long result[] = {f.accepted, f.complete(), f.error, f.error_cycle, f.arrivals, f.completion_arrival, f.first_post_arrival, f.post, f.pre_duplicates, f.pre_unexpected, f.pre_malformed, f.pre_out_of_order, f.post_unexpected, f.post_malformed};
        for (int i = 0; i < 14; ++i) values[i] = result[i];
        return 1;
    }
    catch (...) { return 0; }
}

OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCTiming(void* handle, long long* values)
{
    if (!handle || !values) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        if (!context->first_frame.active) return 0;
        LARGE_INTEGER frequency;
        if (!QueryPerformanceFrequency(&frequency)) return 0;
        values[0] = frequency.QuadPart;
        for (int i = 0; i < FMCTiming::Count; ++i) values[i + 1] = context->fmc_timing.ticks[i];
        return 1;
    }
    catch (...) { return 0; }
}

OEMPA_BRIDGE_API int __cdecl OEMPA_WaitFMCFirstFrame(void* handle, int milliseconds)
{
    if (!handle || milliseconds < 0 || milliseconds > 1000) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        std::unique_lock<std::mutex> lock(context->ascan_mutex);
        if (!context->first_frame.active) return 0;
        context->frame_changed.wait_for(lock, std::chrono::milliseconds(milliseconds), [&] { return context->first_frame.complete() || context->first_frame.error != FMCFirstFrame::None; });
        return 1;
    }
    catch (...) { return 0; }
}

static int g_config_entered = 0;
static int g_config_before_hw = 0;
static int g_config_after_hw = 0;
static int g_config_left = 0;
static int g_config_cycle_count = -1;

static structCorrectionOEMPA* WINAPI ConfigurationCallback(
    void* pAcquisitionParameter,
    const wchar_t* pFileName,
    enumStepCustomizedAPI eStep,
    structRoot* pRoot,
    structCycle* pCycle,
    CFocalLaw* pEmission,
    CFocalLaw* pReception)
{
    switch (eStep)
    {
    case eReadFileWriteHW_Enter:
        g_config_entered = 1;
        break;

    case eWriteHW_Enter:
        g_config_before_hw = 1;
        if (pRoot)
            g_config_cycle_count = pRoot->iCycleCount;
        break;

    case eWriteHW_Leave:
        g_config_after_hw = 1;
        if (pRoot)
            g_config_cycle_count = pRoot->iCycleCount;
        break;

    case eReadFileWriteHW_Leave:
        g_config_left = 1;
        break;

    default:
        break;
    }

    return nullptr;
}

// A-scan callback

static bool AscanSampleIsNonzero(
    const unsigned char* data,
    size_t sample_index,
    size_t sample_size)
{
    const size_t offset = sample_index * sample_size;

    for (size_t byte_index = 0; byte_index < sample_size; ++byte_index)
    {
        if (data[offset + byte_index] != 0)
            return true;
    }

    return false;
}

static int AscanSampleValue(
    const unsigned char* data,
    size_t sample_index,
    size_t sample_size,
    bool is_signed)
{
    const size_t offset = sample_index * sample_size;

    if (sample_size == 1)
    {
        return is_signed
            ? static_cast<signed char>(data[offset])
            : static_cast<unsigned char>(data[offset]);
    }

    if (sample_size == 2)
    {
        if (is_signed)
        {
            short value = 0;
            std::memcpy(&value, data + offset, sizeof(value));
            return static_cast<int>(value);
        }

        unsigned short value = 0;
        std::memcpy(&value, data + offset, sizeof(value));
        return static_cast<int>(value);
    }

    return 0;
}

static void AnalyzeAscanBuffer(
    const void* buffer,
    bool validity_flag,
    int buffer_index,
    size_t sample_count,
    size_t sample_size,
    bool is_signed,
    OEMPAAscanBufferDiagnostic& result)
{
    static const int window_starts[OEMPA_CALLBACK_WINDOW_COUNT] = {
        180, 200, 500, 1000, 2000, 2900
    };
    static const int window_lengths[OEMPA_CALLBACK_WINDOW_COUNT] = {
        31, 101, 101, 101, 101, 101
    };

    result = {};
    result.validity_flag = validity_flag ? 1 : 0;
    result.pointer_nonnull = buffer ? 1 : 0;
    result.first_nonzero_index = -1;
    result.last_nonzero_index = -1;
    result.sample_193_to_end_all_zero = 1;

    for (int window_index = 0;
        window_index < OEMPA_CALLBACK_WINDOW_COUNT;
        ++window_index)
    {
        result.window_start_indices[window_index] = window_starts[window_index];
    }

    if (!validity_flag || !buffer)
        return;

    result.analyzed = 1;
    const unsigned char* data =
        static_cast<const unsigned char*>(buffer);
    const bool is_saturation = buffer_index == 2;
    result.min_max_valid =
        !is_saturation && (sample_size == 1 || sample_size == 2) ? 1 : 0;

    bool has_value = false;

    for (size_t sample_index = 0; sample_index < sample_count; ++sample_index)
    {
        const bool nonzero =
            AscanSampleIsNonzero(data, sample_index, sample_size);

        if (nonzero)
        {
            if (result.first_nonzero_index < 0)
                result.first_nonzero_index = static_cast<int>(sample_index);

            result.last_nonzero_index = static_cast<int>(sample_index);
            ++result.nonzero_sample_count;
        }
        else
        {
            ++result.exact_zero_sample_count;
        }

        if (sample_index >= 193 && nonzero)
            result.sample_193_to_end_all_zero = 0;

        if (is_saturation)
        {
            if (data[sample_index * sample_size] & 0x01)
                ++result.saturation_lsb_set_count;
        }
        else if (result.min_max_valid)
        {
            const int value = AscanSampleValue(
                data,
                sample_index,
                sample_size,
                is_signed
            );

            if (!has_value)
            {
                result.minimum_value = value;
                result.maximum_value = value;
                has_value = true;
            }
            else
            {
                if (value < result.minimum_value)
                    result.minimum_value = value;
                if (value > result.maximum_value)
                    result.maximum_value = value;
            }
        }
    }

    const size_t last_nonzero_plus_one =
        result.last_nonzero_index >= 0
        ? static_cast<size_t>(result.last_nonzero_index + 1)
        : 0;
    result.terminal_zero_sample_count =
        static_cast<int>(sample_count - last_nonzero_plus_one);

    for (int window_index = 0;
        window_index < OEMPA_CALLBACK_WINDOW_COUNT;
        ++window_index)
    {
        const size_t start =
            static_cast<size_t>(window_starts[window_index]);

        if (start >= sample_count)
            continue;

        const size_t available = sample_count - start;
        const size_t requested =
            static_cast<size_t>(window_lengths[window_index]);
        const size_t window_samples =
            available < requested ? available : requested;
        const size_t requested_bytes = window_samples * sample_size;
        const size_t stored_bytes =
            requested_bytes < OEMPA_CALLBACK_WINDOW_BYTE_CAPACITY
            ? requested_bytes
            : OEMPA_CALLBACK_WINDOW_BYTE_CAPACITY;

        result.window_sample_counts[window_index] =
            static_cast<int>(window_samples);
        result.window_byte_counts[window_index] =
            static_cast<int>(stored_bytes);
        result.window_truncated[window_index] =
            stored_bytes < requested_bytes ? 1 : 0;

        std::memcpy(
            result.window_bytes[window_index],
            data + start * sample_size,
            stored_bytes
        );
    }
}

static UINT WINAPI AcquisitionAscanCallback(
    void* pAcquisitionParameter,
    structAcqInfoEx& acqInfo,
    const CStream_0x0001* pStreamHeader,
    const CSubStreamAscan_0x0103* pAscanHeader,
    const void* pBufferMax,
    const void* pBufferMin,
    const void* pBufferSat)
{
    if (!pAcquisitionParameter)
        return 0;
    if (!pAscanHeader)
    {
        OEMPAContext* invalid_context = static_cast<OEMPAContext*>(pAcquisitionParameter);
        std::lock_guard<std::mutex> lock(invalid_context->ascan_mutex);
        ++invalid_context->callback_total;
        ++invalid_context->callback_malformed;
        invalid_context->callback_order.callback(-1, 0, 0, 0, 0, false);
        invalid_context->first_frame.admit(-1, 0, 0, 0, 0, false);
        invalid_context->frame_changed.notify_one();
        return 0;
    }

    OEMPAContext* context =
        static_cast<OEMPAContext*>(pAcquisitionParameter);

    const size_t byte_count =
        static_cast<size_t>(pAscanHeader->dataCount) *
        static_cast<size_t>(pAscanHeader->dataSize);

    const int cycle =
        static_cast<int>(pAscanHeader->cycle);

    std::lock_guard<std::mutex> lock(
        context->ascan_mutex
    );

    // Local acceptance counters; no device calls or storage allocation.
    context->callback_order.callback(cycle, pAscanHeader->dataCount, pAscanHeader->dataSize, pAscanHeader->sign ? 1 : 0, pAscanHeader->bitSize, byte_count != 0 && pAscanHeader->max && pBufferMax);
    ++context->callback_total;
    if (cycle < 0 || static_cast<size_t>(cycle) >= context->multi_ascan.size())
    {
        ++context->callback_unexpected;
        if (context->callback_first_unexpected < 0)
            context->callback_first_unexpected = cycle;
    }
    else if (++context->multi_ascan[cycle].callback_count > 1)
        ++context->callback_duplicates;
    if (byte_count == 0 || !pAscanHeader->max || !pBufferMax ||
        (pAscanHeader->dataSize != 1 && pAscanHeader->dataSize != 2) ||
        (context->callback_buffers_preallocated && byte_count != context->ascan_data.size()))
        ++context->callback_malformed;
    if (context->first_frame.active)
    {
        const long long arrival_tick = context->first_frame.accepted == 0 ? MonotonicTick() : 0;
        const bool capacity_ok = cycle >= 0 && static_cast<size_t>(cycle) < context->multi_ascan.size() && byte_count <= context->multi_ascan[cycle].data.size();
        const bool admit = context->first_frame.admit(cycle, pAscanHeader->dataCount, pAscanHeader->dataSize, pAscanHeader->sign ? 1 : 0, pAscanHeader->bitSize,
            byte_count != 0 && pAscanHeader->max && pBufferMax && (capacity_ok || cycle < 0 || cycle >= 256));
        if (!admit)
        {
            context->frame_changed.notify_one();
            return 0;
        }
        context->fmc_timing.mark(FMCTiming::FirstCallback, arrival_tick);
    }
    if (byte_count == 0)
        return 0;

    const bool diagnostic_mode =
        context->callback_buffers_preallocated;
    const bool max_valid = pAscanHeader->max != 0;
    const bool min_valid = pAscanHeader->min != 0;
    const bool sat_valid = pAscanHeader->sat != 0;

    if (!diagnostic_mode && (!max_valid || !pBufferMax))
        return 0;

    OEMPAAscanCallbackDiagnostic& diagnostic =
        context->callback_diagnostic;

    if (diagnostic_mode)
    {
        diagnostic = {};
        diagnostic.cycle = cycle;
        diagnostic.data_count = static_cast<int>(pAscanHeader->dataCount);
        diagnostic.data_size = static_cast<int>(pAscanHeader->dataSize);
        diagnostic.is_signed = pAscanHeader->sign ? 1 : 0;
        diagnostic.bit_size = static_cast<int>(pAscanHeader->bitSize);
        diagnostic.expected_byte_count =
            static_cast<unsigned long long>(byte_count);
        diagnostic.max_flag = max_valid ? 1 : 0;
        diagnostic.min_flag = min_valid ? 1 : 0;
        diagnostic.sat_flag = sat_valid ? 1 : 0;
        diagnostic.max_pointer_nonnull = pBufferMax ? 1 : 0;
        diagnostic.min_pointer_nonnull = pBufferMin ? 1 : 0;
        diagnostic.sat_pointer_nonnull = pBufferSat ? 1 : 0;

        const size_t sample_count =
            static_cast<size_t>(pAscanHeader->dataCount);
        const size_t sample_size =
            static_cast<size_t>(pAscanHeader->dataSize);

        AnalyzeAscanBuffer(
            pBufferMax,
            max_valid,
            0,
            sample_count,
            sample_size,
            pAscanHeader->sign != 0,
            diagnostic.buffers[0]
        );
        AnalyzeAscanBuffer(
            pBufferMin,
            min_valid,
            1,
            sample_count,
            sample_size,
            pAscanHeader->sign != 0,
            diagnostic.buffers[1]
        );
        AnalyzeAscanBuffer(
            pBufferSat,
            sat_valid,
            2,
            sample_count,
            sample_size,
            false,
            diagnostic.buffers[2]
        );
    }

    if (max_valid && pBufferMax && !diagnostic_mode)
        context->ascan_data.resize(byte_count);

    const bool ascan_capacity_ok =
        max_valid && pBufferMax && byte_count <= context->ascan_data.size();

    if (ascan_capacity_ok)
    {
        std::memcpy(
            context->ascan_data.data(),
            pBufferMax,
            byte_count
        );
        context->ascan_data_bytes = byte_count;
    }
    else
    {
        context->ascan_data_bytes = 0;
    }

    context->ascan_cycle = cycle;

    context->ascan_point_count =
        static_cast<int>(pAscanHeader->dataCount);

    context->ascan_data_size =
        static_cast<int>(pAscanHeader->dataSize);

    context->ascan_signed =
        pAscanHeader->sign ? 1 : 0;

    context->ascan_bit_size =
        static_cast<int>(pAscanHeader->bitSize);

    context->ascan_received = true;

    // Store each configured cycle independently.

    bool multi_ascan_capacity_ok = false;

    if (cycle >= 0 &&
        static_cast<size_t>(cycle) < context->multi_ascan.size())
    {
        MultiAscanRecord& record =
            context->multi_ascan[cycle];

        if (max_valid && pBufferMax && !diagnostic_mode)
            record.data.resize(byte_count);

        multi_ascan_capacity_ok =
            max_valid && pBufferMax && byte_count <= record.data.size();

        if (multi_ascan_capacity_ok)
        {
            std::memcpy(
                record.data.data(),
                pBufferMax,
                byte_count
            );
            record.data_bytes = byte_count;
        }
        else
        {
            record.data_bytes = 0;
        }

        record.point_count =
            static_cast<int>(pAscanHeader->dataCount);

        record.data_size =
            static_cast<int>(pAscanHeader->dataSize);

        record.is_signed =
            pAscanHeader->sign ? 1 : 0;

        record.bit_size =
            static_cast<int>(pAscanHeader->bitSize);

        record.received = true;
    }

    if (diagnostic_mode)
    {
        diagnostic.bridge_copy_capacity_ok =
            ascan_capacity_ok && multi_ascan_capacity_ok ? 1 : 0;
        context->callback_diagnostic_ready = true;
    }

    if (context->first_frame.active && context->first_frame.complete())
    {
        context->fmc_timing.mark(FMCTiming::FrameComplete, MonotonicTick());
        context->frame_changed.notify_one();
    }

    return 0;
}


extern "C"
{


// Device creation

OEMPA_BRIDGE_API void* __cdecl OEMPA_Create()
{
    try
    {
        HMODULE customized_api = LoadLibraryW(
            L"C:\\Program Files\\AOS\\OEMPA 1.1.5.4\\UTCustomizedDriverAPI.dll"
        );

        if (!customized_api)
        {
            DWORD error = GetLastError();

            wchar_t message[256];

            swprintf_s(
                message,
                256,
                L"Failed to load UTCustomizedDriverAPI.dll. Windows error: %lu",
                error
            );

            MessageBoxW(
                nullptr,
                message,
                L"OEMPA Bridge Error",
                MB_OK | MB_ICONERROR
            );

            return nullptr;
        }

        return new OEMPAContext();
    }
    catch (...)
    {
        MessageBoxW(
            nullptr,
            L"Exception while creating CHWDeviceOEMPA.",
            L"OEMPA Bridge Error",
            MB_OK | MB_ICONERROR
        );

        return nullptr;
    }
}


// Device destruction

OEMPA_BRIDGE_API void __cdecl OEMPA_Destroy(
    void* handle)
{
    if (!handle)
        return;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (context->device.GetSWDevice()->IsConnected())
        {
            context->device.GetSWDevice()->SetConnectionState(
                eDisconnected,
                true
            );
        }
    }
    catch (...)
    {
    }

    delete context;
}


// Connection

OEMPA_BRIDGE_API int __cdecl OEMPA_Connect(
    void* handle,
    const wchar_t* ip,
    unsigned short port)
{
    if (!handle || !ip)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        CSWDeviceOEMPA* sw_oempa =
            context->device.GetSWDeviceOEMPA();

        CSWDevice* sw_device =
            context->device.GetSWDevice();

        if (!sw_oempa || !sw_device)
            return 0;

        if (!sw_oempa->SetIPAddress(ip))
            return 0;

        if (!sw_oempa->_SetPort(port))
            return 0;

        if (!sw_device->SetConnectionState(
            eConnected,
            true))
        {
            return 0;
        }

        return sw_device->IsConnected() ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Disconnection

OEMPA_BRIDGE_API int __cdecl OEMPA_Disconnect(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        return context->device.GetSWDevice()->SetConnectionState(
            eDisconnected,
            true
        ) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Connection state

OEMPA_BRIDGE_API int __cdecl OEMPA_IsConnected(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        return context->device.GetSWDevice()->IsConnected()
            ? 1
            : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Cycle count

OEMPA_BRIDGE_API int __cdecl OEMPA_GetCycleCount(
    void* handle,
    int* cycle_count)
{
    if (!handle || !cycle_count)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!TimedPreparationCall("GetCycleCount.LockDevice", [&]() { return context->device.LockDevice(); }))
            return 0;

        bool ok =
            TimedPreparationCall("GetCycleCount.GetCycleCount", [&]() { return context->device.GetCycleCount(
                cycle_count
            ); });

        bool unlock_ok =
            TimedPreparationCall("GetCycleCount.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

        return (ok && unlock_ok) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Firmware ID

OEMPA_BRIDGE_API int __cdecl OEMPA_GetFirmwareId(
    void* handle,
    unsigned short* firmware_id)
{
    if (!handle || !firmware_id)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.LockDevice())
            return 0;

        bool ok =
            context->device.GetFWId(
                firmware_id
            );

        bool unlock_ok =
            context->device.UnlockDevice();

        return (ok && unlock_ok) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Element count

OEMPA_BRIDGE_API int __cdecl OEMPA_GetElementCount(
    void* handle,
    int* element_count)
{
    if (!handle || !element_count)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.LockDevice())
            return 0;

        bool ok =
            context->device.GetElementCountMax(
                element_count
            );

        bool unlock_ok =
            context->device.UnlockDevice();

        return (ok && unlock_ok) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Aperture count

OEMPA_BRIDGE_API int __cdecl OEMPA_GetApertureCount(
    void* handle,
    int* aperture_count)
{
    if (!handle || !aperture_count)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.LockDevice())
            return 0;

        bool ok =
            context->device.GetApertureCountMax(
                aperture_count
            );

        bool unlock_ok =
            context->device.UnlockDevice();

        return (ok && unlock_ok) ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}

// Pulser power snapshot

OEMPA_BRIDGE_API int __cdecl OEMPA_GetPulserPowerSnapshot(
    void* handle,
    double* max_power_w,
    double* current_power_w)
{
    if (!handle || !max_power_w || !current_power_w)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        CSWDeviceOEMPA* sw_oempa =
            context->device.GetSWDeviceOEMPA();

        if (!sw_oempa)
            return 0;

        *max_power_w = sw_oempa->GetPulserPowerMax();
        *current_power_w = sw_oempa->GetPulserPowerCurrent();

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}

// Load configuration

OEMPA_BRIDGE_API int __cdecl OEMPA_LoadConfiguration(
    void* handle,
    const wchar_t* file_path)
{
    if (!handle || !file_path)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        if (GetFileAttributesW(file_path) == INVALID_FILE_ATTRIBUTES)
            return 0;

        // Make sure acquisition is OFF before changing hardware configuration.
        if (!context->device.LockDevice())
            return 0;

        if (!context->device.UnlockDevice(eAcqOff))
            return 0;

        g_config_entered = 0;
        g_config_before_hw = 0;
        g_config_after_hw = 0;
        g_config_left = 0;
        g_config_cycle_count = -1;

        OEMPA_SetCallbackCustomizedDriverAPI(ConfigurationCallback);

        // Parse the file and write the configuration to the OEM-PA.
        bool ok = OEMPA_ReadFileWriteHW(
            &context->device,
            file_path,
            eAcqOff
        );

        return ok ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Configuration diagnostic

OEMPA_BRIDGE_API int __cdecl OEMPA_GetConfigurationDiagnostic(
    int* entered,
    int* before_hw,
    int* after_hw,
    int* left,
    int* parsed_cycle_count)
{
    if (!entered || !before_hw || !after_hw || !left || !parsed_cycle_count)
        return 0;

    *entered = g_config_entered;
    *before_hw = g_config_before_hw;
    *after_hw = g_config_after_hw;
    *left = g_config_left;
    *parsed_cycle_count = g_config_cycle_count;

    return 1;
}


// FMC capability

OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCSupport(
    void* handle,
    int* supported,
    int* enabled)
{
    if (!handle || !supported || !enabled)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        CSWDeviceOEMPA* sw_oempa =
            context->device.GetSWDeviceOEMPA();

        if (!sw_oempa)
            return 0;

        *supported =
            sw_oempa->IsFullMatrixCaptureReadWrite()
            ? 1
            : 0;

        bool fmc_enabled = false;

        if (!context->device.LockDevice())
            return 0;

        bool read_ok =
            context->device.GetEnableFMC(
                &fmc_enabled
            );

        bool unlock_ok =
            context->device.UnlockDevice();

        if (!read_ok || !unlock_ok)
        {
            *enabled = 0;
            return 0;
        }

        *enabled =
            fmc_enabled ? 1 : 0;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}

// Multi-channel capability

OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiChannelSupport(
    void* handle,
    int* supported,
    int* enabled)
{
    if (!handle || !supported || !enabled)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!TimedPreparationCall("GetMultiChannelSupport.IsConnected", [&]() { return context->device.GetSWDevice()->IsConnected(); }))
            return 0;

        CSWDeviceOEMPA* sw_oempa = TimedPreparationCall("GetMultiChannelSupport.GetSWDeviceOEMPA", [&]() { return context->device.GetSWDeviceOEMPA(); });

        if (!sw_oempa)
            return 0;

        *supported = TimedPreparationCall("GetMultiChannelSupport.IsMultiHWChannelSupported", [&]() { return sw_oempa->IsMultiHWChannelSupported(); }) ? 1 : 0;

        bool multi_enabled = false;

        if (!TimedPreparationCall("GetMultiChannelSupport.LockDevice", [&]() { return context->device.LockDevice(); }))
            return 0;

        bool read_ok = TimedPreparationCall("GetMultiChannelSupport.GetEnableMultiHWChannel", [&]() { return context->device.GetEnableMultiHWChannel(&multi_enabled); });
        bool unlock_ok = TimedPreparationCall("GetMultiChannelSupport.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

        if (!read_ok || !unlock_ok)
        {
            *enabled = 0;
            return 1;
        }

        *enabled = multi_enabled ? 1 : 0;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}

// Cycle configuration snapshot

OEMPA_BRIDGE_API int __cdecl OEMPA_GetCycleSnapshot(
    void* handle,
    int cycle,
    OEMPACycleSnapshot* snapshot)
{
    if (!handle || !snapshot || cycle < 0)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        if (!TimedPreparationCall("GetCycleSnapshot.IsConnected", [&]() { return context->device.GetSWDevice()->IsConnected(); }))
            return 0;

        OEMPACycleSnapshot result = {};
        result.cycle = cycle;

        enumBitSize bit_size = e8Bits;
        enumRectification rectification = eSigned;
        enumCompressionType compression_type = eCompression;
        enumOEMPAFilterIndex filter_index;

        DWORD tx_aperture[
            g_iOEMPAApertureDWordCount
        ] = {};

        DWORD rx_aperture[
            g_iOEMPAApertureDWordCount
        ] = {};

        if (!TimedPreparationCall("GetCycleSnapshot.LockDevice", [&]() { return context->device.LockDevice(); }))
        {
            MessageBoxW(
                nullptr,
                L"LockDevice failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Digital gain

        if (!TimedPreparationCall("GetCycleSnapshot.GetGainDigital", [&]() { return context->device.GetGainDigital(
            cycle,
            &result.gain_digital_db); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetGainDigital failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Analog gain

        if (!TimedPreparationCall("GetCycleSnapshot.GetGainAnalog", [&]() { return context->device.GetGainAnalog(
            cycle,
            &result.gain_analog_db); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetGainAnalog failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Beam correction

        if (!TimedPreparationCall("GetCycleSnapshot.GetBeamCorrection", [&]() { return context->device.GetBeamCorrection(
            cycle,
            &result.beam_correction_db); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetBeamCorrection failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // A-scan bit size

        if (!TimedPreparationCall("GetCycleSnapshot.GetAscanBitSize", [&]() { return context->device.GetAscanBitSize(
            &bit_size); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetAscanBitSize failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Rectification

        if (!TimedPreparationCall("GetCycleSnapshot.GetAscanRectification", [&]() { return context->device.GetAscanRectification(
            cycle,
            &rectification); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetAscanRectification failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // A-scan start

        if (!TimedPreparationCall("GetCycleSnapshot.GetAscanStart", [&]() { return context->device.GetAscanStart(
            cycle,
            &result.start_s); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetAscanStart failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // A-scan range

        if (!TimedPreparationCall("GetCycleSnapshot.GetAscanRange", [&]() { return context->device.GetAscanRange(
            cycle,
            &result.range_s,
            &compression_type,
            &result.point_count,
            &result.point_factor); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetAscanRange failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Filter

        if (!TimedPreparationCall("GetCycleSnapshot.GetFilterIndex", [&]() { return context->device.GetFilterIndex(
            cycle,
            &filter_index); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetFilterIndex failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Time slot

        if (!TimedPreparationCall("GetCycleSnapshot.GetTimeSlot", [&]() { return context->device.GetTimeSlot(
            cycle,
            &result.time_slot_s); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetTimeSlot failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // TX aperture

        if (!TimedPreparationCall("GetCycleSnapshot.GetEmissionEnable", [&]() { return context->device.GetEmissionEnable(
            cycle,
            tx_aperture); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetEmissionEnable failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // RX aperture

        if (!TimedPreparationCall("GetCycleSnapshot.GetReceptionEnable", [&]() { return context->device.GetReceptionEnable(
            cycle,
            rx_aperture); }))
        {
            TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });

            MessageBoxW(
                nullptr,
                L"GetReceptionEnable failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Complete hardware communication

        if (!TimedPreparationCall("GetCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); }))
        {
            MessageBoxW(
                nullptr,
                L"UnlockDevice failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Sampling frequency

        if (!TimedPreparationCall("GetCycleSnapshot.GetSamplingFrequency", [&]() { return context->device.GetSamplingFrequency(
            compression_type,
            result.point_factor,
            result.sampling_hz); }))
        {
            MessageBoxW(
                nullptr,
                L"GetSamplingFrequency failed.",
                L"OEMPA Snapshot",
                MB_OK | MB_ICONERROR
            );

            return 0;
        }

        // Enum values

        result.bit_size =
            static_cast<int>(bit_size);

        result.rectification =
            static_cast<int>(rectification);

        result.compression_type =
            static_cast<int>(compression_type);

        result.filter_index =
            static_cast<int>(filter_index);

        // TX and RX elements

        for (int element = 0; element < 16; ++element)
        {
            bool tx_enabled = false;
            bool rx_enabled = false;

            if (!CHWDeviceOEMPA::GetElementEnable(
                element,
                tx_aperture,
                tx_enabled))
            {
                MessageBoxW(
                    nullptr,
                    L"GetElementEnable failed for TX.",
                    L"OEMPA Snapshot",
                    MB_OK | MB_ICONERROR
                );

                return 0;
            }

            if (!CHWDeviceOEMPA::GetElementEnable(
                element,
                rx_aperture,
                rx_enabled))
            {
                MessageBoxW(
                    nullptr,
                    L"GetElementEnable failed for RX.",
                    L"OEMPA Snapshot",
                    MB_OK | MB_ICONERROR
                );

                return 0;
            }

            result.tx_enabled[element] =
                tx_enabled ? 1 : 0;

            result.rx_enabled[element] =
                rx_enabled ? 1 : 0;
        }

        *snapshot = result;

        return 1;
    }
    catch (...)
    {
        MessageBoxW(
            nullptr,
            L"Exception inside OEMPA_GetCycleSnapshot.",
            L"OEMPA Snapshot",
            MB_OK | MB_ICONERROR
        );

        return 0;
    }
}

// Full FMC readback: pointer outputs remain owned until OFF unlock completes.


OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCSnapshotBatch(
    void* handle, const int* base_cycles, OEMPACycleSnapshot* normal,
    OEMPAExtendedCycleSnapshot* multi, OEMPAExtendedCycleSnapshot* tx, int* topology)
{
    if (!handle || !base_cycles || !normal || !multi || !tx || !topology) return 0;
    try
    {
        auto* context = static_cast<OEMPAContext*>(handle);
        if (!context->device.GetSWDevice()->IsConnected()) return 0;
        bool supported = context->device.GetSWDeviceOEMPA()->IsMultiHWChannelSupported();
        if (!supported) return 0;
        std::array<int, 256> base = {};
        for (int cycle = 0; cycle < 256; ++cycle)
        {
            // Restrict the bulk path to the established full16x16 grouping.
            if (base_cycles[cycle] != (cycle % 16 == 0 ? 1 : 0)) return 0;
            base[cycle] = base_cycles[cycle];
        }
        // A failed batch retains its one bounded owner until handle destruction.
        if (context->failed_batch_storage) return 0;
        context->failed_batch_storage = std::make_unique<FMCBatchStorage<AOSBatchTraits>>();
        auto& storage = context->failed_batch_storage;
        auto observe = [](const char* name, auto call) { return TimedPreparationCall(name, call); };
        if (!ReadFMCBatch(context->device, *storage, base, observe, eAcqOff)) return 0;
        // Publish atomically at the API level: no usable arrays on any failure.
        for (int cycle = 0; cycle < 256; ++cycle)
        {
            normal[cycle] = storage->cycles[cycle].normal;
            multi[cycle] = storage->cycles[cycle].multi;
            tx[cycle] = storage->cycles[cycle].tx;
        }
        topology[0] = storage->cycle_count;
        topology[1] = supported ? 1 : 0;
        topology[2] = storage->multichannel ? 1 : 0;
        storage.reset(); // Successful OFF unlock proves outputs are no longer pending.
        return 1;
    }
    catch (...) { return 0; }
}

// Parse configuration

OEMPA_BRIDGE_API int __cdecl OEMPA_ParseConfiguration(
    const wchar_t* file_path,
    int* cycle_count,
    int* multi_channel_enabled)
{
    if (!file_path || !cycle_count || !multi_channel_enabled)
        return 0;

    *cycle_count = -1;
    *multi_channel_enabled = 0;

    if (GetFileAttributesW(file_path) == INVALID_FILE_ATTRIBUTES)
        return 0;

    structRoot root;
    structCycle* pCycle = nullptr;
    CFocalLaw* pEmission = nullptr;
    CFocalLaw* pReception = nullptr;

    bool parse_ok = false;

    try
    {
        parse_ok = OEMPA_ReadFileText(
            file_path,
            root,
            pCycle,
            pEmission,
            pReception
        );

        if (parse_ok)
        {
            *cycle_count = root.iCycleCount;
            *multi_channel_enabled = root.bEnableMultiHWChannel ? 1 : 0;
        }

        OEMPA_Free(
            pCycle,
            pEmission,
            pReception
        );

        return parse_ok ? 1 : 0;
    }
    catch (...)
    {
        OEMPA_Free(
            pCycle,
            pEmission,
            pReception
        );

        return 0;
    }
}


// Mode-specific cycle readback (no acquisition or configuration setters)

OEMPA_BRIDGE_API int __cdecl OEMPA_GetExtendedCycleSnapshot(
    void* handle, int cycle, int multi_channel, OEMPAExtendedCycleSnapshot* snapshot)
{
    if (!handle || cycle < 0 || !snapshot)
        return 0;
    OEMPAContext* context = static_cast<OEMPAContext*>(handle);
    bool locked = false;
    try
    {
        if (!TimedPreparationCall("GetExtendedCycleSnapshot.IsConnected", [&]() { return context->device.GetSWDevice()->IsConnected(); }))
            return 0;
        OEMPAExtendedCycleSnapshot result = {};
        result.width_count = -1;
        result.tx_delay_count = -1;
        int width_capacity = 16;
        int delay_capacity = 16;
        int start_capacity = 16;
        bool hw_acquisition = false;
        unionOEMMCDecimation decimation = {};
        locked = TimedPreparationCall("GetExtendedCycleSnapshot.LockDevice", [&]() { return context->device.LockDevice(); });
        if (!locked)
            return 0;
        bool ok = true;
        if (multi_channel)
        {
            ok = TimedPreparationCall("GetExtendedCycleSnapshot.GetEnableMultiHWChannelAcquisition", [&]() { return context->device.GetEnableMultiHWChannelAcquisition(cycle, &hw_acquisition); });
            ok = ok && TimedPreparationCall("GetExtendedCycleSnapshot.GetMultiHWChannelAcqWriteStart", [&]() { return context->device.GetMultiHWChannelAcqWriteStart(cycle, start_capacity, &result.start_count, result.multi_starts_s); });
            ok = ok && TimedPreparationCall("GetExtendedCycleSnapshot.GetMultiHWChannelAcqDecimation", [&]() { return context->device.GetMultiHWChannelAcqDecimation(cycle, &decimation); });
            // Preserve the packed SDK bytes; Python does not guess channel encoding.
            memcpy(result.multi_decimation_bytes, decimation.byte, sizeof(result.multi_decimation_bytes));
        }
        // Replay cycles have no TX aperture; their widths/delays are not read.
        if (!multi_channel || hw_acquisition)
        {
            ok = ok && TimedPreparationCall("GetExtendedCycleSnapshot.GetEmissionWidths", [&]() { return context->device.GetEmissionWidths(cycle, width_capacity, &result.width_count, result.widths_s); });
            ok = ok && TimedPreparationCall("GetExtendedCycleSnapshot.GetEmissionDelays", [&]() { return context->device.GetEmissionDelays(cycle, delay_capacity, &result.tx_delay_count, result.tx_delays_s); });
        }
        bool unlock_ok = TimedPreparationCall("GetExtendedCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });
        locked = false;
        if (!ok || !unlock_ok || result.width_count < -1 || result.width_count > 16 ||
            result.tx_delay_count < -1 || result.tx_delay_count > 16 || result.start_count < 0 || result.start_count > 16)
            return 0;
        result.hw_acquisition = hw_acquisition ? 1 : 0;
        *snapshot = result;
        return 1;
    }
    catch (...)
    {
        if (locked)
            TimedPreparationCall("GetExtendedCycleSnapshot.UnlockDevice", [&]() { return context->device.UnlockDevice(); });
        return 0;
    }
}

// Direct read-only cycle classification diagnostic
OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiHWChannelCycleDiagnostic(
    void* handle, int cycle, int initial_state,
    int* getter_success, int* acquisition_state, int* unlock_success)
{
    if (!handle || cycle < 0 || (initial_state != 0 && initial_state != 1) ||
        !getter_success || !acquisition_state || !unlock_success)
        return 0;
    *getter_success = *acquisition_state = *unlock_success = -1;
    OEMPAContext* context = static_cast<OEMPAContext*>(handle);
    bool locked = false;
    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;
        locked = context->device.LockDevice();
        if (!locked)
            return 0;
        bool enabled = initial_state != 0;
        bool ok = context->device.GetEnableMultiHWChannelAcquisition(cycle, &enabled);
        *getter_success = ok ? 1 : 0;
        *acquisition_state = enabled ? 1 : 0;
        *unlock_success = context->device.UnlockDevice() ? 1 : 0;
        locked = false;
        return 1;
    }
    catch (...)
    {
        if (locked)
            context->device.UnlockDevice();
        return 0;
    }
}

// Read-only emission getter diagnostic
OEMPA_BRIDGE_API int __cdecl OEMPA_GetEmissionGetterDiagnostic(
    void* handle, int cycle, int getter, int capacity, int count_seed,
    const float* float_seed, const unsigned long* aperture_seed,
    int* observations, float* after_call, float* after_unlock,
    unsigned long* aperture_after_call, unsigned long* aperture_after_unlock)
{
    if (!handle || cycle < 0 || getter < 0 || getter > 2 || capacity < 1 || capacity > 64 ||
        count_seed < 0 || count_seed > capacity || !float_seed || !aperture_seed ||
        !observations || !after_call || !after_unlock || !aperture_after_call || !aperture_after_unlock)
        return 0;
    static_assert(g_iOEMPAApertureElementCountMax == 64, "Diagnostic allocation must match SDK");
    static_assert(g_iOEMPAApertureDWordCount == 4, "Diagnostic bitmap must match SDK");
    OEMPAContext* context = static_cast<OEMPAContext*>(handle);
    bool locked = false;
    try
    {
        float values[64];
        DWORD aperture[4];
        std::memcpy(values, float_seed, sizeof(values));
        std::memcpy(aperture, aperture_seed, sizeof(aperture));
        int count = count_seed;
        int maximum = capacity;
        locked = context->device.LockDevice(eAcqOff);
        if (!locked)
            return 0;
        bool ok = getter == 0 ? context->device.GetEmissionEnable(cycle, aperture) :
            getter == 1 ? context->device.GetEmissionWidths(cycle, maximum, &count, values) :
            context->device.GetEmissionDelays(cycle, maximum, &count, values);
        observations[0] = ok ? 1 : 0;
        observations[1] = maximum;
        observations[2] = count;
        std::memcpy(after_call, values, sizeof(values));
        std::memcpy(aperture_after_call, aperture, sizeof(aperture));
        observations[3] = context->device.UnlockDevice(eAcqOff) ? 1 : 0;
        locked = false;
        observations[4] = maximum;
        observations[5] = count;
        std::memcpy(after_unlock, values, sizeof(values));
        std::memcpy(aperture_after_unlock, aperture, sizeof(aperture));
        return 1;
    }
    catch (...)
    {
        if (locked)
            context->device.UnlockDevice(eAcqOff);
        return 0;
    }
}

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
    int* trigger_mode)
{
    if (!handle || cycle < 0 ||
        !ascan_enabled || !ascan_request ||
        !ascan_request_frequency_hz ||
        !maximum_enabled || !minimum_enabled ||
        !saturation_enabled || !trigger_mode)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        bool ascan = false;
        bool maximum = false;
        bool minimum = false;
        bool saturation = false;
        enumAscanRequest request = eAscanAll;
        enumOEMPATrigger trigger;
        double frequency = 0.0;

        if (!context->device.LockDevice())
            return 0;

        bool ok = context->device.GetEnableAscan(&ascan);
        ok = ok && context->device.GetAscanRequest(&request);
        ok = ok && context->device.GetAscanRequestFrequency(&frequency);
        ok = ok && context->device.GetEnableAscanMaximum(cycle, &maximum);
        ok = ok && context->device.GetEnableAscanMinimum(cycle, &minimum);
        ok = ok && context->device.GetEnableAscanSaturation(cycle, &saturation);
        ok = ok && context->device.GetTriggerMode(&trigger);

        bool unlock_ok = context->device.UnlockDevice();

        if (!ok || !unlock_ok)
            return 0;

        *ascan_enabled = ascan ? 1 : 0;
        *ascan_request = static_cast<int>(request);
        *ascan_request_frequency_hz = frequency;
        *maximum_enabled = maximum ? 1 : 0;
        *minimum_enabled = minimum ? 1 : 0;
        *saturation_enabled = saturation ? 1 : 0;
        *trigger_mode = static_cast<int>(trigger);

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


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
    double* reception_wedge_delay_s)
{
    if (!handle || cycle < 0 || capacity <= 0 ||
        !element_count || !gains_db || !focal_count ||
        !focal_tof_s || !ddf_enabled ||
        !emission_wedge_delay_s || !reception_wedge_delay_s)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        int gain_capacity = capacity;
        int gain_count = 0;
        int focal_capacity = capacity;
        int focal_actual = 0;
        bool ddf = false;
        double emission_wedge = 0.0;
        double reception_wedge = 0.0;

        if (!context->device.LockDevice())
            return 0;

        bool ok = context->device.GetReceptionGains(
            cycle,
            gain_capacity,
            &gain_count,
            gains_db
        );

        ok = ok && context->device.GetReceptionFocusing(
            cycle,
            focal_capacity,
            &focal_actual,
            focal_tof_s
        );

        ok = ok && context->device.GetEnableDDF(
            cycle,
            &ddf
        );

        ok = ok && context->device.GetEmissionWedgeDelay(
            cycle,
            1,
            &emission_wedge
        );

        ok = ok && context->device.GetReceptionWedgeDelay(
            cycle,
            1,
            &reception_wedge
        );

        bool unlock_ok = context->device.UnlockDevice();

        if (!ok || !unlock_ok)
            return 0;

        *element_count = gain_count;
        *focal_count = focal_actual;
        *ddf_enabled = ddf ? 1 : 0;
        *emission_wedge_delay_s = emission_wedge;
        *reception_wedge_delay_s = reception_wedge;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


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
    int* rx_focusing)
{
    if (!handle || cycle < 0 || capacity <= 0 ||
        !tx_element_count || !tx_delays_s ||
        !rx_element_count || !rx_focal_count ||
        !rx_delays_s || !rx_focusing)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        int tx_capacity = capacity;
        int tx_count = 0;

        int rx_element_capacity = capacity;
        int rx_focal_capacity = 1;
        int rx_count = 0;
        int focal_count = 0;

        enumFocusing focusing = eStandard;

        if (!context->device.LockDevice())
            return 0;

        bool ok = context->device.GetEmissionDelays(
            cycle,
            tx_capacity,
            &tx_count,
            tx_delays_s
        );

        ok = ok && context->device.GetReceptionDelays(
            cycle,
            capacity,
            rx_element_capacity,
            rx_focal_capacity,
            &rx_count,
            &focal_count,
            rx_delays_s
        );

        ok = ok && context->device.GetEnableDDF(
            cycle,
            &focusing
        );

        bool unlock_ok = context->device.UnlockDevice();

        if (!ok || !unlock_ok)
            return 0;

        *tx_element_count = tx_count;
        *rx_element_count = rx_count;
        *rx_focal_count = focal_count;
        *rx_focusing = static_cast<int>(focusing);

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}



// PA focal-law setter diagnostic

OEMPA_BRIDGE_API int __cdecl OEMPA_TestPAFocalLawSetters(
    void* handle,
    int cycle,
    int* status,
    int status_count)
{
    if (!handle || cycle < 0 || !status || status_count < 11)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    for (int i = 0; i < status_count; ++i)
        status[i] = 0;

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        // 16-element aperture: elements 0..15 enabled.
        DWORD aperture[g_iOEMPAApertureDWordCount] = {};
        aperture[0] = 0x0000FFFF;

        float widths[16];
        float tx_delays[16];
        float rx_gains[16];
        float rx_delays[16];

        for (int i = 0; i < 16; ++i)
        {
            widths[i] = 0.5e-6f;
            tx_delays[i] = 0.0f;
            rx_gains[i] = 0.0f;
            rx_delays[i] = 0.0f;
        }

        double tx_wedge = 0.0;
        double rx_wedge = 0.0;
        int focal_count = 1;
        double focal_tof[1] = {0.0};
        enumFocusing focusing = eStandard;

        // Acquisition is explicitly kept OFF before any configuration write.
        if (!context->device.LockDevice())
            return 0;

        if (!context->device.UnlockDevice(eAcqOff))
            return 0;

        if (!context->device.LockDevice())
            return 0;

        // Follow the vendor WriteHWFocalLaw ordering.
        status[0] = context->device.SetEmissionWedgeDelay(cycle, 1, tx_wedge) ? 1 : 0;
        status[1] = context->device.SetEmissionWidths(cycle, aperture, widths) ? 1 : 0;
        status[2] = context->device.SetEmissionDelays(cycle, aperture, tx_delays) ? 1 : 0;
        status[3] = context->device.SetEmissionEnable(cycle, aperture) ? 1 : 0;

        status[4] = context->device.SetReceptionWedgeDelay(cycle, 1, rx_wedge) ? 1 : 0;
        status[5] = context->device.SetReceptionGains(cycle, aperture, rx_gains) ? 1 : 0;
        status[6] = context->device.SetReceptionDelays(cycle, 16, focal_count, aperture, rx_delays) ? 1 : 0;
        status[7] = context->device.SetReceptionEnable(cycle, aperture) ? 1 : 0;
        status[8] = context->device.SetReceptionFocusing(cycle, focal_count, focal_tof) ? 1 : 0;
        status[9] = context->device.EnableDDF(cycle, focusing) ? 1 : 0;

        // Commit pending configuration while explicitly leaving acquisition OFF.
        status[10] = context->device.UnlockDevice(eAcqOff) ? 1 : 0;

        return 1;
    }
    catch (...)
    {
        try
        {
            context->device.UnlockDevice(eAcqOff);
        }
        catch (...)
        {
        }

        return 0;
    }
}


// Register A-scan callback

OEMPA_BRIDGE_API int __cdecl OEMPA_StartAscan(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        {
            std::lock_guard<std::mutex> lock(
                context->ascan_mutex
            );

            context->ascan_data.clear();
            context->ascan_data_bytes = 0;
            context->ascan_cycle = -1;
            context->ascan_point_count = 0;
            context->ascan_data_size = 0;
            context->ascan_signed = 0;
            context->ascan_bit_size = 0;
            context->ascan_received = false;
            context->callback_diagnostic = {};
            context->callback_diagnostic_ready = false;
            context->callback_buffers_preallocated = false;
            for (MultiAscanRecord& record : context->multi_ascan)
            {
                record.data.clear();
                record.data_bytes = 0;
                record.point_count = 0;
                record.data_size = 0;
                record.is_signed = 0;
                record.bit_size = 0;
                record.received = false;
            }
        }

        if (!context->device.SetAcquisitionParameter(
            context))
        {
            return 0;
        }

        if (!context->device.SetAcquisitionAscan_0x00010103(
            AcquisitionAscanCallback))
        {
            return 0;
        }

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// Prepare A-scan callback buffers while acquisition is OFF

OEMPA_BRIDGE_API int __cdecl OEMPA_PrepareAscanCallbackBuffers(
    void* handle,
    int buffer_capacity_bytes)
{
    if (!handle || buffer_capacity_bytes <= 0)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (context->multi_ascan.empty())
            return 0;

        const size_t capacity =
            static_cast<size_t>(buffer_capacity_bytes);

        context->ascan_data.resize(capacity);
        context->ascan_data_bytes = 0;
        context->ascan_received = false;
        context->callback_diagnostic = {};
        context->callback_diagnostic_ready = false;

        for (MultiAscanRecord& record : context->multi_ascan)
        {
            record.data.resize(capacity);
            record.data_bytes = 0;
            record.point_count = 0;
            record.data_size = 0;
            record.is_signed = 0;
            record.bit_size = 0;
            record.received = false;
        }

        context->callback_buffers_preallocated = true;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// A-scan callback diagnostic

OEMPA_BRIDGE_API int __cdecl OEMPA_GetAscanCallbackDiagnostic(
    void* handle,
    OEMPAAscanCallbackDiagnostic* diagnostic)
{
    if (!handle || !diagnostic)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (!context->callback_diagnostic_ready)
            return 0;

        *diagnostic = context->callback_diagnostic;
        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// A-scan state

OEMPA_BRIDGE_API int __cdecl OEMPA_HasAscan(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        return context->ascan_received ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// A-scan information

OEMPA_BRIDGE_API int __cdecl OEMPA_GetAscanInfo(
    void* handle,
    int* cycle,
    int* point_count,
    int* data_size,
    int* is_signed,
    int* bit_size)
{
    if (!handle ||
        !cycle ||
        !point_count ||
        !data_size ||
        !is_signed ||
        !bit_size)
    {
        return 0;
    }

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (!context->ascan_received)
            return 0;

        *cycle =
            context->ascan_cycle;

        *point_count =
            context->ascan_point_count;

        *data_size =
            context->ascan_data_size;

        *is_signed =
            context->ascan_signed;

        *bit_size =
            context->ascan_bit_size;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// Copy A-scan

OEMPA_BRIDGE_API int __cdecl OEMPA_CopyAscan(
    void* handle,
    void* buffer,
    int buffer_size)
{
    if (!handle || !buffer || buffer_size <= 0)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (!context->ascan_received ||
            context->ascan_data_bytes == 0)
        {
            return 0;
        }

        const int required_size =
            static_cast<int>(context->ascan_data_bytes);

        if (buffer_size < required_size)
            return -required_size;

        std::memcpy(
            buffer,
            context->ascan_data.data(),
            context->ascan_data_bytes
        );

        return required_size;
    }
    catch (...)
    {
        return 0;
    }
}

// Set multi-channel A-scan storage size

OEMPA_BRIDGE_API int __cdecl OEMPA_SetMultiAscanCycleCount(
    void* handle,
    int cycle_count)
{
    if (!handle || cycle_count <= 0)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        context->multi_ascan.clear();
        context->multi_ascan.resize(
            static_cast<size_t>(cycle_count)
        );
        context->callback_buffers_preallocated = false;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// Clear multi-channel A-scans

OEMPA_BRIDGE_API int __cdecl OEMPA_ClearMultiAscan(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        context->callback_total = context->callback_duplicates = context->callback_unexpected = context->callback_malformed = 0;
        context->callback_first_unexpected = -1;
        context->first_frame = FMCFirstFrame{};
        context->callback_order = CallbackOrder{};

        for (MultiAscanRecord& record : context->multi_ascan)
        {
            record.data.clear();
            record.data_bytes = 0;
            record.point_count = 0;
            record.data_size = 0;
            record.is_signed = 0;
            record.bit_size = 0;
            record.received = false;
            record.callback_count = 0;
        }

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// Read-only local callback acceptance statistics
OEMPA_BRIDGE_API int __cdecl OEMPA_GetCallbackRecordStats(
    void* handle, int capacity, int* counts, int* summary)
{
    if (!handle || !counts || !summary || capacity <= 0)
        return 0;
    OEMPAContext* context = static_cast<OEMPAContext*>(handle);
    try
    {
        std::lock_guard<std::mutex> lock(context->ascan_mutex);
        if (static_cast<size_t>(capacity) != context->multi_ascan.size())
            return 0;
        for (int cycle = 0; cycle < capacity; ++cycle)
            counts[cycle] = context->multi_ascan[cycle].callback_count;
        summary[0] = context->callback_total;
        summary[1] = context->callback_duplicates;
        summary[2] = context->callback_unexpected;
        summary[3] = context->callback_malformed;
        summary[4] = context->callback_first_unexpected;
        return 1;
    }
    catch (...)
    {
        return 0;
    }
}

// Multi-channel A-scan count

OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiAscanCount(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        int count = 0;

        for (const MultiAscanRecord& record : context->multi_ascan)
        {
            if (record.received)
                ++count;
        }

        return count;
    }
    catch (...)
    {
        return 0;
    }
}


// Multi-channel cycle state

OEMPA_BRIDGE_API int __cdecl OEMPA_HasMultiAscanCycle(
    void* handle,
    int cycle)
{
    if (!handle || cycle < 0)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (static_cast<size_t>(cycle) >= context->multi_ascan.size())
            return 0;

        return context->multi_ascan[cycle].received
            ? 1
            : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Multi-channel A-scan information

OEMPA_BRIDGE_API int __cdecl OEMPA_GetMultiAscanInfo(
    void* handle,
    int cycle,
    int* point_count,
    int* data_size,
    int* is_signed,
    int* bit_size)
{
    if (!handle ||
        cycle < 0 ||
        !point_count ||
        !data_size ||
        !is_signed ||
        !bit_size)
    {
        return 0;
    }

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (static_cast<size_t>(cycle) >= context->multi_ascan.size())
            return 0;

        MultiAscanRecord& record =
            context->multi_ascan[cycle];

        if (!record.received)
            return 0;

        *point_count = record.point_count;
        *data_size = record.data_size;
        *is_signed = record.is_signed;
        *bit_size = record.bit_size;

        return 1;
    }
    catch (...)
    {
        return 0;
    }
}


// Copy multi-channel A-scan

OEMPA_BRIDGE_API int __cdecl OEMPA_CopyMultiAscan(
    void* handle,
    int cycle,
    void* buffer,
    int buffer_size)
{
    if (!handle ||
        cycle < 0 ||
        !buffer ||
        buffer_size <= 0)
    {
        return 0;
    }

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        std::lock_guard<std::mutex> lock(
            context->ascan_mutex
        );

        if (static_cast<size_t>(cycle) >= context->multi_ascan.size())
            return 0;

        MultiAscanRecord& record =
            context->multi_ascan[cycle];

        if (!record.received || record.data_bytes == 0)
            return 0;

        const int required_size =
            static_cast<int>(record.data_bytes);

        if (buffer_size < required_size)
            return -required_size;

        std::memcpy(
            buffer,
            record.data.data(),
            record.data_bytes
        );

        return required_size;
    }
    catch (...)
    {
        return 0;
    }
}

// Enable acquisition

OEMPA_BRIDGE_API int __cdecl OEMPA_EnableAcquisition(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        AcquisitionOrderMarker marker(context, true);
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        if (!context->device.LockDevice())
            return 0;

        { std::lock_guard<std::mutex> lock(context->ascan_mutex); if (context->first_frame.active) context->fmc_timing.mark(FMCTiming::OnEnter, MonotonicTick()); }
        marker.success = context->device.UnlockDevice(eAcqOn);
        { std::lock_guard<std::mutex> lock(context->ascan_mutex); if (context->first_frame.active) context->fmc_timing.mark(FMCTiming::OnReturn, MonotonicTick()); }
        return marker.success ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


// Disable acquisition

OEMPA_BRIDGE_API int __cdecl OEMPA_DisableAcquisition(
    void* handle)
{
    if (!handle)
        return 0;

    OEMPAContext* context =
        static_cast<OEMPAContext*>(handle);

    try
    {
        AcquisitionOrderMarker marker(context, false);
        if (!TimedPreparationCall("DisableAcquisition.IsConnected", [&]() { return context->device.GetSWDevice()->IsConnected(); }))
            return 0;

        if (!TimedPreparationCall("DisableAcquisition.LockDevice", [&]() { return context->device.LockDevice(); }))
            return 0;

        { std::lock_guard<std::mutex> lock(context->ascan_mutex); if (context->first_frame.active) context->fmc_timing.mark(FMCTiming::OffEnter, MonotonicTick()); }
        marker.success = TimedPreparationCall("DisableAcquisition.UnlockDevice", [&]() { return context->device.UnlockDevice(eAcqOff); });
        { std::lock_guard<std::mutex> lock(context->ascan_mutex); if (context->first_frame.active) context->fmc_timing.mark(FMCTiming::OffReturn, MonotonicTick()); }
        return marker.success ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}

// Backup configuration

OEMPA_BRIDGE_API int __cdecl OEMPA_BackupConfiguration(
    void* handle,
    const wchar_t* file_path)
{
    if (!handle || !file_path)
        return 0;

    OEMPAContext* context = static_cast<OEMPAContext*>(handle);

    try
    {
        if (!context->device.GetSWDevice()->IsConnected())
            return 0;

        wchar_t backup_path[MAX_PATH];

        if (wcslen(file_path) >= MAX_PATH)
            return 0;

        wcscpy_s(
            backup_path,
            MAX_PATH,
            file_path
        );

        bool ok = OEMPA_ReadHWWriteFile(
            &context->device,
            g_iOEMPACycleCountMax,
            g_iOEMPAApertureElementCountMax,
            g_iOEMPAFocalCountMax,
            g_iOEMPADACCountMax,
            backup_path
        );

        return ok ? 1 : 0;
    }
    catch (...)
    {
        return 0;
    }
}


}
