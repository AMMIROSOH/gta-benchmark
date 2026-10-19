# Agent-owned task execution

The current five-task pack declares `action_interface=agent_actions_v1` and
records `policy_mode=agent_actions`, `executor_version=interruptible_pad_v1` and
`controller_version=null`. This applies to waypoint v3, steal-car v5, drive v2,
kill-NPC v1 and earn-money v1. Historical definitions and results keep their
original interfaces; the old car controller is available only to definitions
without the new declaration.

## What the agent receives

Every adapter receives the same projected structured observation: player state,
current vehicle, camera forward, clock/weather, local road/pedestrian nodes and
links, world-direction clearance rays, and nearby vehicles ordered by reference.
Vehicle geometry includes the native driver-door position, validity, door-use
state, lock enum, body extents and velocity. No suitability filter, ranked
candidate list, route cost, chosen route, interception point or anchor advice
is passed. Bicycles, locked and moving vehicles remain observable.

The Actors mapping adds up to 32 loaded NPCs and 32 active pickups within 80 m,
in pool order, plus inventory, the selected slot and retained attributed kill
events. Counts are bounded: absence is neither death nor proof that an entity
does not exist elsewhere. Pickup type 8/19 represents money; `amount` is the
engine ammo/quantity word, not a host valuation. Health, state, position and
heading, line of sight, raw ped type and selected weapon type are facts; no
victim selection or combat strategy is supplied. Engine ped types include 4/5
civilian male/female, 6 police and 7–16 gangs; these are engine classes, not
benchmark eligibility labels. The observation retains NPCs from every class.

Task instructions, deterministic evaluator progress, recent adapter decisions
and `current_command` accompany the observation. That command describes the
input active when the observation was sampled. State can change during inference.
The local recorder has no path into the model request.

## What the agent decides

One `Decision` supplies an action and exact `parameters`. Every action requires
integer `duration_ms` in 1–3000. World walking/running/sprinting also requires
`direction_world_xy`, a finite unit XY vector. `jump`, `enter_exit` and weapon
cycling are one-shot pulses limited to 400 ms. Extra fields and execution plans
are rejected. The task action set and current player mode remain enforced.

Jev uses a fixed unranked held-control menu: 16 world directions, each explicitly
authorizing up to 3000 ms, and the task-permitted pad actions. Its next decision
preempts that hold; idle releases controls. Pulse actions offer only 400 ms. The
manifest identifies this as `jev_held_controls_3000ms_v1`. Earlier development
menus with short-duration choices are retained in their original run traces. Other
adapters can supply any valid unit direction and duration, without confidence
or probability metadata. No Jev-specific distribution is required by the runner.

The agent owns route choice, obstacle handling, vehicle selection, interception,
entry attempts, waiting, combat and recovery. Entry presses the ordinary game
button once: GTA chooses a nearby door and runs its built-in animation. The host
never walks to that door, retries entry or follows a selected entity.

Combat actions press ordinary pad buttons: attack, aim, aim+attack, aim with
half-strength right-stick adjustment, and weapon cycling. Normal GTA targeting
and configured aim assistance apply; behavior depends on game input settings
and must be disclosed in comparisons. There
is no host aim correction, pursuit, target snapping or weapon grant.

## Input continuity and limits

The executor mechanically projects a selected world direction to one fixed
endpoint 20 m from the execution origin. It does not move that endpoint during
the command. Native pad projection compensates only for camera rotation; normal
collisions still apply. An endpoint reached early can stop movement.

The next model request overlaps execution. A newer accepted decision immediately
preempts the previous command. The host refreshes short native leases (at most
300 ms, about every 100 ms) only until the fixed agent-authorized deadline, capped
by the task deadline. A pulse gets one lease of at most 400 ms and is never
renewed. Renewals carry the same action and frozen endpoint; they make no route,
target, retry or recovery decision. A stalled/crashed runner therefore loses
input authority within the native lease, rather than keeping a three-second key
hold alive. Native ownership, seqlock, live-process and expiry checks remain.

Malformed/stale decisions, API errors, pause, lost focus/telemetry and player-mode
changes cancel authorization. Death, arrest and task completion release controls.
An expired command stays released until the agent supplies another valid command.
This removes latency-driven gaps when the agent chooses a sufficient horizon;
it cannot guarantee continuous walking if the agent chooses short holds or waits.

## Auditing

`source=agent_action` records the accepted command ID, parameters, origin, frozen
endpoint and authorized duration. Each native write uses
`source=authorized_command_lease` with its parent command ID, native request ID,
lease duration and authorization end. `applied_actions` counts agent commands;
`native_input_leases` counts writes. `navigation_control_ticks` stays zero.
See [results](results.md), [bridge layouts](bridge.md) and [task scoring](task-pack.md).
