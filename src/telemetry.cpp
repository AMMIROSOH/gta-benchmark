#include "telemetry_protocol.h"
#include "agent_bridge.h"
#include <cmath>
#include <cstring>
#include <cstdio>
#include <cwchar>
#include "Events.h"
#include "GameVersion.h"
#include "CClock.h"
#include "CTimer.h"
#include "CWeather.h"
#include "CWorld.h"
#include "CPlayerInfo.h"
#include "CWanted.h"
#include "common.h"

namespace {
using namespace sa_agent;
HANDLE mapping_handle = nullptr;
Snapshot* shared = nullptr;
std::uint64_t last_sample_ms = 0;
std::uint32_t samples = 0, errors = 0;
bool initialized = false, stopping = false;

void Log(const char* message) {
    // Resolve relative to our own module, never the game's working directory.
    HMODULE self = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                          GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                          reinterpret_cast<LPCWSTR>(&Log), &self)) return;
    wchar_t path[MAX_PATH]{};
    if (!GetModuleFileNameW(self, path, MAX_PATH)) return;
    auto* separator = wcsrchr(path, L'\\');
    if (!separator) return;
    wcscpy_s(separator + 1, MAX_PATH - (separator + 1 - path), L"SAAgentTelemetry.log");
    FILE* file = nullptr;
    if (_wfopen_s(&file, path, L"a") == 0) {
        std::fprintf(file, "%llu %s\n", GetTickCount64(), message);
        std::fclose(file);
    }
}

Snapshot Header() {
    Snapshot value{};
    value.magic = kMagic;
    value.schema = kSchema;
    value.byte_size = sizeof(Snapshot);
    value.process_id = GetCurrentProcessId();
    value.game_version = plugin::GetGameVersion();
    value.sampled_at_ms = GetTickCount64();
    value.sample_count = samples;
    value.error_count = errors;
    value.sdk_version = 1005;
    value.vehicle_model = -1;
    return value;
}

void Publish(const Snapshot& value) {
    if (!shared) return;
    // Odd sequence means a write is in progress. Interlocked operations fence
    // the copy so readers can reject torn snapshots without blocking the game.
    InterlockedIncrement(&shared->sequence);
    std::memcpy(reinterpret_cast<char*>(shared) + sizeof(LONG),
                reinterpret_cast<const char*>(&value) + sizeof(LONG),
                sizeof(Snapshot) - sizeof(LONG));
    MemoryBarrier();
    InterlockedIncrement(&shared->sequence);
}

void Collect(Snapshot& value) {
    value.game_time_ms = CTimer::m_snTimeInMilliseconds;
    if (CTimer::m_UserPause) value.flags |= UserPaused;
    if (CTimer::m_CodePause) value.flags |= CodePaused;
    value.clock_hour = CClock::ms_nGameClockHours;
    value.clock_minute = CClock::ms_nGameClockMinutes;
    value.clock_second = CClock::ms_nGameClockSeconds;
    value.weather_old = CWeather::OldWeatherType;
    value.weather_new = CWeather::NewWeatherType;

    auto* player = FindPlayerPed(0);
    if (!player) return;
    value.flags |= PlayerReady;
    const auto& pos = player->GetPosition();
    value.x = pos.x;
    value.y = pos.y;
    value.z = pos.z;
    value.heading_radians = player->GetHeading();
    value.health = player->m_fHealth;
    value.max_health = player->m_fMaxHealth;
    value.armour = player->m_fArmour;
    value.interior = player->m_nAreaCode;
    value.money = CWorld::Players[0].m_nMoney;
    if (auto* wanted = player->GetWanted()) value.wanted_level = wanted->m_nWantedLevel;
    if (player->m_nSelectedWepSlot < 13) {
        const auto& weapon = player->m_aWeapons[player->m_nSelectedWepSlot];
        value.weapon_type = static_cast<int>(weapon.m_eWeaponType);
        value.ammo_total = weapon.m_nAmmoTotal;
    }

    auto* vehicle = FindPlayerVehicle(0, false);
    const auto& velocity = vehicle ? vehicle->m_vecMoveSpeed : player->m_vecMoveSpeed;
    // SA velocity is expressed per 1/50-second simulation step.
    value.velocity_x = velocity.x * 50.0f;
    value.velocity_y = velocity.y * 50.0f;
    value.velocity_z = velocity.z * 50.0f;
    value.speed_mps = std::sqrt(value.velocity_x * value.velocity_x +
                                value.velocity_y * value.velocity_y +
                                value.velocity_z * value.velocity_z);
    if (vehicle) {
        value.flags |= InVehicle;
        value.vehicle_model = vehicle->m_nModelIndex;
        value.vehicle_health = vehicle->m_fHealth;
    }
}

void OnFrame() {
    if (stopping || !shared) return;
    const auto now = GetTickCount64();
    if (now - last_sample_ms < sa_agent::bridge::TelemetryIntervalMilliseconds()) return;
    last_sample_ms = now;
    ++samples;
    auto value = Header();
    __try {
        Collect(value);
        sa_agent::bridge::PublishWorld();
    } __except (GetExceptionCode() == EXCEPTION_ACCESS_VIOLATION
                  ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        ++errors;
        value = Header();
        value.flags |= SampleError;
        if (errors == 1) Log("Game state unavailable during sampling; snapshot marked invalid.");
    }
    Publish(value);
}

void OnShutdown() {
    sa_agent::bridge::Shutdown();
    stopping = true;
    auto value = Header();
    value.flags = Stopping;
    Publish(value);
    Log("Game shutting down.");
    // Windows releases the mapping when the game exits. Keeping it mapped here
    // avoids a dangling pointer during any late game callbacks.
}
} // namespace

extern "C" __declspec(dllexport) void InitializeASI() {
    if (initialized) return;
    initialized = true;
    if (!plugin::IsGameVersion10us()) {
        Log("Unsupported executable: this build supports classic SA 1.0 US only. No hooks installed.");
        return;
    }
    mapping_handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                                       0, sizeof(Snapshot), kMappingName);
    if (!mapping_handle) {
        Log("CreateFileMappingW failed.");
        return;
    }
    const bool already_exists = GetLastError() == ERROR_ALREADY_EXISTS;
    shared = static_cast<Snapshot*>(MapViewOfFile(mapping_handle, FILE_MAP_ALL_ACCESS,
                                                 0, 0, sizeof(Snapshot)));
    if (!shared) {
        CloseHandle(mapping_handle);
        mapping_handle = nullptr;
        Log("MapViewOfFile failed.");
        return;
    }
    if (already_exists && shared->magic == kMagic && shared->process_id != GetCurrentProcessId()) {
        HANDLE owner = OpenProcess(SYNCHRONIZE, FALSE, shared->process_id);
        const bool live_owner = owner && WaitForSingleObject(owner, 0) == WAIT_TIMEOUT;
        if (owner) CloseHandle(owner);
        if (live_owner) {
            UnmapViewOfFile(shared);
            CloseHandle(mapping_handle);
            shared = nullptr;
            mapping_handle = nullptr;
            Log("Another running game owns the telemetry mapping.");
            return;
        }
    }
    shared->sequence = 0;
    Publish(Header());
    sa_agent::bridge::Initialize();
    plugin::Events::gameProcessEvent += OnFrame;
    plugin::Events::shutdownRwEvent += OnShutdown;
    Log("Started: Plugin-SDK 1005, GTA SA 1.0 US, schema 1, 10 Hz, local shared memory.");
}
