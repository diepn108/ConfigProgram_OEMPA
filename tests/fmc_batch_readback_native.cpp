#include "../bridge/fmc_batch_readback.h"
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct Traits
{
    using BitSize = int; using Rectification = int; using Compression = int; using Filter = int;
    using Word = uint32_t;
    struct Decimation { unsigned char byte[8] = {}; };
};
struct FakeDevice
{
    bool held = false;
    int locks = 0, unlocks = 0, flushes = 0, reads = 0, normal_cycles = 0, multi_cycles = 0, tx_cycles = 0;
    std::string failure;
    std::vector<std::function<void()>> pending;
    bool LockDevice(int state) { assert(state == 0 && !held); ++locks; if (failure == "lock") return false; held = true; return true; }
    bool Flush() { assert(held); ++flushes; if (failure == "flush") return false; drain(); return true; }
    void drain() { for (const auto& action : pending) action(); pending.clear(); }
    bool UnlockDevice(int state) { assert(state == 0 && held); ++unlocks; if (failure == "unlock_pending") { held = false; return false; } drain(); held = false; if (failure == "unlock_throw") throw std::runtime_error("unlock"); return failure != "unlock"; }
    template<class Function> bool queue(Function action) { assert(held); ++reads; pending.emplace_back(action); return true; }
    bool GetCycleCount(int* value) { return queue([=]() { *value = failure == "topology" ? 1 : 256; }); }
    bool GetEnableMultiHWChannel(bool* value) { return queue([=]() { *value = true; }); }
    bool GetGainDigital(int cycle, double* value) { ++normal_cycles; return queue([=]() { *value = 0; }); }
    bool GetGainAnalog(int cycle, float* value) { if (failure == "throw" && cycle == 17) throw std::runtime_error("getter"); if (failure == "getter" && cycle == 17) return false; return queue([=]() { *value = 20; }); }
    bool GetBeamCorrection(int cycle, float* value) { return queue([=]() { *value = 0; }); }
    bool GetAscanBitSize(int* value) { return queue([=]() { *value = 0; }); }
    bool GetAscanRectification(int cycle, int* value) { return queue([=]() { *value = 0; }); }
    bool GetAscanStart(int cycle, double* value) { return queue([=]() { *value = 0; }); }
    bool GetAscanRange(int cycle, double* range, int* compression, long* count, long* factor) { return queue([=]() { *range = 30e-6; *compression = 0; *count = 3001; *factor = 256; }); }
    bool GetFilterIndex(int cycle, int* value) { return queue([=]() { *value = 1; }); }
    bool GetTimeSlot(int cycle, double* value) { return queue([=]() { *value = .002; }); }
    bool GetEmissionEnable(int cycle, uint32_t* value) { return queue([=]() { value[0] = cycle % 16 == 0 ? 1u << (cycle / 16) : 0; }); }
    bool GetReceptionEnable(int cycle, uint32_t* value) { return queue([=]() { value[0] = 1u << (cycle % 16); }); }
    bool GetEnableMultiHWChannelAcquisition(int cycle, bool* value) { ++multi_cycles; return queue([=]() { if (failure == "functional_flags") *value = cycle % 16 == 0; }); }
    bool GetMultiHWChannelAcqWriteStart(int cycle, int& capacity, int* count, float* value) { assert(capacity == 16); return queue([=]() { *count = 16; for (int i = 0; i < 16; ++i) value[i] = 0; }); }
    bool GetMultiHWChannelAcqDecimation(int cycle, Traits::Decimation* value) { return queue([=]() { value->byte[0] = static_cast<unsigned char>(cycle); }); }
    bool GetEmissionWidths(int cycle, int& capacity, int* count, float* value) { ++tx_cycles; assert(capacity == 16); return queue([=]() { if (failure == "invalid_count") { *count = 17; return; } if (failure != "unreadable_tx") { *count = 1; value[0] = .5e-6f; } }); }
    bool GetEmissionDelays(int cycle, int& capacity, int* count, float* value) { assert(capacity == 16); return queue([=]() { if (failure != "unreadable_tx") { *count = 1; value[0] = 0; } }); }
    bool GetSamplingFrequency(int compression, long factor, double& value) { assert(!held && pending.empty()); value = 100e6; return failure != "sampling"; }
    bool GetElementEnable(int element, const uint32_t* words, bool& value) { assert(!held); value = (words[0] & (1u << element)) != 0; return true; }
};
int main(int argc, char** argv)
{
    assert(argc == 2);
    FakeDevice device; device.failure = argv[1];
    FMCBatchStorage<Traits> storage;
    std::array<int, 256> base = {};
    for (int cycle = 0; cycle < 256; cycle += 16) base[cycle] = 1;
    auto observe = [](const char*, auto call) { return call(); };
    bool accepted = false;
    try { accepted = ReadFMCBatch(device, storage, base, observe, 0); } catch (const std::runtime_error&) {}
    const bool expected = device.failure == "exact" || device.failure == "unreadable_tx" || device.failure == "functional_flags";
    assert(accepted == expected);
    assert(!device.held);
    if (device.failure == "unlock_pending")
    {
        assert(!device.pending.empty());
        // Production retains the owner through SDK teardown after uncertain unlock.
        device.drain();
        assert(storage.cycles[240].tx.width_count == 1);
    }
    assert(device.pending.empty());
    assert(device.locks == 1 && device.unlocks == (device.failure == "lock" ? 0 : 1));
    if (accepted)
    {
        assert(device.flushes == 2 && device.normal_cycles == 256 && device.multi_cycles == 256);
        assert(device.tx_cycles == (device.failure == "functional_flags" ? 32 : 16));
        assert(device.reads == (device.failure == "functional_flags" ? 3650 : 3618));
        for (int cycle = 0; cycle < 256; ++cycle)
        {
            const auto& item = storage.cycles[cycle];
            assert(item.normal.cycle == cycle && item.normal.point_count == 3001 && item.normal.sampling_hz == 100e6);
            assert(item.normal.gain_analog_db == 20 && item.normal.filter_index == 1);
            assert(item.normal.start_s == 0 && item.normal.range_s == 30e-6 && item.normal.time_slot_s == .002);
            assert(item.normal.point_factor == 256 && item.normal.bit_size == 0 && item.normal.rectification == 0 && item.normal.compression_type == 0);
            for (int element = 0; element < 16; ++element)
            {
                assert(item.normal.tx_enabled[element] == (cycle % 16 == 0 && element == cycle / 16));
                assert(item.normal.rx_enabled[element] == (element == cycle % 16));
            }
            assert(item.multi.start_count == 16 && item.multi.multi_decimation_bytes[0] == static_cast<unsigned char>(cycle));
            if (base[cycle]) assert(item.tx.width_count == (device.failure == "unreadable_tx" ? -1 : 1));
        }
    }
    std::cout << "passed " << argv[1] << "\n";
}
