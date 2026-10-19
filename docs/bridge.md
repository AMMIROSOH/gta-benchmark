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
| `Local\SAAgent.Actors.v1` | 6996 | `0x50414153` | Game |
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
action is exposed by the historical 0–20 action set.

The current bridge adds codes 21 attack, 22 aim, 23 aim+attack, 24–27 aim with
right-stick left/right/up/down, 28 next weapon and 29 previous weapon. These are
on-foot normal pad inputs, with the same ownership, expiry and pause checks.
Normal GTA targeting/aim assistance applies; the host does not select a victim
or aim at coordinates. The inspected button mapping is documented in
[gta-reversed Pad.cpp](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Pad.cpp).

`actors_protocol.h` and `actor_state.py` define the new 6996-byte Actors layout:
56-byte header, 32 × 40-byte pedestrians, 32 × 28-byte pickups, 128 × 36-byte
kill events, and 13 × 12-byte inventory slots. Header offsets: sampled tick 24,
latest event 32, ped count 36, pickup count 40, event count 44, selected slot 48.
Event offsets: ID 0, victim reference 4, weapon 8, attribution flags 12, Windows
tick 16, XYZ 24. References contain pool generation; no pointers cross the ABI.
Capabilities bit 0 confirms the death hook; bit 1 confirms combat input support;
bit 2 confirms detailed NPC facts. Ped flags: bit 0 in vehicle, bit 1 line of
sight from player eye to NPC torso (buildings, vehicles and objects), bits 8–15
raw engine ped type, bits 16–23 selected weapon type. Older mappings without
capability bit 2 produce null for the three added fields, preserving compatibility.
Snapshots publish with telemetry at 10 Hz. All snapshots retain the most recent
128 engine-attributed death events, including unloaded victims. An event gap
fails scoring rather than silently losing kills. Actor and pickup lists cover
80 m, in pool order, capped at 32 each. See [task scoring](task-pack.md).

Navigation vehicle flags bits 16–23 now contain the raw engine door-lock enum;
the remaining geometry layout is unchanged. The agent-actions projection exposes
door coordinates, validity, busy state and that enum, while excluding the older
controller suitability flag, interception point and route anchors.

Current tasks use [agent actions](agent-actions.md). The Python authorization
is at most 3000 ms, but native leases remain at most 300 ms (one-shot pulses
at most 400 ms). Renewals have a fixed endpoint and authorization deadline.
This changes no existing mapping size and does not extend the native 750-ms cap.

Waypoint task version 2 reuses this unchanged ABI for agent-directed bounded
movement. Python projects the agent's unit direction into one point 3 m away
and sends one lease of at most 750 ms. It supplies no route or automatic renewal.
See [waypoint navigation](waypoint-navigation.md). The separate car controller
continues to use world goals under its existing assistance contract.

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
