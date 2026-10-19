#pragma once
#include <cstdint>
namespace sa_agent::actors {
inline constexpr wchar_t kName[] = L"Local\\SAAgent.Actors.v1";
inline constexpr std::uint32_t kMagic = 0x50414153;
#pragma pack(push, 4)
struct Ped {
    std::int32_t reference, model, state; std::uint32_t flags;
    float x, y, z, health, armour, heading;
};
struct Pickup {
    std::uint32_t reference; std::int32_t model; std::uint32_t type, amount;
    float x, y, z;
};
struct Kill {
    std::uint32_t event_id; std::int32_t victim_reference, weapon;
    std::uint32_t flags; // 1: player ped; 2: player's vehicle; 4: headshot
    std::uint64_t occurred_at_ms; float x, y, z;
};
struct Weapon { std::int32_t type; std::uint32_t ammo, slot; };
struct Snapshot {
    std::int32_t sequence;
    std::uint32_t magic, schema, byte_size, process_id, capabilities;
    std::uint64_t sampled_at_ms;
    std::uint32_t latest_event_id, ped_count, pickup_count, event_count, selected_slot, reserved;
    Ped peds[32]; Pickup pickups[32]; Kill events[128]; Weapon weapons[13];
};
#pragma pack(pop)
static_assert(sizeof(Ped) == 40 && sizeof(Pickup) == 28 && sizeof(Kill) == 36);
static_assert(sizeof(Snapshot) == 6996);
void Initialize();
void Publish();
}
