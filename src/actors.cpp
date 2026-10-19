#include "actors_protocol.h"
#include "kill_ledger.h"
#include "lifecycle.h"
#include <Windows.h>
#include <algorithm>
#include <cstring>
#include <utility>
#include "CPools.h"
#include "CPickups.h"
#include "CWorld.h"
#include "common.h"
#include "safetyhook.hpp"
namespace sa_agent::actors {
namespace {
Snapshot* shared = nullptr;
HANDLE handle = nullptr;
SafetyHookInline kill_hook;
KillLedger ledger;
Kill events[128]{};
std::uint32_t latest = 0;
std::uint32_t last_generation = 0;
// Static cdecl routine; gta-reversed/source/game_sa/Events/EventHandler.{h,cpp}.
// This is the engine's death registration, never inferred from an entity disappearing.
void __cdecl RegisterKill(const CPed* victim, const CEntity* source, eWeaponType weapon, bool headshot) {
    auto* player = FindPlayerPed(0);
    auto* car = FindPlayerVehicle(0, false);
    auto* pool = CPools::ms_pPedPool;
    const auto attribution = player && source == player ? 1u : car && car->m_pDriver == player && source == car ? 2u : 0u;
    if (victim && victim != player && pool && attribution) {
        const auto ref = pool->GetRef(const_cast<CPed*>(victim));
        if (ledger.Register(ref, true)) {
            const auto& pos = victim->GetPosition();
            auto& event = events[latest % 128];
            event = {++latest, ref, static_cast<int>(weapon), attribution | (headshot ? 4u : 0u),
                     GetTickCount64(), pos.x, pos.y, pos.z};
        }
    }
    kill_hook.call<void>(victim, source, weapon, headshot);
}
}
void Initialize() {
    handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(Snapshot), kName);
    shared = handle ? static_cast<Snapshot*>(MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Snapshot))) : nullptr;
    if (shared) std::memset(shared, 0, sizeof(*shared));
    auto hook = SafetyHookInline::create(reinterpret_cast<void*>(0x4B9340), reinterpret_cast<void*>(&RegisterKill));
    if (hook) kill_hook = std::move(*hook);
}
void Publish() {
    if (!shared) return;
    const auto generation = lifecycle::Generation();
    if (generation != last_generation) {
        // A New Game may reuse exactly the same pool slot and generation IDs.
        // Keep event IDs monotonic, but reset victim-lifetime deduplication.
        ledger.Reset();
        last_generation = generation;
    }
    Snapshot value{};
    value.magic = kMagic; value.schema = 1; value.byte_size = sizeof(value);
    value.process_id = GetCurrentProcessId(); value.sampled_at_ms = GetTickCount64();
    value.capabilities = kill_hook ? 7u : 6u; // death events, combat, detailed NPC facts
    value.latest_event_id = latest; value.event_count = std::min(latest, 128u);
    for (unsigned i = 0; i < value.event_count; ++i)
        value.events[i] = events[(latest-value.event_count+i) % 128];
    auto* player = FindPlayerPed(0);
    auto* pool = CPools::ms_pPedPool;
    if (player && pool) {
        const auto& origin = player->GetPosition();
        auto nearby = [&](const CVector& pos) {
            const auto dx = origin.x-pos.x, dy = origin.y-pos.y, dz = origin.z-pos.z;
            return dx*dx+dy*dy+dz*dz <= 80.f*80.f;
        };
        value.selected_slot = player->m_nSelectedWepSlot;
        for (unsigned i = 0; i < 13; ++i)
            value.weapons[i] = {static_cast<int>(player->m_aWeapons[i].m_eWeaponType), player->m_aWeapons[i].m_nAmmoTotal, i};
        for (int i = 0; i < pool->m_nSize; ++i) {
            auto* ped = pool->GetAt(i);
            if (!ped) continue;
            const auto ref = pool->GetRef(ped);
            ledger.Observe(ref);
            if (ped == player || value.ped_count >= 32) continue;
            const auto& pos = ped->GetPosition();
            if (!nearby(pos)) continue;
            const auto slot = ped->m_nSelectedWepSlot;
            const auto weapon = slot < 13 ? static_cast<unsigned>(ped->m_aWeapons[slot].m_eWeaponType) : 0u;
            const bool visible = CWorld::GetIsLineOfSightClear(
                CVector(origin.x, origin.y, origin.z+.7f), CVector(pos.x, pos.y, pos.z+.7f),
                true, true, false, true, true, false, false);
            const auto facts = (ped->bInVehicle ? 1u : 0u) | (visible ? 2u : 0u) |
                ((static_cast<unsigned>(ped->m_nPedType) & 255u) << 8) | ((weapon & 255u) << 16);
            value.peds[value.ped_count++] = {ref, ped->m_nModelIndex, static_cast<int>(ped->m_ePedState),
                facts, pos.x, pos.y, pos.z, ped->m_fHealth, ped->m_fArmour, ped->GetHeading()};
        }
        for (unsigned i = 0; i < 620 && value.pickup_count < 32; ++i) {
            auto& pickup = CPickups::aPickUps[i];
            if (pickup.m_nPickupType == PICKUP_NONE || pickup.m_nFlags.bDisabled) continue;
            const auto pos = pickup.GetPosn();
            if (!nearby(pos)) continue;
            const auto ref = (static_cast<unsigned>(static_cast<unsigned short>(pickup.m_nReferenceIndex)) << 16) | i;
            value.pickups[value.pickup_count++] = {ref, pickup.m_nModelIndex, pickup.m_nPickupType,
                pickup.m_nAmmo, pos.x, pos.y, pos.z};
        }
    }
    InterlockedIncrement(reinterpret_cast<volatile LONG*>(&shared->sequence));
    std::memcpy(reinterpret_cast<char*>(shared)+4, reinterpret_cast<const char*>(&value)+4, sizeof(value)-4);
    MemoryBarrier();
    InterlockedIncrement(reinterpret_cast<volatile LONG*>(&shared->sequence));
}
}
