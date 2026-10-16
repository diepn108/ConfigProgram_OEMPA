#include "../bridge/fmc_first_frame.h"
#include "../bridge/fmc_timing.h"
#include "../bridge/preparation_timing.h"
#include <cassert>
#include <cstdio>
#include "../bridge/callback_order.h"
#include <array>
#include <cstring>
#include <iostream>
#include <string>

// SDK-free: the production admission gate controls preallocated record copies.
int main(int argc, char** argv)
{
    if (argc != 2) return 1;
    const std::string scenario = argv[1];
    FMCTiming timing;
    timing.mark(FMCTiming::FirstCallback, 101);
    timing.mark(FMCTiming::FirstCallback, 999);
    timing.mark(FMCTiming::FrameComplete, 256);
    assert(timing.ticks[FMCTiming::FirstCallback] == 101);
    assert(timing.ticks[FMCTiming::FrameComplete] == 256);
    PreparationTiming preparation;
    preparation.add("LockDevice", 100);
    preparation.add("LockDevice", 250);
    assert(preparation.entries[0].count == 2 && preparation.entries[0].total_ns == 350 && preparation.entries[0].max_ns == 250);
    std::array<std::array<char, 20>, 65> labels = {};
    for (int i = 0; i < 65; ++i)
    {
        std::snprintf(labels[i].data(), 20, "getter%d", i);
        preparation.add(labels[i].data(), 1);
    }
    assert(preparation.overflow && preparation.entries[0].count == 2);
    // Existing entries still aggregate after capacity is reached.
    preparation.add("LockDevice", 50);
    assert(preparation.entries[0].count == 3 && preparation.entries[0].total_ns == 400);
    try
    {
        PreparationCall scope(preparation, "LockDevice");
        throw 1;
    }
    catch (int) {}
    assert(preparation.entries[0].count == 4);
    FMCFirstFrame frame;
    frame.reset(7, 1, 1, 0);
    CallbackOrder log;
    log.reset(256, 7, 1, 1, 0);
    std::array<std::array<signed char, 7>, 256> records = {};
    auto callback = [&](int cycle, bool post, bool valid = true, int points = 7, int size = 1, int sign = 1, int bits = 0)
    {
        std::array<signed char, 7> data;
        for (int n = 0; n < 7; ++n) data[n] = post ? -100 : static_cast<signed char>(cycle % 101 + n);
        log.callback(cycle, points, size, sign, bits, valid);
        if (frame.admit(cycle, points, size, sign, bits, valid))
            std::memcpy(records[cycle].data(), data.data(), data.size());
    };
    log.append(CallbackOrder::OnRequested);
    for (int cycle = 0; cycle < 256; ++cycle)
    {
        if (cycle == 1) log.append(CallbackOrder::OnReturned);
        if (scenario == "missing" && cycle == 173) continue;
        if (scenario == "duplicate" && cycle == 21) callback(0, false);
        if (scenario == "unexpected" && cycle == 42) callback(256, false);
        if (scenario == "order" && cycle == 42) callback(43, false);
        if (scenario == "malformed" && cycle == 42) { callback(cycle, false, false); continue; }
        if (scenario == "count" && cycle == 42) { callback(cycle, false, true, 6); continue; }
        if (scenario == "size" && cycle == 42) { callback(cycle, false, true, 7, 2); continue; }
        if (scenario == "sign" && cycle == 42) { callback(cycle, false, true, 7, 1, 0); continue; }
        if (scenario == "bits" && cycle == 42) { callback(cycle, false, true, 7, 1, 1, 1); continue; }
        callback(cycle, false);
    }
    log.append(CallbackOrder::OffRequested);
    log.append(CallbackOrder::OffEntered);
    int post = scenario == "late25" ? 25 : scenario == "late26" ? 26 : scenario == "overflow" ? 600 : 0;
    for (int i = 0; i < post; ++i) callback(i % 256, true);
    if (scenario == "postbad") callback(256, true, false);
    log.append(CallbackOrder::OffReturned);
    log.append(CallbackOrder::FinalObserved, log.arrivals);
    std::cout << "{\"frame\":[" << frame.accepted << ',' << frame.complete() << ',' << frame.error << ',' << frame.error_cycle << ',' << frame.arrivals << ',' << frame.completion_arrival << ',' << frame.first_post_arrival << ',' << frame.post << ',' << frame.pre_duplicates << ',' << frame.pre_unexpected << ',' << frame.pre_malformed << ',' << frame.pre_out_of_order << ',' << frame.post_unexpected << ',' << frame.post_malformed << "],\"raw\":[";
    for (int i = 0; i < 256 * 7; ++i) std::cout << (i ? "," : "") << static_cast<int>(records[i / 7][i % 7]);
    std::cout << "],\"summary\":[" << log.stored << ',' << log.required << ',' << log.arrivals << ',' << log.dropped_callbacks << ',' << log.dropped_markers << ',' << log.complete_order << ',' << log.duplicate_order << ',' << log.last_callback_order << ',' << log.order << "],\"first\":[";
    for (int i = 0; i < 2047; ++i) std::cout << (i ? "," : "") << log.first[i];
    std::cout << "],\"rows\":[";
    for (int i = 0; i < log.stored * 10; ++i) std::cout << (i ? "," : "") << log.events[i / 10][i % 10];
    std::cout << "]}";
}
