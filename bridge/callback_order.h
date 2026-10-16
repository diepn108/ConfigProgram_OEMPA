#pragma once

#include <array>
#include <cstdint>

// Local diagnostics only. Caller owns the callback mutex.
struct CallbackOrder
{
    static constexpr int callback_capacity = 512;
    static constexpr int marker_capacity = 64;
    static constexpr int columns = 10;
    enum Kind { Callback = 1, OnRequested, OnReturned, FirstCallback, UniqueComplete, FirstDuplicate, OffRequested, OffEntered, OffReturned, FinalObserved };
    using Event = std::array<int64_t, columns>;
    std::array<Event, callback_capacity + marker_capacity> events = {};
    std::array<int64_t, 2047> first = {};
    int required = 0, points = 0, size = 0, sign = 0, bits = 0;
    int stored = 0, callbacks_stored = 0, markers_stored = 0, unique = 0;
    int64_t order = 0, arrivals = 0, dropped_callbacks = 0, dropped_markers = 0;
    int64_t complete_order = 0, duplicate_order = 0, last_callback_order = 0;
    bool active = false;

    void reset(int count, int samples, int data_size, int is_signed, int bit_size)
    {
        *this = CallbackOrder{};
        required = count; points = samples; size = data_size; sign = is_signed; bits = bit_size;
        active = true;
    }

    int64_t append(int kind, int64_t arrival = 0, int cycle = -1, int samples = 0, int data_size = 0, int is_signed = 0, int bit_size = 0, int status = 0)
    {
        if (!active) return 0;
        const int64_t index = ++order;
        const bool callback = kind == Callback;
        if ((callback && callbacks_stored == callback_capacity) || (!callback && markers_stored == marker_capacity))
        {
            if (callback) ++dropped_callbacks; else ++dropped_markers;
            return index;
        }
        events[stored++] = {index, kind, arrival, cycle, samples, data_size, is_signed, bit_size, status, 0};
        if (callback) ++callbacks_stored; else ++markers_stored;
        return index;
    }

    void callback(int cycle, int samples, int data_size, int is_signed, int bit_size, bool valid)
    {
        if (!active) return;
        const bool expected = cycle >= 0 && cycle < required;
        const bool duplicate = expected && first[cycle] != 0;
        const bool malformed = !valid || samples != points || data_size != size || is_signed != sign || bit_size != bits;
        const int status = (malformed ? 1 : 0) | (!expected ? 2 : 0) | (duplicate ? 4 : 0);
        const int64_t index = append(Callback, ++arrivals, cycle, samples, data_size, is_signed, bit_size, status);
        last_callback_order = index;
        if (arrivals == 1) append(FirstCallback, arrivals, cycle);
        if (expected && !duplicate)
        {
            first[cycle] = index;
            if (++unique == required)
            {
                complete_order = index;
                append(UniqueComplete, arrivals, cycle);
            }
        }
        if (duplicate && duplicate_order == 0)
        {
            duplicate_order = index;
            append(FirstDuplicate, arrivals, cycle);
        }
    }
};
