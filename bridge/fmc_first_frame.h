#pragma once

#include <cstdint>

// Caller owns the storage mutex. No allocation, device control or file I/O.
struct FMCFirstFrame
{
    enum Error { None = 0, Malformed, Unexpected, Duplicate, OutOfOrder };
    bool active = false;
    int accepted = 0, error = None, error_cycle = -1;
    int points = 0, size = 0, sign = 0, bits = 0;
    int64_t arrivals = 0, completion_arrival = 0, first_post_arrival = 0;
    int64_t post = 0, pre_duplicates = 0, pre_unexpected = 0, pre_malformed = 0, pre_out_of_order = 0;
    int64_t post_unexpected = 0, post_malformed = 0;

    bool complete() const { return accepted == 256 && error == None; }

    void reset(int samples, int data_size, int is_signed, int bit_size)
    {
        *this = FMCFirstFrame{};
        active = true; points = samples; size = data_size; sign = is_signed; bits = bit_size;
    }

    bool admit(int cycle, int samples, int data_size, int is_signed, int bit_size, bool valid)
    {
        if (!active) return true;
        ++arrivals;
        const bool malformed = !valid || samples != points || data_size != size || is_signed != sign || bit_size != bits;
        const bool unexpected = cycle < 0 || cycle >= 256;
        if (complete())
        {
            if (++post == 1) first_post_arrival = arrivals;
            if (unexpected) ++post_unexpected;
            if (malformed) ++post_malformed;
            return false; // Existing first-frame record storage is now immutable.
        }
        if (error != None) return false;
        if (malformed) { error = Malformed; ++pre_malformed; }
        else if (unexpected) { error = Unexpected; ++pre_unexpected; }
        else if (cycle < accepted) { error = Duplicate; ++pre_duplicates; }
        else if (cycle != accepted) { error = OutOfOrder; ++pre_out_of_order; }
        if (error != None) { error_cycle = cycle; return false; }
        if (++accepted == 256) completion_arrival = arrivals;
        return true;
    }
};
