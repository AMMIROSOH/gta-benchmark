# Game data and control contract

The game must be classic **GTA SA 1.0 US**, x86. The ASI rejects other versions
before installing hooks. The inspected local executable is the SDK's HoodLum
variant. Python can be x64: no process pointers cross this interface.

Structures are little-endian with 4-byte packing. A writer increments the 32-bit
sequence to odd, publishes payload, then increments to even. Readers accept a
copy only when the sequence is equal and even before and after. The Python
control writer owns a named mutex and issues write barriers around its copy.

| Mapping | Bytes | Magic | Writer |
| --- | --- | --- | --- |
| `Local\SAAgent.Telemetry.v1` | 160 | `0x54414153` | Game |
| `Local\SAAgent.World.v1` | 800 | `0x57414153` | Game |
| `Local\SAAgent.Control.v1` | 64 | `0x43414153` | One task runner |
| `Local\SAAgent.Navigation.v1` | 10112 | `0x4E414153` | Game |
| `Local\SAAgent.Lifecycle.v1` | 96 | `0x4C414153` | Game |
| `Local\SAAgent.Reset.v1` | 64 | `0x52414153` | Host runner |

Exact layouts are defined in `src/telemetry_protocol.h`, `src/agent_protocol.h`
and their Python counterparts. Change the mapping/schema name when changing
layouts. All headers include magic, schema, size, sequence and process identity.
Lifecycle layouts are in `src/lifecycle_protocol.h` and `sa_agent/lifecycle.py`.
The host-only reset channel acknowledges New Game requests and a new session
generation, then waits for controllable gameplay. It is separate from the
agent's action set. See [episode lifecycle](episode-lifecycle.md).

World state adds the current vehicle's pool reference, subclass and driver role;
up to 16 nearest loaded vehicles within the configured radius; camera forward
XY; three nearby geometry probes; player state; actual render dimensions; the
configured frame cap; and the last applied command ID. Vehicle references include
the pool slot generation. Approximate driver-door approach points are geometry,
not teleport/navigation actions. No global map or path planner is supplied.
The `reserved[0]` world word contains the SDK player state (playing=0, died=1,
arrested=2); remaining reserved words are zero.

The navigation mapping is required by the car acquisition controller. It publishes at 5 Hz:
up to 96 loaded road/pedestrian nodes with up to 16 links each, 16 vehicle
geometry records, and 16 clearance/ground probes. Geometry includes the engine's
front-left driver-door position, lock usability, body dimensions, forward/right
basis, velocity, a front traffic-interception point and clear route anchors.
It also reports whether the player's native vehicle-entry task is active.

The pad hook runs after `CPad::UpdatePads`. It preserves injected old/new button
state for edge detection and restores pad mode when the lease ends. An enabled
command needs an allowed action, a live owning process and an expiry within
750 ms of issue. Paused/script-disabled players do not receive inputs. Human
pad processing runs when there is no active agent lease. A named mutex prevents
two runners from owning controls concurrently.

Action codes match `sa_agent/actions.py`: 0 idle; 1 forward; 2 backward; 3 left;
4 right; 5 sprint; 6 jump; 7 enter/exit; 8 accelerate; 9 brake; 10 steer left;
11 steer right; 12 reverse; 13 handbrake; 14 forward-left; 15 forward-right;
16 accelerate-left; 17 accelerate-right; 18 world-walk; 19 world-run; 20 world-sprint.
For actions 18-20 the first three reserved command words encode float goal X,
goal Y and stop radius. The bridge converts these world goals to normal pad
input using the camera orientation every frame. The same owner, pause, expiry
and maximum-duration checks apply. Primitive on-foot directions remain
camera-relative; vehicle steering is car-relative. No fire, menu, spawn or arbitrary memory-write
action is exposed.

The device-selection hook at `psSelectDevice` (1.0-US address `0x746190`, documented
in gta-reversed's `source/app/platform/win/WinPs.cpp`) selects a supported 1280×720
mode through the game's normal initialization path. This keeps the selected mode,
refresh rate and raster dimensions consistent. A separate render callback caps
pacing at 30 FPS. The runner checks the published dimensions and cap. The local
build is installed and live telemetry confirms this profile and the pad hook.

The optional upstream III.VC.SA.WindowedMode v2.2 ASI makes the game a 1280×720
window for local recording. Its archive is pinned and SHA-256 checked by
`tools/setup_windowed.py`; its INI lives under `configs/`. It does not provide
agent observations or task actions.
