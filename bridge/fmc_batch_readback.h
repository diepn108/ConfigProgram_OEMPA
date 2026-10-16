#pragma once
#include "oempa_bridge.h"
#include <array>
#include <cstring>

// All asynchronous output pointers and count/capacity references outlive OFF unlock.
template<class Traits> struct FMCBatchStorage
{
    struct Cycle
    {
        OEMPACycleSnapshot normal = {};
        OEMPAExtendedCycleSnapshot multi = {}, tx = {};
        typename Traits::BitSize bits = {};
        typename Traits::Rectification rectification = {};
        typename Traits::Compression compression = {};
        typename Traits::Filter filter = {};
        typename Traits::Decimation decimation = {};
        std::array<typename Traits::Word, 4> emission = {}, reception = {};
        bool hw = false;
        int start_capacity = 16, width_capacity = 16, delay_capacity = 16;
        int tx_width_capacity = 16, tx_delay_capacity = 16;
        Cycle() { multi.width_count = multi.tx_delay_count = tx.width_count = tx.tx_delay_count = -1; }
    };
    int cycle_count = -1;
    bool multichannel = false;
    std::array<Cycle, 256> cycles;
};

// A failed/throwing getter must still attempt OFF unlock with every output alive.
// No retries after an uncertain SDK failure, and no output is published on failure.
template<class Unlock> struct OFFReadbackCleanup
{
    Unlock unlock;
    bool held = true;
    explicit OFFReadbackCleanup(Unlock value) : unlock(value) {}
    bool finish() { held = false; return unlock(); }
    ~OFFReadbackCleanup() { if (held) { try { finish(); } catch (...) {} } }
};

template<class Device, class Storage, class Observe, class State>
bool ReadFMCBatch(Device& device, Storage& storage, const std::array<int, 256>& base, Observe observe, State off)
{
    if (!observe("FMCBatch.LockDevice", [&]() { return device.LockDevice(off); })) return false;
    auto unlock = [&]() { return observe("FMCBatch.UnlockDevice", [&]() { return device.UnlockDevice(off); }); };
    OFFReadbackCleanup<decltype(unlock)> cleanup(unlock);
#define FMC_READ(method, ...) if (!observe("FMCBatch." #method, [&]() { return device.method(__VA_ARGS__); })) return false
    FMC_READ(GetCycleCount, &storage.cycle_count);
    FMC_READ(GetEnableMultiHWChannel, &storage.multichannel);
    FMC_READ(Flush); // Counts/flags are asynchronous; inspect only after completion.
    if (storage.cycle_count != 256 || !storage.multichannel) return false;
    for (int cycle = 0; cycle < 256; ++cycle)
    {
        auto& item = storage.cycles[cycle];
        auto& normal = item.normal;
        normal.cycle = cycle;
        FMC_READ(GetGainDigital, cycle, &normal.gain_digital_db);
        FMC_READ(GetGainAnalog, cycle, &normal.gain_analog_db);
        FMC_READ(GetBeamCorrection, cycle, &normal.beam_correction_db);
        FMC_READ(GetAscanBitSize, &item.bits);
        FMC_READ(GetAscanRectification, cycle, &item.rectification);
        FMC_READ(GetAscanStart, cycle, &normal.start_s);
        FMC_READ(GetAscanRange, cycle, &normal.range_s, &item.compression, &normal.point_count, &normal.point_factor);
        FMC_READ(GetFilterIndex, cycle, &item.filter);
        FMC_READ(GetTimeSlot, cycle, &normal.time_slot_s);
        FMC_READ(GetEmissionEnable, cycle, item.emission.data());
        FMC_READ(GetReceptionEnable, cycle, item.reception.data());
        FMC_READ(GetEnableMultiHWChannelAcquisition, cycle, &item.hw);
        FMC_READ(GetMultiHWChannelAcqWriteStart, cycle, item.start_capacity, &item.multi.start_count, item.multi.multi_starts_s);
        FMC_READ(GetMultiHWChannelAcqDecimation, cycle, &item.decimation);
    }
    FMC_READ(Flush); // Any conditional reads must use completed flags, not seeds.
    for (int cycle = 0; cycle < 256; ++cycle)
    {
        auto& item = storage.cycles[cycle];
        if (item.hw)
        {
            FMC_READ(GetEmissionWidths, cycle, item.width_capacity, &item.multi.width_count, item.multi.widths_s);
            FMC_READ(GetEmissionDelays, cycle, item.delay_capacity, &item.multi.tx_delay_count, item.multi.tx_delays_s);
        }
        if (base[cycle])
        {
            FMC_READ(GetEmissionWidths, cycle, item.tx_width_capacity, &item.tx.width_count, item.tx.widths_s);
            FMC_READ(GetEmissionDelays, cycle, item.tx_delay_capacity, &item.tx.tx_delay_count, item.tx.tx_delays_s);
        }
    }
    if (!cleanup.finish()) return false;
    // Only local decoding/derived sampling after all pending pointer writes finish.
    for (auto& item : storage.cycles)
    {
        auto& normal = item.normal;
        normal.bit_size = static_cast<int>(item.bits);
        normal.rectification = static_cast<int>(item.rectification);
        normal.compression_type = static_cast<int>(item.compression);
        normal.filter_index = static_cast<int>(item.filter);
        FMC_READ(GetSamplingFrequency, item.compression, normal.point_factor, normal.sampling_hz);
        for (int element = 0; element < 16; ++element)
        {
            bool tx = false, rx = false;
            if (!device.GetElementEnable(element, item.emission.data(), tx) || !device.GetElementEnable(element, item.reception.data(), rx)) return false;
            normal.tx_enabled[element] = tx ? 1 : 0;
            normal.rx_enabled[element] = rx ? 1 : 0;
        }
        item.multi.hw_acquisition = item.hw ? 1 : 0;
        std::memcpy(item.multi.multi_decimation_bytes, item.decimation.byte, sizeof(item.multi.multi_decimation_bytes));
        for (const auto* extended : {&item.multi, &item.tx})
            if (extended->width_count < -1 || extended->width_count > 16 || extended->tx_delay_count < -1 || extended->tx_delay_count > 16 || extended->start_count < 0 || extended->start_count > 16) return false;
    }
#undef FMC_READ
    return true;
}
