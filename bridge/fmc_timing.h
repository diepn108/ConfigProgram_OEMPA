#pragma once
#include <array>
#include <cstdint>

// Caller owns the existing storage mutex. First observation wins, no allocation.
struct FMCTiming
{
    enum Mark { OnEnter, OnReturn, FirstCallback, FrameComplete, OffRequest, OffEnter, OffReturn, Count };
    std::array<int64_t, Count> ticks = {};
    void mark(int index, int64_t value) { if (!ticks[index]) ticks[index] = value; }
};
