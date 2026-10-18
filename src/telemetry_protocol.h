#pragma once
#include <Windows.h>
#include <cstddef>
#include <cstdint>

namespace sa_agent {
inline constexpr wchar_t kMappingName[] = L"Local\\SAAgent.Telemetry.v1";
inline constexpr std::uint32_t kMagic = 0x54414153; // "SAAT" in little endian
inline constexpr std::uint32_t kSchema = 1;
enum Flags : std::uint32_t {
    PlayerReady = 1, InVehicle = 2, UserPaused = 4, CodePaused = 8,
    SampleError = 16, Stopping = 32
};

// Fixed-width, pointer-free ABI shared by the x86 game and x64 Python.
#pragma pack(push, 4)
struct Snapshot {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, process_id, game_version;
    std::uint64_t sampled_at_ms;
    std::uint32_t game_time_ms, flags, sample_count, error_count;
    float x, y, z, heading_radians, health, max_health, armour;
    std::int32_t money;
    std::uint32_t wanted_level;
    std::int32_t vehicle_model;
    float vehicle_health, speed_mps, velocity_x, velocity_y, velocity_z;
    std::uint32_t clock_hour, clock_minute, clock_second;
    std::int32_t weather_old, weather_new, weapon_type;
    std::uint32_t ammo_total, interior, sdk_version, reserved[4];
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 160);
static_assert(offsetof(Snapshot, sampled_at_ms) == 24);
static_assert(offsetof(Snapshot, x) == 48);
static_assert(offsetof(Snapshot, sdk_version) == 140);
} // namespace sa_agent
