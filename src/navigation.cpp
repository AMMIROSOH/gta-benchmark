#include "navigation.h"
#include "navigation_protocol.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <vector>
#include "CCarEnterExit.h"
#include "CCamera.h"
#include "CColModel.h"
#include "CPedIntelligence.h"
#include "CPools.h"
#include "CPathFind.h"
#include "CWorld.h"
#include "common.h"

namespace sa_agent::navigation {
namespace {
NavigationSnapshot* shared = nullptr;
HANDLE mapping = nullptr;
std::uint64_t last_publish = 0;
constexpr auto unused = std::numeric_limits<std::uint32_t>::max();
bool Clear(const CVector& from, const CVector& to) {
    return CWorld::GetIsLineOfSightClear(from, to, true, false, false, true, true, false, false);
}
std::uint32_t Ref(const CNodeAddress& address) { return (address.Region << 16) | address.Index; }
float Distance2(const CVector& a, const CVector& b) {
    const float x = a.x - b.x, y = a.y - b.y;
    return x*x + y*y;
}
void Anchors(const NavigationSnapshot& value, const CVector& goal, std::uint32_t* out, bool road) {
    std::fill(out, out + 3, unused);
    std::vector<std::pair<float, unsigned int>> candidates;
    for (unsigned int i = 0; i < value.node_count; ++i) {
        const auto& node = value.nodes[i];
        const CVector pos(node.x, node.y, node.z);
        float d = Distance2(pos, goal);
        if (d <= 225 && std::abs(pos.z - goal.z) < 3.0f)
            candidates.emplace_back(d * (road && (node.flags & 1) ? 0.65f : 1.0f), i);
    }
    std::sort(candidates.begin(), candidates.end());
    unsigned int found = 0;
    for (const auto& candidate : candidates) {
        const auto& node = value.nodes[candidate.second];
        if (Clear(CVector(node.x, node.y, node.z + 0.7f), CVector(goal.x, goal.y, goal.z + 0.7f))) {
            out[found++] = node.reference;
            if (found == 3) break;
        }
    }
}
}

void Initialize() {
    mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                sizeof(NavigationSnapshot), kNavigationName);
    if (mapping) shared = static_cast<NavigationSnapshot*>(
        MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(NavigationSnapshot)));
    if (shared) std::memset(shared, 0, sizeof(*shared));
}

void Publish(const WorldSnapshot& world) {
    auto* player = FindPlayerPed(0);
    if (!shared || !player) return;
    const auto now = GetTickCount64();
    if (now-last_publish < 200) return; // bounded 5 Hz geometry work, independent of rendering
    last_publish = now;
    NavigationSnapshot value{};
    value.magic = kNavigationMagic; value.schema = 1; value.byte_size = sizeof(value);
    value.process_id = GetCurrentProcessId(); value.capabilities = 3; // geometry + world pad goals
    value.sampled_at_ms = now; value.camera_orientation = TheCamera.m_fOrientation;
    value.entering_vehicle = player->m_ePedState == PEDSTATE_ENTER_CAR ||
        (player->m_pIntelligence && player->m_pIntelligence->IsPedGoingForCarDoor());
    const auto origin = player->GetPosition();
    const CVector eye(origin.x, origin.y, origin.z + 0.55f);
    std::vector<std::pair<float, CPathNode*>> candidates;
    for (int area = 0; area < NUM_PATH_MAP_AREAS; ++area) {
        auto* nodes = ThePaths.m_pPathNodes[area];
        const auto count = ThePaths.m_dwNumNodes[area];
        if (!nodes || count > 65535) continue;
        for (unsigned int i = 0; i < count; ++i) {
            auto& node = nodes[i];
            if (node.WaterNode || node.SwitchedOff || node.InteriorNode || !node.NumberAdjNodes) continue;
            const auto pos = node.GetNodeCoors();
            const auto distance = Distance2(origin, pos);
            if (distance < 90*90 && std::abs(pos.z - origin.z) < 4.0f)
                candidates.emplace_back(distance, &node);
        }
    }
    const auto count = std::min(candidates.size(), static_cast<size_t>(kNavigationNodes));
    std::partial_sort(candidates.begin(), candidates.begin() + count, candidates.end(),
        [](const auto& a, const auto& b) { return a.first < b.first; });
    value.node_count = static_cast<unsigned int>(count);
    for (unsigned int i = 0; i < count; ++i) {
        const auto* source = candidates[i].second;
        auto& node = value.nodes[i];
        const auto pos = const_cast<CPathNode*>(source)->GetNodeCoors();
        node.reference = Ref(source->Address);
        node.x = pos.x; node.y = pos.y; node.z = pos.z; node.width = source->Width / 16.0f;
        const auto area = source->Address.Region;
        node.flags = source->Address.Index < ThePaths.m_dwNumVehicleNodes[area] ? 1u : 0u;
        if (Clear(eye, CVector(pos.x, pos.y, pos.z + 0.7f))) node.flags |= 2;
        std::fill(std::begin(node.links), std::end(node.links), unused);
        auto* links = ThePaths.m_pNodeLinks[area];
        if (links) for (int j = 0; j < source->NumberAdjNodes; ++j) {
            const unsigned int index = static_cast<unsigned short>(source->IndexAdjacentNodes) + j;
            if (index < ThePaths.m_dwNumAddresses[area]) node.links[j] = Ref(links[index]);
        }
    }
    // Connect the pedestrian and road graphs only where nearby geometry is clear.
    for (unsigned int i = 0; i < count; ++i) for (unsigned int j = i + 1; j < count; ++j) {
        auto& a = value.nodes[i]; auto& b = value.nodes[j];
        if ((a.flags & 1) == (b.flags & 1) || std::abs(a.z - b.z) > 1.5f ||
            Distance2(CVector(a.x,a.y,a.z), CVector(b.x,b.y,b.z)) > 49.0f) continue;
        if (!Clear(CVector(a.x,a.y,a.z+0.7f), CVector(b.x,b.y,b.z+0.7f))) continue;
        for (auto& link : a.links) if (link == unused) { link = b.reference; break; }
        for (auto& link : b.links) if (link == unused) { link = a.reference; break; }
    }
    value.ray_count = kNavigationRays;
    for (int i = 0; i < kNavigationRays; ++i) {
        const auto angle = i * 6.283185307f / kNavigationRays;
        const float x = -std::sin(angle), y = std::cos(angle);
        float low = 0, high = 8.0f;
        for (int step = 0; step < 5; ++step) {
            const auto distance = (low + high) * 0.5f;
            bool clear = true;
            for (float side : {-0.3f, 0.0f, 0.3f}) {
                CVector start(eye.x + y*side, eye.y - x*side, eye.z);
                CVector end(start.x + x*distance, start.y + y*distance, eye.z);
                clear = clear && Clear(start, end);
            }
            if (clear) low = distance; else high = distance;
        }
        bool ground_found = false;
        const auto ground = CWorld::FindGroundZFor3DCoord(origin.x+x*std::min(low, 3.0f),
            origin.y+y*std::min(low, 3.0f), origin.z+2.0f, &ground_found, nullptr);
        const auto delta = ground - (origin.z - 1.0f);
        value.rays[i] = {ground_found && std::abs(delta) < 1.6f ? low : 0.0f, delta};
    }
    auto* pool = CPools::ms_pVehiclePool;
    for (unsigned int i = 0; pool && i < world.nearby_count; ++i) {
        auto* vehicle = pool->GetAtRef(world.vehicles[i].reference);
        if (!vehicle) continue;
        auto& item = value.vehicles[value.vehicle_count++];
        item.reference = world.vehicles[i].reference;
        const auto pos = vehicle->GetPosition();
        // Use reference-returning matrix accessors. The SDK's CPlaceable
        // vector-by-value wrappers use an incompatible hidden-return ABI here.
        const auto& matrix = vehicle->GetMatrix();
        const auto right = matrix.GetRight(), forward = matrix.GetForward();
        item.right_x = right.x; item.right_y = right.y;
        item.forward_x = forward.x; item.forward_y = forward.y;
        item.velocity_x = vehicle->m_vecMoveSpeed.x * 50;
        item.velocity_y = vehicle->m_vecMoveSpeed.y * 50;
        item.half_width = 1.0f; item.front_extent = 2.4f; item.rear_extent = -2.4f;
        if (auto* col = vehicle->GetColModel()) {
            item.half_width = std::max(std::abs(col->m_boundBox.m_vecMin.x), std::abs(col->m_boundBox.m_vecMax.x));
            item.front_extent = col->m_boundBox.m_vecMax.y;
            item.rear_extent = col->m_boundBox.m_vecMin.y;
        }
        CVector door = pos;
        item.flags |= (static_cast<unsigned>(vehicle->m_eDoorLock) & 0xffu) << 16;
        if (vehicle->m_nVehicleSubClass == 0) {
            CCarEnterExit::GetPositionToOpenCarDoor(&door, vehicle, 10); // CAR_DOOR_LF: driver
            item.flags |= 16;
            if (vehicle->CanPedOpenLocks(player) && vehicle->m_fHealth > 300 && !vehicle->m_pFire &&
                matrix.GetUp().z > 0.75f) item.flags |= 1;
            if (CCarEnterExit::IsCarDoorInUse(vehicle, 10, 10)) item.flags |= 8;
        }
        item.door_x = door.x; item.door_y = door.y; item.door_z = door.z;
        const auto offset = item.front_extent + 3.0f;
        const CVector front(pos.x+forward.x*offset, pos.y+forward.y*offset, pos.z+forward.z*offset);
        item.front_x = front.x; item.front_y = front.y; item.front_z = front.z;
        if (Clear(eye, CVector(door.x,door.y,door.z+0.55f))) item.flags |= 2;
        if (Clear(eye, CVector(front.x,front.y,front.z+0.55f))) item.flags |= 4;
        Anchors(value, door, item.door_anchors, false);
        Anchors(value, front, item.front_anchors, true);
    }
    InterlockedIncrement(&shared->sequence);
    std::memcpy(reinterpret_cast<char*>(shared) + 4, reinterpret_cast<const char*>(&value) + 4, sizeof(value)-4);
    MemoryBarrier();
    InterlockedIncrement(&shared->sequence);
}
}
