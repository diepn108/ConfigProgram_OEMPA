#include "../bridge/callback_order.h"
#include <iostream>
#include <string>

// SDK-free executable exercises the same bookkeeping used by the real callback.
int main(int argc, char** argv)
{
    if (argc != 2) return 1;
    const std::string scenario = argv[1];
    CallbackOrder log;
    log.reset(256, 3001, 1, 1, 0);
    log.append(CallbackOrder::OnRequested);
    log.callback(0, 3001, 1, 1, 0, true);
    log.append(CallbackOrder::OnReturned);
    for (int cycle = 1; cycle < 256; ++cycle)
    {
        if (scenario == "early" && cycle == 12) log.callback(0, 3001, 1, 1, 0, true);
        log.callback(cycle, 3001, 1, 1, 0, true);
    }
    log.append(CallbackOrder::OffRequested);
    log.append(CallbackOrder::OffEntered);
    if (scenario == "late") for (int cycle = 0; cycle < 28; ++cycle) log.callback(cycle, 3001, 1, 1, 0, true);
    if (scenario == "overflow") for (int cycle = 0; cycle < 600; ++cycle) log.callback(cycle % 256, 3001, 1, 1, 0, true);
    if (scenario == "malformed")
    {
        log.callback(-1, 0, 0, 0, 0, false);
        log.callback(0, 3000, 1, 1, 0, true);
        log.callback(0, 3001, 2, 0, 1, true);
    }
    log.append(CallbackOrder::OffReturned);
    log.append(CallbackOrder::FinalObserved, log.arrivals);
    if (scenario == "markers") for (int i = 0; i < 100; ++i) log.append(CallbackOrder::FinalObserved, log.arrivals);
    std::cout << "{\"summary\":[" << log.stored << ',' << log.required << ',' << log.arrivals << ',' << log.dropped_callbacks << ',' << log.dropped_markers << ',' << log.complete_order << ',' << log.duplicate_order << ',' << log.last_callback_order << ',' << log.order << "],\"first\":[";
    for (int i = 0; i < 2047; ++i) std::cout << (i ? "," : "") << log.first[i];
    std::cout << "],\"rows\":[";
    for (int i = 0; i < log.stored * 10; ++i) std::cout << (i ? "," : "") << log.events[i / 10][i % 10];
    std::cout << "]}";
}
