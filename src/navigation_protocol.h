#pragma once
#include <Windows.h>
#include <cstdint>

namespace sa_agent {
inline constexpr wchar_t kNavigationName[] = L"Local\\SAAgent.Navigation.v1";
inline constexpr std::uint32_t kNavigationMagic = 0x4E414153;
inline constexpr int kNavigationNodes = 96, kNavigationRays = 16;
#pragma pack(push, 4)
struct NavigationNode {
    std::uint32_t reference, flags; // road=1, clear from player=2
    float x, y, z, width;
    std::uint32_t links[16]; // native node references; UINT_MAX is unused
};
struct VehicleGeometry {
    std::int32_t reference;
    std::uint32_t flags; // openable=1, door clear=2, front clear=4, busy=8, valid door=16
    float door_x, door_y, door_z, velocity_x, velocity_y;
    float right_x, right_y, forward_x, forward_y;
    float half_width, front_extent, rear_extent;
    float front_x, front_y, front_z;
    std::uint32_t door_anchors[3], front_anchors[3];
};
struct NavigationRay { float clearance_m, ground_delta_m; };
struct NavigationSnapshot {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, process_id, capabilities;
    std::uint64_t sampled_at_ms;
    std::uint32_t node_count, vehicle_count, ray_count, entering_vehicle;
    float camera_orientation;
    std::uint32_t reserved[3];
    NavigationNode nodes[kNavigationNodes];
    VehicleGeometry vehicles[16];
    NavigationRay rays[kNavigationRays];
};
#pragma pack(pop)
static_assert(sizeof(NavigationNode) == 88);
static_assert(sizeof(VehicleGeometry) == 92);
static_assert(sizeof(NavigationSnapshot) == 10112);
}
