#include "agent_bridge.h"
#include "agent_protocol.h"
#include "navigation.h"
#include "movement.h"
#include "lifecycle.h"
#include "actors_protocol.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <cwchar>
#include <cstdio>
#include <utility>
#include "Events.h"
#include "CPad.h"
#include "CPools.h"
#include "CCamera.h"
#include "CTimer.h"
#include "CWorld.h"
#include "CPlayerInfo.h"
#include "CMenuManager.h"
#include "RenderWare.h"
#include "common.h"
#include "safetyhook.hpp"

namespace sa_agent::bridge {
namespace {
WorldSnapshot* world = nullptr;
ControlCommand* control = nullptr;
HANDLE world_handle = nullptr, control_handle = nullptr;
SafetyHookInline pad_hook, video_hook;
CControllerState last_pad{};
bool was_controlling = false, stopped = false, profile_enabled = true;
short original_pad_mode = 0;
unsigned int width = 1280, height = 720, fps_cap = 30, telemetry_hz = 10;
unsigned int max_action_ms = 750, last_request = 0;
float nearby_radius = 80.0f;
bool control_enabled = true, pad_hook_ready = false, video_hook_ready = false;
LARGE_INTEGER counter_frequency{}, next_frame{};

void LogVideo(int requested, int chosen, const RwVideoMode& mode, int result) {
    HMODULE self = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&LogVideo), &self);
    wchar_t path[MAX_PATH]{};
    GetModuleFileNameW(self, path, MAX_PATH);
    auto* slash = wcsrchr(path, L'\\');
    if (!slash) return;
    wcscpy_s(slash + 1, MAX_PATH - (slash + 1 - path), L"SAAgentTelemetry.log");
    FILE* file = nullptr;
    if (_wfopen_s(&file, path, L"a") == 0) {
        std::fprintf(file, "Video mode requested=%d chosen=%d size=%dx%d depth=%d flags=%u result=%d\n",
            requested, chosen, mode.width, mode.height, mode.depth, mode.flags, result);
        std::fclose(file);
    }
}

void* Map(const wchar_t* name, DWORD size, HANDLE& handle) {
    handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, size, name);
    return handle ? MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, size) : nullptr;
}

bool ReadCommand(ControlCommand& result) {
    if (!control) return false;
    const LONG before = InterlockedCompareExchange(&control->sequence, 0, 0);
    if (before & 1) return false;
    std::memcpy(&result, control, sizeof(result));
    MemoryBarrier();
    return before == InterlockedCompareExchange(&control->sequence, 0, 0) &&
           result.sequence == before && result.magic == kControlMagic &&
           result.schema == 1 && result.byte_size == sizeof(result);
}

void ApplyPad() {
    auto* pad = CPad::GetPad(0);
    if (!pad) return;
    ControlCommand request{};
    const auto now = GetTickCount64();
    bool active = !stopped && !lifecycle::Busy() && control_enabled && ReadCommand(request) && request.enabled == 1 &&
        request.owner_pid != 0 && request.issued_at_ms <= now && request.expires_at_ms > now &&
        request.expires_at_ms - request.issued_at_ms <= max_action_ms && request.action_id <= 29;
    if (active) {
        HANDLE owner = OpenProcess(SYNCHRONIZE, FALSE, request.owner_pid);
        active = owner && WaitForSingleObject(owner, 0) == WAIT_TIMEOUT;
        if (owner) CloseHandle(owner);
    }
    if (active && (CTimer::m_UserPause || CTimer::m_CodePause || pad->DisablePlayerControls)) active = false;
    if (!active) {
        if (was_controlling) {
            pad->OldState = last_pad;
            pad->NewState = {};
            pad->Mode = original_pad_mode;
            last_pad = {};
            was_controlling = false;
        }
        return;
    }
    if (!was_controlling) original_pad_mode = pad->Mode;
    pad->Mode = 0; // documented default pad layout; restored when the lease ends
    pad->OldState = was_controlling ? last_pad : CControllerState{};
    CControllerState value{};
    // Combat and weapon-cycle controls are strictly on foot.
    if (request.action_id >= 21 && FindPlayerVehicle(0, false)) request.action_id = 0;
    switch (request.action_id) {
        case 21: value.ButtonCircle = 255; break;
        case 22: value.RightShoulder1 = 255; break;
        case 23: value.RightShoulder1 = value.ButtonCircle = 255; break;
        case 24: value.RightShoulder1 = 255; value.RightStickX = -64; break;
        case 25: value.RightShoulder1 = 255; value.RightStickX = 64; break;
        case 26: value.RightShoulder1 = 255; value.RightStickY = -64; break;
        case 27: value.RightShoulder1 = 255; value.RightStickY = 64; break;
        case 28: value.RightShoulder2 = 255; break;
        case 29: value.LeftShoulder2 = 255; break;
        case 1: value.LeftStickY = -128; break;
        case 2: value.LeftStickY = 128; break;
        case 3: value.LeftStickX = -128; break;
        case 4: value.LeftStickX = 128; break;
        case 5: value.LeftStickY = -128; value.ButtonCross = 255; break;
        case 6: value.LeftStickY = -128; value.ButtonSquare = 255; break;
        case 7: value.ButtonTriangle = 255; break;
        case 8: value.ButtonCross = 255; break;
        case 9: case 12: value.ButtonSquare = 255; break;
        case 10: value.LeftStickX = -128; break;
        case 11: value.LeftStickX = 128; break;
        case 13: value.RightShoulder1 = 255; break;
        case 14: value.LeftStickX = -90; value.LeftStickY = -90; break;
        case 15: value.LeftStickX = 90; value.LeftStickY = -90; break;
        case 16: value.LeftStickX = -128; value.ButtonCross = 255; break;
        case 17: value.LeftStickX = 128; value.ButtonCross = 255; break;
        case 18: case 19: case 20: {
            // Fixed-width optional goal payload in the previously reserved
            // words. Convert world direction using the same camera orientation
            // that CTaskSimplePlayerOnFoot uses, every frame, as the camera turns.
            float goal[4]{};
            std::memcpy(goal, request.reserved, sizeof(goal));
            auto* player = FindPlayerPed(0);
            if (!player || FindPlayerVehicle(0, false) || !std::isfinite(goal[0]) ||
                !std::isfinite(goal[1]) || !std::isfinite(goal[2]) ||
                std::abs(goal[0]) > 6000 || std::abs(goal[1]) > 6000 ||
                goal[2] < 0.1f || goal[2] > 3.0f) break;
            const auto& pos = player->GetPosition();
            const auto dx = goal[0] - pos.x, dy = goal[1] - pos.y;
            if (dx*dx + dy*dy <= goal[2]*goal[2]) break;
            const float magnitude = request.action_id == 18 ? 60.0f : 128.0f;
            const auto stick = WorldDirectionToStick(dx, dy, TheCamera.m_fOrientation, magnitude);
            value.LeftStickX = stick.x;
            value.LeftStickY = stick.y;
            if (request.action_id == 20) value.ButtonCross = 255;
            break;
        }
        default: break;
    }
    // Enter/exit and jump are edge-triggered. Separate requests get a release
    // frame even if the model selects the same button twice in a row.
    if ((request.action_id == 6 || request.action_id == 7 || request.action_id == 28 || request.action_id == 29) && request.request_id != last_request &&
        (last_pad.ButtonTriangle || last_pad.ButtonSquare || last_pad.RightShoulder2 || last_pad.LeftShoulder2)) {
        value.ButtonTriangle = value.ButtonSquare = 0;
        value.RightShoulder2 = value.LeftShoulder2 = 0;
    } else {
        last_request = request.request_id;
    }
    pad->NewState = value;
    last_pad = value;
    was_controlling = true;
}

void __cdecl UpdatePadsHook() {
    pad_hook.call<void>();
    lifecycle::Tick();
    ApplyPad();
}

RwBool __cdecl SelectDeviceHook() {
    const int requested = FrontEndMenuManager.m_nDisplayVideoMode;
    int selected = requested;
    RwVideoMode chosen{};
    if (profile_enabled) {
        for (int i = 0; i < RwEngineGetNumVideoModes(); ++i) {
            RwVideoMode mode{};
            if (RwEngineGetVideoModeInfo(&mode, i) && mode.width == static_cast<int>(width) &&
                mode.height == static_cast<int>(height) && mode.depth == 32 &&
                (mode.flags & rwVIDEOMODEEXCLUSIVE)) {
                selected = i;
                chosen = mode;
                FrontEndMenuManager.m_nPrefsVideoMode = i;
                FrontEndMenuManager.m_nDisplayVideoMode = i;
                break;
            }
        }
    }
    // Select through the game's normal path so mode, refresh rate, globals and
    // raster dimensions all agree before the Direct3D device is created.
    const auto result = video_hook.call<RwBool>();
    LogVideo(requested, selected, chosen, result);
    return result;
}

void LimitFrameRate() {
    if (!profile_enabled || !fps_cap || stopped) return;
    LARGE_INTEGER now{};
    QueryPerformanceCounter(&now);
    if (next_frame.QuadPart) {
        while (now.QuadPart < next_frame.QuadPart) {
            const auto milliseconds = (next_frame.QuadPart - now.QuadPart) * 1000 / counter_frequency.QuadPart;
            if (milliseconds > 1) Sleep(static_cast<DWORD>(milliseconds - 1));
            else SwitchToThread();
            QueryPerformanceCounter(&now);
        }
    }
    // No catch-up bursts after a slow frame or a pause.
    next_frame.QuadPart = now.QuadPart + counter_frequency.QuadPart / fps_cap;
    RsGlobal.maxFPS = static_cast<int>(fps_cap);
}

void ReadProfile() {
    HMODULE self = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                      GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                      reinterpret_cast<LPCWSTR>(&ReadProfile), &self);
    wchar_t file[MAX_PATH]{};
    GetModuleFileNameW(self, file, MAX_PATH);
    auto* extension = wcsrchr(file, L'.');
    if (!extension) return;
    wcscpy_s(extension, MAX_PATH - (extension - file), L".ini");
    auto setting = [&](const wchar_t* section, const wchar_t* key, int fallback) {
        return GetPrivateProfileIntW(section, key, fallback, file);
    };
    profile_enabled = setting(L"Benchmark", L"Enabled", 1) != 0;
    width = std::clamp(setting(L"Benchmark", L"Width", 1280), 640u, 3840u);
    height = std::clamp(setting(L"Benchmark", L"Height", 720), 480u, 2160u);
    fps_cap = std::clamp(setting(L"Benchmark", L"FPSCap", 30), 30u, 60u);
    telemetry_hz = std::clamp(setting(L"Benchmark", L"TelemetryHz", 10), 5u, 30u);
    nearby_radius = static_cast<float>(std::clamp(setting(L"Benchmark", L"NearbyVehicleRadius", 80), 5u, 200u));
    max_action_ms = std::clamp(setting(L"Control", L"MaxActionMilliseconds", 750), 50u, 750u);
    control_enabled = setting(L"Control", L"Enabled", 1) != 0;
}
} // namespace

unsigned int TelemetryIntervalMilliseconds() { return 1000 / telemetry_hz; }

void Initialize() {
    ReadProfile();
    QueryPerformanceFrequency(&counter_frequency);
    world = static_cast<WorldSnapshot*>(Map(kWorldName, sizeof(WorldSnapshot), world_handle));
    control = static_cast<ControlCommand*>(Map(kControlName, sizeof(ControlCommand), control_handle));
    if (world) std::memset(world, 0, sizeof(*world));
    if (control) std::memset(control, 0, sizeof(*control));
    navigation::Initialize();
    actors::Initialize();
    lifecycle::Initialize();
    // CPad::UpdatePads is from Plugin-SDK; psSelectDevice is documented by
    // gta-reversed/source/app/platform/win/WinPs.cpp for the same 1.0-US EXE.
    // The parent ASI rejects other executables before calling Initialize.
    if (control_enabled && control) {
        auto hook = SafetyHookInline::create(reinterpret_cast<void*>(0x541DD0),
                                             reinterpret_cast<void*>(&UpdatePadsHook));
        if (hook) { pad_hook = std::move(*hook); pad_hook_ready = true; }
    }
    if (profile_enabled) {
        auto hook = SafetyHookInline::create(reinterpret_cast<void*>(0x746190),
                                             reinterpret_cast<void*>(&SelectDeviceHook));
        if (hook) { video_hook = std::move(*hook); video_hook_ready = true; }
        plugin::Events::drawingEvent.before += LimitFrameRate;
    }
}

void PublishWorld() {
    if (!world || stopped) return;
    WorldSnapshot value{};
    value.magic = kWorldMagic;
    value.schema = 1;
    value.byte_size = sizeof(value);
    value.process_id = GetCurrentProcessId();
    value.capabilities = (pad_hook_ready ? 1u : 0u) | (video_hook_ready ? 2u : 0u) |
                         (profile_enabled ? 4u : 0u);
    value.sampled_at_ms = GetTickCount64();
    value.player_vehicle_ref = -1;
    value.player_vehicle_class = -1;
    value.render_width = static_cast<unsigned int>(RsGlobal.maximumWidth);
    value.render_height = static_cast<unsigned int>(RsGlobal.maximumHeight);
    value.fps_cap = profile_enabled ? fps_cap : 0;
    value.last_applied_request = last_request;
    value.camera_forward_x = TheCamera.m_fCamFrontXNorm;
    value.camera_forward_y = TheCamera.m_fCamFrontYNorm;
    value.reserved[0] = CWorld::Players[0].m_nPlayerState;
    auto* player = FindPlayerPed(0);
    auto* pool = CPools::ms_pVehiclePool;
    if (player && pool) {
        const auto& origin = player->GetPosition();
        auto* current = FindPlayerVehicle(0, false);
        if (current) {
            value.player_vehicle_ref = pool->GetRef(current);
            value.player_vehicle_class = static_cast<int>(current->m_nVehicleSubClass);
            value.is_driver = current->m_pDriver == player;
        }
        const float heading = player->GetHeading();
        for (int direction = 0; direction < 3; ++direction) {
            const float angle = heading + (direction == 1 ? 0.785398f : direction == 2 ? -0.785398f : 0.0f);
            CVector start(origin.x, origin.y, origin.z + 0.7f);
            CVector end(start.x - std::sin(angle) * 3.0f,
                        start.y + std::cos(angle) * 3.0f, start.z);
            if (!CWorld::GetIsLineOfSightClear(start, end, true, false, false, true, true, false, false))
                value.obstacle_mask |= 1u << direction;
        }
        for (int i = 0; i < pool->m_nSize; ++i) {
            auto* vehicle = pool->GetAt(i);
            if (!vehicle) continue;
            const auto& pos = vehicle->GetPosition();
            const float dx = pos.x - origin.x, dy = pos.y - origin.y, dz = pos.z - origin.z;
            const float distance = std::sqrt(dx * dx + dy * dy + dz * dz);
            if (distance > nearby_radius) continue;
            const auto& speed = vehicle->m_vecMoveSpeed;
            NearbyVehicle entry{};
            entry.reference = pool->GetRef(vehicle);
            entry.model = vehicle->m_nModelIndex;
            entry.vehicle_class = static_cast<int>(vehicle->m_nVehicleSubClass);
            entry.x = pos.x; entry.y = pos.y; entry.z = pos.z;
            entry.heading = vehicle->GetHeading();
            entry.health = vehicle->m_fHealth;
            entry.speed_mps = std::sqrt(speed.x * speed.x + speed.y * speed.y + speed.z * speed.z) * 50.0f;
            entry.distance_m = distance;
            entry.flags = (vehicle->m_pDriver ? 1u : 0u) | (entry.speed_mps > 0.5f ? 2u : 0u) |
                          (vehicle == current ? 4u : 0u);
            unsigned int insert = 0;
            while (insert < value.nearby_count && value.vehicles[insert].distance_m <= distance) ++insert;
            if (insert >= kMaxNearbyVehicles) continue;
            const auto count = std::min(value.nearby_count + 1, static_cast<unsigned int>(kMaxNearbyVehicles));
            for (auto j = count - 1; j > insert; --j) value.vehicles[j] = value.vehicles[j - 1];
            value.vehicles[insert] = entry;
            value.nearby_count = count;
        }
    }
    InterlockedIncrement(&world->sequence);
    std::memcpy(reinterpret_cast<char*>(world) + 4, reinterpret_cast<const char*>(&value) + 4,
                sizeof(value) - 4);
    MemoryBarrier();
    InterlockedIncrement(&world->sequence);
    navigation::Publish(value);
    actors::Publish();
}

void Shutdown() { stopped = true; lifecycle::Shutdown(); }
} // namespace sa_agent::bridge
