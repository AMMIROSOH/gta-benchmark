#pragma once
#include <Windows.h>
#include <cstdint>

namespace sa_agent {
inline constexpr wchar_t kWorldName[] = L"Local\\SAAgent.World.v1";
inline constexpr wchar_t kControlName[] = L"Local\\SAAgent.Control.v1";
inline constexpr std::uint32_t kWorldMagic = 0x57414153;
inline constexpr std::uint32_t kControlMagic = 0x43414153;
inline constexpr int kMaxNearbyVehicles = 16;

#pragma pack(push, 4)
struct NearbyVehicle {
    std::int32_t reference, model, vehicle_class;
    std::uint32_t flags; // occupied=1, moving=2, player's current vehicle=4
    float x, y, z, heading, health, speed_mps, distance_m;
};
struct WorldSnapshot {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, process_id, capabilities;
    std::uint64_t sampled_at_ms;
    std::int32_t player_vehicle_ref, player_vehicle_class;
    std::uint32_t is_driver, render_width, render_height, fps_cap;
    std::uint32_t last_applied_request, nearby_count, obstacle_mask;
    float camera_forward_x, camera_forward_y;
    std::uint32_t reserved[5];
    NearbyVehicle vehicles[kMaxNearbyVehicles];
};
struct ControlCommand {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, owner_pid, request_id;
    std::uint64_t issued_at_ms, expires_at_ms;
    // Actions 18-20 use reserved[0..2] as IEEE-754 float goal X/Y/stop radius.
    std::uint32_t action_id, enabled, reserved[4];
};
#pragma pack(pop)
static_assert(sizeof(NearbyVehicle) == 44);
static_assert(sizeof(WorldSnapshot) == 800);
static_assert(sizeof(ControlCommand) == 64);
} // namespace sa_agent
