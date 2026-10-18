#pragma once
#include <Windows.h>
#include <cstdint>

namespace sa_agent::lifecycle {
inline constexpr wchar_t kStatusName[] = L"Local\\SAAgent.Lifecycle.v1";
inline constexpr wchar_t kCommandName[] = L"Local\\SAAgent.Reset.v1";
inline constexpr std::uint32_t kStatusMagic = 0x4C414153;
inline constexpr std::uint32_t kCommandMagic = 0x52414153;
enum Phase : std::uint32_t { Idle, Loading, PreparingIntro, Ready, Failed, Cancelled };
enum Error : std::uint32_t { NoError, OwnerLost, ResetDeadline, SamplingFault };
enum Flag : std::uint32_t {
    PlayerPresent = 1, PlayerControllable = 2, CutsceneActive = 4,
    MenuActive = 8, Playing = 16, ScreenFading = 32, ControllableStable = 64
};
#pragma pack(push, 4)
struct Command {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, owner_pid, request_id;
    std::uint64_t issued_at_ms, expires_at_ms;
    // action: 1 new game, 2 cancel, 3 finish validated preparation.
    // Cancel/finish use the original request ID. flags: 1 skip opening cutscenes.
    std::uint32_t action, target_pid, flags, timeout_ms, reserved[2];
};
struct Status {
    LONG sequence;
    std::uint32_t magic, schema, byte_size, process_id, capabilities;
    std::uint64_t sampled_at_ms;
    std::uint32_t request_id, owner_pid, phase, error, session_generation;
    std::int32_t game_state;
    std::uint32_t flags, cutscenes_skipped;
    std::uint64_t accepted_at_ms, completed_at_ms;
    std::uint32_t reserved[4];
};
#pragma pack(pop)
static_assert(sizeof(Command) == 64);
static_assert(sizeof(Status) == 96);
}
