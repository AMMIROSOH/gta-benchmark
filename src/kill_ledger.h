#pragma once
#include <array>
#include <cstdint>
namespace sa_agent::actors {
class KillLedger {
    struct Slot { std::int32_t ref = -1; bool killed = false; };
    std::array<Slot, 4096> slots{};
public:
    void Reset() { for (auto& slot : slots) slot = {}; }
    void Observe(std::int32_t ref) {
        if (ref < 0 || static_cast<unsigned>(ref >> 8) >= slots.size()) return;
        auto& slot = slots[ref >> 8];
        if (slot.ref != ref) slot = {ref, false};
    }
    bool Register(std::int32_t ref, bool attributed) {
        if (!attributed || ref < 0 || static_cast<unsigned>(ref >> 8) >= slots.size()) return false;
        Observe(ref);
        auto& slot = slots[ref >> 8];
        if (slot.killed) return false;
        slot.killed = true;
        return true;
    }
};
}
