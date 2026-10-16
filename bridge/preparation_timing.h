#pragma once
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>

// Per-worker, bounded observations. Never used by the acquisition callback.
struct PreparationTiming
{
    struct Entry { const char* name = nullptr; int64_t count = 0, total_ns = 0, max_ns = 0; };
    bool enabled = false;
    bool overflow = false;
    std::array<Entry, 64> entries = {};
    void add(const char* name, int64_t ns)
    {
        for (auto& entry : entries)
        {
            if (!entry.name) entry.name = name;
            if (std::strcmp(entry.name, name) != 0) continue;
            ++entry.count;
            entry.total_ns += ns;
            if (ns > entry.max_ns) entry.max_ns = ns;
            return;
        }
        overflow = true;
    }
};

struct PreparationCall
{
    PreparationTiming& profile;
    const char* name;
    std::chrono::steady_clock::time_point start;
    PreparationCall(PreparationTiming& value, const char* label) : profile(value), name(label), start(std::chrono::steady_clock::now()) {}
    ~PreparationCall() { profile.add(name, std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count()); }
};
