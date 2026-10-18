#include "lifecycle.h"
#include "lifecycle_protocol.h"
#include <cstring>
#include "Events.h"
#include "CGame.h"
#include "CMenuManager.h"
#include "CCutsceneMgr.h"
#include "CCamera.h"
#include "CPad.h"
#include "CTimer.h"
#include "CWorld.h"
#include "CPlayerInfo.h"
#include "common.h"

namespace sa_agent::lifecycle {
namespace {
Status* shared = nullptr;
Command* command = nullptr;
HANDLE status_handle = nullptr, command_handle = nullptr;
Status current{};
std::uint32_t generation_at_request = 0;
std::uint64_t deadline = 0, ready_since = 0, last_skip = 0;
bool skip_intro = true, stopped = false;

void* Map(const wchar_t* name, DWORD size, HANDLE& handle) {
    handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, size, name);
    return handle ? MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, size) : nullptr;
}

bool OwnerAlive(std::uint32_t pid) {
    HANDLE owner = OpenProcess(SYNCHRONIZE, FALSE, pid);
    const bool alive = owner && WaitForSingleObject(owner, 0) == WAIT_TIMEOUT;
    if (owner) CloseHandle(owner);
    return alive;
}

bool Foreground() {
    DWORD pid = 0;
    const auto window = GetForegroundWindow();
    if (!window || IsIconic(window)) return false;
    GetWindowThreadProcessId(window, &pid);
    return pid == GetCurrentProcessId();
}

void Publish() {
    if (!shared) return;
    current.sampled_at_ms = GetTickCount64();
    current.game_state = gGameState;
    InterlockedIncrement(&shared->sequence);
    std::memcpy(reinterpret_cast<char*>(shared) + 4,
                reinterpret_cast<const char*>(&current) + 4, sizeof(current) - 4);
    MemoryBarrier();
    InterlockedIncrement(&shared->sequence);
}

bool Read(Command& value) {
    if (!command) return false;
    const LONG before = InterlockedCompareExchange(&command->sequence, 0, 0);
    if (before & 1) return false;
    std::memcpy(&value, command, sizeof(value));
    MemoryBarrier();
    const auto now = GetTickCount64();
    return before == InterlockedCompareExchange(&command->sequence, 0, 0) &&
        value.sequence == before && value.magic == kCommandMagic && value.schema == 1 &&
        value.byte_size == sizeof(value) && value.target_pid == GetCurrentProcessId() &&
        value.owner_pid && value.request_id && value.issued_at_ms <= now &&
        value.expires_at_ms > now && value.expires_at_ms - value.issued_at_ms <= 5000 &&
        OwnerAlive(value.owner_pid);
}

void SessionInitialized() {
    ++current.session_generation;
    ready_since = 0;
}

void TickImpl() {
    const auto now = GetTickCount64();
    Command request{};
    bool finish_requested = false;
    if (Read(request)) {
        const bool same_request = request.request_id == current.request_id &&
                                  request.owner_pid == current.owner_pid;
        finish_requested = same_request && request.action == 3;
        if (request.action == 2 && same_request && Busy()) {
            current.phase = Cancelled;
            current.completed_at_ms = now;
        } else if (request.action == 1 && !same_request && !Busy() && Foreground() &&
                   (gGameState == 7 || gGameState == 9) &&
                   !FrontEndMenuManager.m_bWantToRestart && !FrontEndMenuManager.m_bWantToLoad &&
                   request.timeout_ms >= 10000 && request.timeout_ms <= 600000 &&
                   (request.flags & ~1u) == 0) {
            current.request_id = request.request_id;
            current.owner_pid = request.owner_pid;
            current.phase = Loading;
            current.error = NoError;
            current.cutscenes_skipped = 0;
            current.accepted_at_ms = now;
            current.completed_at_ms = 0;
            generation_at_request = current.session_generation;
            deadline = now + request.timeout_ms;
            ready_since = last_skip = 0;
            skip_intro = (request.flags & 1) != 0;
            // The same front-end path as confirming New Game. The outer game
            // loop performs shutdown/reinitialization after this callback returns.
            // Do not call CGame::InitialiseWhenRestarting from inside CGame::Process.
            CGame::bMissionPackGame = false;
            FrontEndMenuManager.m_nSelectedMissionPack = 0;
            FrontEndMenuManager.m_bWantToLoad = false;
            FrontEndMenuManager.DoSettingsBeforeStartingAGame();
        }
    }
    current.flags = FrontEndMenuManager.m_bMenuActive ? MenuActive : 0u;
    // Game state values follow the classic executable: 7 front end, 9 gameplay.
    // Avoid dereferencing world pools while the outer loop is rebuilding them.
    if (gGameState == 9 && !FrontEndMenuManager.m_bWantToRestart) {
        auto* player = FindPlayerPed(0);
        auto* pad = CPad::GetPad(0);
        if (player) current.flags |= PlayerPresent;
        if (CCutsceneMgr::ms_running || CCutsceneMgr::ms_cutsceneProcessing)
            current.flags |= CutsceneActive;
        if (TheCamera.m_bFading || TheCamera.m_fFadeAlpha > 1.0f)
            current.flags |= ScreenFading;
        const bool playing = !CTimer::m_UserPause && !CTimer::m_CodePause &&
            !FrontEndMenuManager.m_bMenuActive && CWorld::Players[0].m_nPlayerState == 0;
        if (playing) current.flags |= Playing;
        if (player && pad && !pad->DisablePlayerControls && playing &&
            !(current.flags & (CutsceneActive | ScreenFading)) &&
            !TheCamera.m_bWideScreenOn && player->m_fHealth > 0)
            current.flags |= PlayerControllable;
    }
    if (!Busy()) { Publish(); return; }
    if (!OwnerAlive(current.owner_pid) || now >= deadline) {
        current.error = now >= deadline ? ResetDeadline : OwnerLost;
        current.phase = Failed;
        current.completed_at_ms = now;
        Publish();
        return;
    }
    if (current.session_generation != generation_at_request) {
        current.phase = PreparingIntro;
        if (skip_intro && (current.flags & CutsceneActive) &&
            (current.flags & PlayerPresent) && CCutsceneMgr::ms_running &&
            !CCutsceneMgr::ms_wasCutsceneSkipped && CCutsceneMgr::ms_cutsceneTimer >= 1.0f &&
            now - last_skip >= 1000 && Foreground()) {
            // Standard cutscene skip function; lets the original script clean up.
            CCutsceneMgr::SkipCutscene();
            ++current.cutscenes_skipped;
            last_skip = now;
        }
        if ((current.flags & PlayerControllable) && Foreground()) {
            if (!ready_since) ready_since = now;
            if (now - ready_since >= 3000) {
                current.flags |= ControllableStable;
                // Keep preparation active across gaps between intro scenes.
                // Only the host, after verifying the opening alley and BMX,
                // can acknowledge that the requested starting state is ready.
                if (finish_requested) {
                    current.phase = Ready;
                    current.completed_at_ms = now;
                }
            }
        } else {
            ready_since = 0;
        }
    }
    Publish();
}
}

bool Busy() { return current.phase == Loading || current.phase == PreparingIntro; }

void Initialize() {
    shared = static_cast<Status*>(Map(kStatusName, sizeof(Status), status_handle));
    command = static_cast<Command*>(Map(kCommandName, sizeof(Command), command_handle));
    if (shared) std::memset(shared, 0, sizeof(*shared));
    if (command) std::memset(command, 0, sizeof(*command));
    current.magic = kStatusMagic;
    current.schema = 1;
    current.byte_size = sizeof(current);
    current.process_id = GetCurrentProcessId();
    current.capabilities = shared && command ? 1u : 0u;
    plugin::Events::initGameEvent += SessionInitialized;
    plugin::Events::reInitGameEvent += SessionInitialized;
    Publish();
}

void Tick() {
    if (stopped || !shared) return;
    __try { TickImpl(); }
    __except (GetExceptionCode() == EXCEPTION_ACCESS_VIOLATION
                 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        current.phase = Failed;
        current.error = SamplingFault;
        current.completed_at_ms = GetTickCount64();
        Publish();
    }
}

void Shutdown() { stopped = true; }
}
